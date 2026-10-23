import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from datetime import date
from src.models import db,Account,Bill,CreditCard,Income
from src.routes import bp
app=Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1] / 'src/templates'))
app.config.update(SECRET_KEY='qa',SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
db.init_app(app);app.register_blueprint(bp)
with app.app_context():
 db.create_all();a=Account(name='QA Checking');db.session.add(a);db.session.flush()
 db.session.add(Bill(name='Internet QA',owner='QA',amount=30,due_day=20,account_id=a.id))
 db.session.add(CreditCard(name='QA Visa',payment_account_id=a.id,balance=0,balance_as_of=date.today(),statement_close_day=15,payment_due_day=28,credit_limit=3500,is_active=False))
 db.session.add(Income(name="Early Pay QA",amount=200,frequency="weekly",next_pay=date(2027,1,1),account_id=a.id))
 db.session.commit()
app.run(port=5088)
