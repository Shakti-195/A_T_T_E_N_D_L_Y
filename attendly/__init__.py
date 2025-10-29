# -*- coding: utf-8 -*-
"""
This file contains the application factory, create_app(), which is responsible
for initializing the Flask application, its extensions, and its blueprints.
"""

# --- Standard Library Imports ---
import os
from datetime import timedelta

# --- Third-Party Library Imports ---
import click
from flask import Flask, g, session, send_from_directory, render_template
from fpdf import FPDF
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

# --- Local Application Imports ---
from .extensions import db, mail, scheduler, migrate, login_manager  # <-- ADD login_manager
from .utils import email_reports_job

def create_app():
    """
    Create and configure an instance of the Flask application.
    """
    # --- Robust Path Configuration ---
    basedir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.dirname(basedir)
    
    template_dir = os.path.join(project_root, 'templates')
    static_dir = os.path.join(project_root, 'static')

    app = Flask(__name__.split('.')[0],
                template_folder=template_dir,
                static_folder=static_dir)

    # --- Configuration ---
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(project_root, 'attendance.db')}")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-and-long-random-key-for-production')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
    app.config['UPLOAD_FOLDER'] = os.path.join(static_dir, 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # --- Mail Configuration ---
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'scena7800@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'amiskslxnpjqwqga')
    app.config['MAIL_DEFAULT_SENDER'] = ('Attendly', app.config['MAIL_USERNAME'])

    # --- Scheduler Configuration ---
    app.config['SCHEDULER_JOBSTORES'] = {
        'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
    }
    app.config['SCHEDULER_EXECUTORS'] = {
        'default': ThreadPoolExecutor(20)
    }
    app.config['SCHEDULER_API_ENABLED'] = True
    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Kolkata'
    
    # --- Initialize Extensions ---
    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)  # <-- INITIALIZE LOGIN MANAGER
    
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()

    # --- User Loader for Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        from .models import User
        return db.session.get(User, int(user_id))

    # --- Register Blueprints ---
    from .auth.routes import auth_bp
    from .dashboard.routes import dashboard_bp
    from .student.routes import student_bp
    from .profile.routes import profile_bp
    from .admin.routes import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # --- Favicon Route (FIX FOR 404 ERROR) ---
    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon to prevent 404 errors"""
        try:
            return send_from_directory(
                os.path.join(app.root_path, 'static'),
                'favicon.ico',
                mimetype='image/vnd.microsoft.icon'
            )
        except Exception:
            # If favicon doesn't exist, return empty response
            return '', 204

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors gracefully"""
        try:
            return render_template('errors/404.html'), 404
        except Exception:
            return '<h1>404 - Page Not Found</h1>', 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors gracefully"""
        db.session.rollback()
        app.logger.error(f"500 Error: {str(error)}")
        try:
            return render_template('errors/500.html'), 500
        except Exception:
            return '<h1>500 - Internal Server Error</h1>', 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Catch-all error handler for debugging"""
        app.logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
        db.session.rollback()
        
        # In development, show the actual error
        if app.debug:
            raise error
        
        try:
            return render_template('errors/500.html'), 500
        except Exception:
            return f'<h1>500 - Internal Server Error</h1><p>{str(error)}</p>', 500

    # --- Request Hooks ---
    @app.before_request
    def load_logged_in_user():
        """Load current user and role into g object"""
        from .models import User
        user_id = session.get('user_id')
        
        try:
            g.user = db.session.get(User, user_id) if user_id else None
            
            if g.user:
                # Handle admin role switching
                if 'view_as' in session and g.user.role == 'admin':
                    g.role = session['view_as']
                else:
                    g.role = g.user.role
                    session['role'] = g.user.role 
            else:
                g.role = None
        except Exception as e:
            app.logger.error(f"Error loading user: {str(e)}", exc_info=True)
            g.user = None
            g.role = None
            session.clear()

    @app.context_processor
    def inject_g_role():
        """Injects the g.role variable into the template context."""
        return dict(
            g_role=getattr(g, 'role', None),
            g_user=getattr(g, 'user', None)
        )

    # --- CLI Commands ---
    @app.cli.command('init-db')
    def init_db_command():
        """Drops and recreates all tables, and creates default subjects."""
        from .models import Subject
        db.drop_all()
        db.create_all()
        
        default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
        for subject_name in default_subjects:
            if not Subject.query.filter_by(name=subject_name).first():
                subject = Subject(name=subject_name)
                db.session.add(subject)
        
        db.session.commit()
        click.echo('✅ Database Initialized Successfully.')

    @app.cli.command('test-email')
    @click.argument('recipient')
    def test_email_command(recipient):
        """Sends a test email to the specified recipient address."""
        from .utils import send_email
        subject = "Attendly Mail Setup Test"
        body = "Congratulations! If you received this email, your Flask-Mail configuration is working correctly."
        if send_email(subject, [recipient], body):
            click.echo(f"✅ Attempted to send a test email to {recipient}. Check their inbox.")
        else:
            click.echo("❌ Failed to send email. Check the terminal for a detailed error log.")

    @app.cli.command('populate-attendly-ids')
    def populate_attendly_ids_command():
        """Populate attendly_id for all existing users."""
        from .models import User
        
        users = User.query.filter_by(attendly_id=None).all()
        
        if not users:
            click.echo('✅ All users already have attendly_id assigned.')
            return
        
        for user in users:
            user.attendly_id = f"ATD{user.id:06d}"
        
        db.session.commit()
        click.echo(f'✅ Successfully updated {len(users)} users with attendly_id')
        
        if users:
            click.echo('\n📋 Examples:')
            for user in users[:5]:
                click.echo(f'  • {user.username}: {user.attendly_id}')

    return app
