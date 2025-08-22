# app/src/app.py

from flask import Flask
from .models import db
from .routes import bp
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
app.register_blueprint(bp)

# Immediately create tables when the app object is built
with app.app_context():
    db.create_all()

