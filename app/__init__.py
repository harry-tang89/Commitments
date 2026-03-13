"""
Flask application factory / initialization module.
"""
from flask import Flask, jsonify, redirect, request, url_for
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


@login.unauthorized_handler
def handle_unauthorized():
    if request.path.startswith("/api/mobile/"):
        return jsonify({"ok": False, "message": "Authentication required."}), 401
    return redirect(url_for(login.login_view, next=request.url))


from app import routes, models  # noqa: E402
