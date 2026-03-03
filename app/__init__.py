"""
Flask application factory / initialization module.
"""
from flask import Flask
from app.config import AppConfig
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

app = Flask(__name__)
app.config.from_object(AppConfig)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = "login"

from app import routes, models  # noqa: E402
