import os
from flask import Flask
from flask_migrate import Migrate
from .models import db, Account  # Import at least one model to check table existence
from .routes import bp as main_bp

def create_app():
    """Application factory: configure app, extensions, and blueprints."""
    app = Flask(__name__)

    # 1. Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # 2. Initialize extensions
    db.init_app(app)
    Migrate(app, db)

    # 3. Auto-create tables if missing
    with app.app_context():
        if not db.inspect(db.engine).has_table("account"):
            db.create_all()
            print("✅ Database tables created.")

    # 4. Register blueprints
    app.register_blueprint(main_bp)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
