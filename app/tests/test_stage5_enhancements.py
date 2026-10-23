"""Behavior checks for the Stage 5 enhancement pass."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from flask import Flask
from flask_migrate import Migrate, stamp, upgrade, downgrade
from sqlalchemy import inspect, text
from src.models import db, Account, Bill, BillPause, CreditCard
from src.routes import bp
from src.utils.dashboard import bill_dates

class Enhancements(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder='../src/templates')
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app)
        Migrate(self.app, db)
        self.app.register_blueprint(bp)
        self.ctx = self.app.app_context(); self.ctx.push()
        db.create_all()
        self.account = Account(name='Checking')
        db.session.add(self.account); db.session.flush()
        self.bill = Bill(name='Internet', owner='Test', amount=30, due_day=20, account_id=self.account.id)
        self.card = CreditCard(name='Visa', payment_account_id=self.account.id, balance=0,
            balance_as_of=date.today(), statement_close_day=15, payment_due_day=28, credit_limit=3500)
        db.session.add_all([self.bill, self.card]); db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def test_pause_reactivation_preserves_past_and_skips_paused_dates(self):
        with patch('src.routes.date') as clock:
            clock.today.return_value = date(2026,10,10)
            self.client.post(f'/bills/{self.bill.id}/active', data={'action':'deactivate'})
            self.assertFalse(self.bill.is_active)
            self.assertEqual(bill_dates(self.bill,date(2026,9,1),date(2026,12,31)),[date(2026,9,20)])
            clock.today.return_value = date(2026,11,10)
            self.client.post(f'/bills/{self.bill.id}/active', data={'action':'activate'})
        self.assertEqual(bill_dates(self.bill,date(2026,9,1),date(2026,12,31)),
                         [date(2026,9,20),date(2026,11,20),date(2026,12,20)])
        self.assertEqual(self.client.post(f'/bills/{self.bill.id}/active',data={'action':'bad'}).status_code,400)

    def test_bill_save_stays_and_failed_save_does_not_overwrite(self):
        form=dict(name='Internet',owner='Test',amount='40',frequency='monthly',due_day='20',payment_method=f'account:{self.account.id}',save_action='stay')
        response=self.client.post(f'/bills/{self.bill.id}',data=form)
        self.assertTrue(response.location.endswith(f'/bills/{self.bill.id}'))
        form['amount']='-10'
        response=self.client.post(f'/bills/{self.bill.id}',data=form)
        self.assertTrue(response.location.endswith(f'/bills/{self.bill.id}'))
        self.assertEqual(self.bill.amount,Decimal('40'))
        form.update(amount='45',save_action='exit')
        self.assertTrue(self.client.post(f'/bills/{self.bill.id}',data=form).location.endswith('/bills'))

    def test_card_save_actions_and_dashboard_displays(self):
        form=dict(name='Visa',payment_account_id=str(self.account.id),balance='0',balance_as_of=date.today().isoformat(),statement_close_day='15',payment_due_day='28',minimum_payment='0',extra_payment='0',credit_limit='3500',save_action='stay')
        response=self.client.post(f'/credit-cards/{self.card.id}/edit',data=form)
        self.assertTrue(response.location.endswith(f'/credit-cards/{self.card.id}/edit'))
        form['save_action']='exit'
        self.assertTrue(self.client.post(f'/credit-cards/{self.card.id}/edit',data=form).location.endswith('/credit-cards'))
        self.card.is_active=False; db.session.commit()
        html=self.client.get('/').get_data(as_text=True)
        self.assertIn('$3,500.00',html); self.assertIn('Inactive',html)

    def test_migration_existing_bill_defaults_active_and_round_trip(self):
        bill_id=self.bill.id
        db.session.remove()
        with db.engine.begin() as conn:
            conn.execute(text('DROP TABLE bill_pauses'))
            conn.execute(text('ALTER TABLE bills DROP COLUMN is_active'))
            conn.execute(text('ALTER TABLE bills DROP COLUMN inactive_from'))
        stamp(revision='c5d5a9b2e781')
        upgrade(revision='d7e8f901ab23')
        self.assertTrue(db.session.get(Bill,bill_id).is_active)
        self.assertEqual(db.session.get(Bill,bill_id).amount,Decimal('30'))
        db.session.remove(); downgrade(revision='c5d5a9b2e781')
        self.assertNotIn('is_active',{c['name'] for c in inspect(db.engine).get_columns('bills')})
        upgrade(revision='d7e8f901ab23')
        self.assertTrue(db.session.get(Bill,bill_id).is_active)
