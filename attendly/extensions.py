# -*- coding: utf-8 -*-
"""
This file is used to instantiate extension objects.
By keeping them in a separate file, we avoid circular import issues.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_apscheduler import APScheduler
from flask_migrate import Migrate
from flask_login import LoginManager  # <-- Import LoginManager

db = SQLAlchemy()
mail = Mail()
scheduler = APScheduler()
migrate = Migrate()
login_manager = LoginManager()  # <-- Instantiate LoginManager here

# Optional configuration for login_manager defaults:
login_manager.login_view = 'auth.login'                # Endpoint to redirect unauthorized users
login_manager.login_message_category = 'info'          # Flash message styling
