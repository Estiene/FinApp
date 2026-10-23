"""Historical captures, actual observations, Early Pay and issue #4 review."""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from flask_migrate import Migrate, stamp, upgrade, downgrade
from sqlalchemy import text
from src.models import (db, Account, Income, Bill, CreditCard,
    AccountBalanceObservation, AccountForecastSnapshot, AccountForecastPoint)
from src.routes import bp
from src.utils.dashboard import early_pay_date, income_dates, nominal_income_dates, build_dashboard_data
from src.utils.balance_history import capture_forecast
from src.utils.cash_flow_projection import daily_account_projection

class EarlyPayMapping(unittest.TestCase):
    def test_exact_weekday_table(self):
        monday = date(2026,10,26)
        expected_one = [date(2026,10,23), date(2026,10,26), date(2026,10,27), date(2026,10,28), date(2026,10,29), date(2026,10,30), date(2026,10,30)]
        expected_two = [date(2026,10,23), date(2026,10,26), date(2026,10,26), date(2026,10,27), date(2026,10,28), date(2026,10,30), date(2026,10,30)]
        for offset in range(7):
            nominal=monday+timedelta(days=offset)
            self.assertEqual(early_pay_date(nominal,0),nominal)
            self.assertEqual(early_pay_date(nominal,1),expected_one[offset])
            self.assertEqual(early_pay_date(nominal,2),expected_two[offset])
        with self.assertRaises(ValueError): early_pay_date(monday,3)

    def test_month_year_edges_and_same_day_distinct_deposits(self):
        account=SimpleNamespace(early_pay_days=2)
        for frequency in ('weekly','biweekly','monthly'):
            income=SimpleNamespace(account=account,frequency=frequency,next_pay=date(2027,1,1))
            self.assertEqual(income_dates(income,date(2026,12,1),date(2026,12,31)),[date(2026,12,30)])
            self.assertNotIn(date(2027,1,1),income_dates(income,date(2027,1,1),date(2027,1,2)))
            self.assertEqual(income.next_pay,date(2027,1,1))
        income=SimpleNamespace(account=account,frequency='twice_monthly',day_of_month_1=7,day_of_month_2=8)
        self.assertEqual(income_dates(income,date(2026,11,1),date(2026,11,30)),[date(2026,11,6),date(2026,11,6)])
        account.early_pay_days=0
        self.assertEqual(income_dates(income,date(2026,11,1),date(2026,11,30)),nominal_income_dates(income,date(2026,11,1),date(2026,11,30)))
        # A bank holiday is intentionally not adjusted.
        self.assertEqual(early_pay_date(date(2026,12,26),1),date(2026,12,25))

