"""Regressions for Stage 5 manual QA bugs."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from flask import Flask
from src.models import db, Account, Bill, CreditCard, Income
from src.routes import bp
from src.utils.card_forecast import payoff_estimate
from src.utils.dashboard import build_dashboard_data


class ManualQAFixes(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder='../src/templates')
        self.app.config.update(TESTING=True, SECRET_KEY='qa', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app)
        self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.old, self.new = Account(name='Old'), Account(name='New')
        db.session.add_all([self.old, self.new])
        db.session.flush()
        self.card = CreditCard(name='Visa', payment_account_id=self.new.id,
            statement_close_day=15, payment_due_day=31, balance=Decimal('500'),
            balance_as_of=date(2026, 10, 23), minimum_payment=Decimal('25'),
            extra_payment=Decimal('10'), annual_percentage_rate=Decimal('23'))
        db.session.add(self.card)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def bill(self):
        b = Bill(name='Subscription', owner='QA', amount=Decimal('30'), due_day=20,
                 account_id=self.old.id, credit_card_id=self.card.id)
        db.session.add(b)
        db.session.commit()
        return b

    def test_charge_follows_card_account_without_rewriting_bill(self):
        b = self.bill()
        with patch('src.routes.render_template', return_value='report') as render:
            self.client.get('/report?year=2026&month=11')
        rows = {r['account'].id: r for r in render.call_args.kwargs['report_data']}
        self.assertEqual(rows[self.old.id]['totals']['credit_card_charges'], 0)
        self.assertEqual(rows[self.new.id]['totals']['credit_card_charges'], 30)
        self.assertEqual(rows[self.new.id]['totals']['bills'], 0)
        self.assertEqual(b.account_id, self.old.id)

    def test_inactive_assignment_rejected_and_existing_link_warned(self):
        b = self.bill()
        self.card.is_active = False
        db.session.commit()
        form = dict(name='Changed', owner='QA', amount='40', frequency='monthly', due_day='20',
                    payment_method=f'card:{self.card.id}')
        for path in ['/bills', f'/bills/{b.id}']:
            response = self.client.post(path, data=form, follow_redirects=True)
            self.assertIn(b'Inactive credit cards cannot receive recurring bills', response.data)
        self.assertEqual(Bill.query.count(), 1)
        self.assertEqual(b.amount, Decimal('30'))
        self.assertEqual(b.name, 'Subscription')
        self.assertNotIn(f'value="card:{self.card.id}"'.encode(), self.client.get('/bills').data)
        response = self.client.get('/report?year=2026&month=11')
        self.assertIn(b'references inactive card', response.data)
        form['payment_method'] = f'account:{self.new.id}'
        self.client.post(f'/bills/{b.id}', data=form)
        self.assertIsNone(b.credit_card_id)

    def test_invalid_income_cannot_create_or_overwrite(self):
        inc = Income(name='Salary', amount=Decimal('125'), frequency='weekly',
                     next_pay=date(2026, 10, 23), account_id=self.old.id)
        db.session.add(inc)
        db.session.commit()
        form = dict(name='Changed', frequency='weekly', next_pay='2026-10-23', account_id=str(self.new.id))
        for amount in ['-10', 'NaN', 'Infinity', '1.001', 'abc']:
            form['amount'] = amount
            for path in ['/incomes', f'/incomes/{inc.id}']:
                self.client.post(path, data=form)
            db.session.expire_all()
            self.assertEqual(Income.query.count(), 1)
            self.assertEqual(inc.amount, Decimal('125'))
            self.assertEqual(inc.name, 'Salary')
            self.assertEqual(inc.account_id, self.old.id)
        form['amount'] = '130.25'
        self.client.post(f'/incomes/{inc.id}', data=form)
        self.assertEqual(inc.amount, Decimal('130.25'))

    def test_promotion_switches_to_regular_apr(self):
        args = dict(promotional_apr='0', promotional_end=date(2026, 11, 23), as_of=date(2026, 10, 23))
        estimate = payoff_estimate('100', '12', '30', **args)
        # Two zero-interest periods, then interest of 0.40 and 0.10.
        self.assertEqual(estimate, dict(months=4, interest=Decimal('0.50'), total_paid=Decimal('100.50')))
        expired = payoff_estimate('100', '12', '30', **{**args, 'promotional_end': date(2026, 10, 22)})
        self.assertEqual(expired, payoff_estimate('100', '12', '30'))
        self.assertEqual(payoff_estimate('50', '23', '35', **args)['interest'], Decimal('0'))
        self.assertIsNone(payoff_estimate('1000', '24', '1', **args))
        self.assertEqual(payoff_estimate('50', None, '35', **args)['interest'], Decimal('0'))
        self.assertIsNone(payoff_estimate('500', None, '35', **args))
        self.assertIsNotNone(payoff_estimate('100', '0', '1', promotional_apr='24',
            promotional_end=date(2026, 10, 23), as_of=date(2026, 10, 23)))

    def test_dashboard_estimates_beyond_promo_expiration(self):
        self.card.promotional_apr = Decimal('0')
        self.card.promotional_apr_end_date = date(2027, 4, 23)
        summary = build_dashboard_data([], today=date(2026, 10, 23), credit_cards=[self.card])['credit_card_summaries'][0]
        estimate = summary['payoff_estimate']
        self.assertIsNotNone(estimate)
        self.assertGreater(estimate['interest'], 0)
        self.assertLess(estimate['interest'], Decimal('89.96'))
        self.assertEqual(estimate['total_paid'], Decimal('500') + estimate['interest'])