class HistoryRoutes(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__,template_folder='../src/templates')
        self.app.config.update(TESTING=True,SECRET_KEY='test',SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app);Migrate(self.app,db);self.app.register_blueprint(bp)
        self.ctx=self.app.app_context();self.ctx.push();db.create_all()
        self.a=Account(name='A',starting_balance=100,balance_as_of=date(2026,10,22))
        self.b=Account(name='B',starting_balance=50,balance_as_of=date(2026,10,22))
        db.session.add_all([self.a,self.b]);db.session.flush()
        self.income=Income(name='Salary',amount=200,frequency='monthly',next_pay=date(2026,11,1),account_id=self.a.id)
        db.session.add(self.income);db.session.commit();self.client=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop()

    def test_actual_saves_are_retained_and_corrections_are_explicit(self):
        path=f'/accounts/{self.a.id}/balance'
        for amount in ('100.00','150.00'):
            self.client.post(path,data={'starting_balance':amount,'balance_as_of':'2026-10-22'})
        self.assertEqual(AccountBalanceObservation.query.count(),2)
        before=AccountBalanceObservation.query.count()
        self.client.post(path,data={'starting_balance':'NaN','balance_as_of':'2026-10-22'})
        self.assertEqual(AccountBalanceObservation.query.count(),before)
        with patch('src.routes.render_template',return_value='history') as render:
            self.client.get(f'/balance-history?account_id={self.a.id}&from=2026-10-01&to=2026-11-30')
        observations=render.call_args.kwargs['observations']
        self.assertEqual(len(observations),1);self.assertEqual(observations[0].balance,Decimal('150'))

    def test_forecast_values_do_not_change_after_live_inputs_change(self):
        first=capture_forecast(self.a,[],date(2026,10,23),30)
        db.session.add(first);db.session.commit()
        frozen=[(p.balance_date,p.balance) for p in first.points]
        self.income.amount=999;self.a.starting_balance=777;self.a.early_pay_days=2
        db.session.commit();db.session.expire_all()
        self.assertEqual([(p.balance_date,p.balance) for p in db.session.get(AccountForecastSnapshot,first.id).points],frozen)
        self.assertEqual(len(frozen),31)
        later=capture_forecast(self.a,[],date(2026,10,23),30)
        self.assertNotEqual(later.points[-1].balance,first.points[-1].balance)
        self.assertEqual(self.client.post(f'/accounts/{self.a.id}/forecasts',data={'horizon':'999'}).status_code,302)
        self.assertEqual(AccountForecastSnapshot.query.count(),1)

    def test_history_empty_and_selection_do_not_write_or_leak_other_accounts(self):
        other=capture_forecast(self.b,[],date(2026,10,23),30);db.session.add(other);db.session.commit()
        html=self.client.get(f'/balance-history?account_id={self.a.id}&forecast_id={other.id}&selection=1&from=2026-10-01&to=2026-12-31').get_data(as_text=True)
        self.assertIn('No saved forecasts',html)
        self.assertNotIn(f'Saved forecast #{other.id}',html)
        self.assertEqual(AccountForecastSnapshot.query.count(),1)
        response=self.client.post(f'/accounts/{self.a.id}/forecasts',data={'horizon':'30'},follow_redirects=True)
        self.assertIn(b'<svg',response.data)
        self.assertEqual(AccountForecastSnapshot.query.count(),2)
        self.assertEqual(self.client.get('/balance-history?from=bad&to=bad').status_code,200)

    def test_early_pay_validation_and_cross_month_report_dashboard_consistency(self):
        path=f'/accounts/{self.a.id}/early-pay'
        for value in ('-1','3','oops'):
            self.client.post(path,data={'early_pay_days':value})
            self.assertEqual(self.a.early_pay_days,0)
        self.client.post(path,data={'early_pay_days':'2'})
        # Sunday Nov 1 deposits Friday Oct 30; nominal schedule remains Nov 1.
        self.assertEqual(self.income.next_pay,date(2026,11,1))
        with patch('src.routes.render_template',return_value='report') as render:
            self.client.get('/report?year=2026&month=10')
        section={s['account'].id:s for s in render.call_args.kwargs['report_data']}[self.a.id]
        self.assertEqual(section['totals']['income'],200)
        rows=daily_account_projection(self.a,date(2026,10,23),date(2026,10,31))
        self.assertEqual(rows[-1]['balance'],Decimal('300'))
        forecast=capture_forecast(self.a,[],date(2026,10,23),30)
        self.assertEqual(next(p.balance for p in forecast.points if p.balance_date==date(2026,10,30)),Decimal('300'))
        self.assertEqual(build_dashboard_data([self.a],today=date(2026,10,30))['account_summaries'][0]['projected_balance'],Decimal('300'))

    def test_issue4_monthly_totals_separate_real_cash_out_from_card_charges(self):
        self.income.amount=100
        db.session.add(Income(name='B income',amount=200,frequency='monthly',next_pay=date(2026,11,5),account_id=self.b.id))
        db.session.add(Bill(name='A bill',owner='Test',amount=30,due_day=10,account_id=self.a.id))
        db.session.add(Bill(name='B bill',owner='Test',amount=50,due_day=10,account_id=self.b.id))
        card=CreditCard(name='Card',payment_account_id=self.a.id,balance=0,balance_as_of=date(2026,10,1),statement_close_day=15,payment_due_day=28,minimum_payment=0,extra_payment=0)
        db.session.add(card);db.session.flush()
        db.session.add(Bill(name='Card bill',owner='Test',amount=40,due_day=5,account_id=self.a.id,credit_card_id=card.id));db.session.commit()
        with patch('src.routes.render_template',return_value='report') as render:
            self.client.get('/report?year=2026&month=11')
        sections={s['account'].id:s for s in render.call_args.kwargs['report_data']}
        a,b=sections[self.a.id]['totals'],sections[self.b.id]['totals']
        self.assertEqual(a,dict(income=100,bills=30,credit_card_payments=40,credit_card_charges=40,net=30))
        self.assertEqual(b,dict(income=200,bills=50,credit_card_payments=0,credit_card_charges=0,net=150))

    def test_history_migration_seeds_only_known_balance_and_is_reversible(self):
        account_id=self.a.id
        db.session.remove()
        with db.engine.begin() as connection:
            for table in ('account_forecast_points','account_forecast_snapshots','account_balance_observations'):
                connection.execute(text('DROP TABLE '+table))
            # SQLite cannot drop a column referenced by a CHECK constraint; rebuild the old table.
            connection.execute(text('CREATE TABLE accounts_old (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE, starting_balance NUMERIC(12,2) NOT NULL, balance_as_of DATE NOT NULL)'))
            connection.execute(text('INSERT INTO accounts_old SELECT id,name,starting_balance,balance_as_of FROM accounts'))
            connection.execute(text('DROP TABLE accounts'))
            connection.execute(text('ALTER TABLE accounts_old RENAME TO accounts'))
        stamp(revision='d7e8f901ab23');upgrade(revision='e8f901ab24cd')
        account=db.session.get(Account,account_id)
        self.assertEqual(account.early_pay_days,0)
        observation=AccountBalanceObservation.query.filter_by(account_id=account_id).one()
        self.assertEqual(observation.balance,Decimal('100'));self.assertEqual(observation.balance_date,date(2026,10,22))
        self.assertIsNone(observation.recorded_at);self.assertEqual(observation.source,'imported')
        self.assertEqual(AccountForecastSnapshot.query.count(),0)
        db.session.remove();downgrade(revision='d7e8f901ab23');upgrade(revision='e8f901ab24cd')
        self.assertEqual(AccountBalanceObservation.query.count(),2)
