# -*- coding: utf-8 -*-
"""
This file contains the application factory, create_app(), which is responsible
for initializing the Flask application, its extensions, and its blueprints.
Version: 2.0 - Complete with Email & Scheduler Support
"""

# --- Standard Library Imports ---
import os
import logging
from datetime import timedelta

# --- Third-Party Library Imports ---
import click
from flask import Flask, g, session, send_from_directory, render_template
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

# --- Local Application Imports ---
from .extensions import db, mail, scheduler, migrate, login_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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

    # --- Environment Configuration ---
    from dotenv import load_dotenv
    load_dotenv()

    # --- Database Configuration ---
    # app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    #     'DATABASE_URL', 
    #     f"sqlite:///{os.path.join(project_root, 'attendance.db')}"
    # )
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    #     'pool_pre_ping': True,
    #     'pool_recycle': 3600,
    #     'connect_args': {'timeout': 15}
    # }
    
    # # --- Secret Key Configuration ---
    # app.config['SECRET_KEY'] = os.environ.get(
    #     'SECRET_KEY', 
    #     'a-very-secret-and-long-random-key-for-production'
    # )

    # --- Database Configuration ---
    database_url = os.environ.get('DATABASE_URL')

    # ✅ Render adds "postgres://" instead of "postgresql://"
    # SQLAlchemy needs it corrected
    if database_url and database_url.startswith("postgres://"):
     database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f"sqlite:///{os.path.join(project_root, 'attendance.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
     # NOTE: 'connect_args' should not be used for PostgreSQL
        **({'connect_args': {'timeout': 15}} if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI'] else {})
    }

    
    # --- Session Configuration ---
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # --- File Upload Configuration ---
    app.config['UPLOAD_FOLDER'] = os.path.join(static_dir, 'uploads')
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'csv'}
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # --- Development Settings ---
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable static file caching in development
    
    # --- Mail Configuration ---
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your_app_password')
    app.config['MAIL_DEFAULT_SENDER'] = (
        'Attendly',
        os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')
    )
    
    # --- Timezone Configuration ---
    app.config['TZ'] = os.environ.get('TZ', 'Asia/Kolkata')

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
    login_manager.init_app(app)
    
    # --- Configure Login Manager ---
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '❌ Please log in to access this page.'
    login_manager.login_message_category = 'warning'

    # --- Initialize Scheduler ---
    try:
        if not scheduler.running:
            scheduler.init_app(app)
            scheduler.start()
            logger.info("✅ APScheduler started successfully")
    except Exception as e:
        logger.warning(f"⚠️ Scheduler initialization warning: {str(e)}")

    # --- Create Database Tables ---
    with app.app_context():
        try:
            db.create_all()
            logger.info("✅ Database tables created/verified")
        except Exception as e:
            logger.error(f"❌ Error creating database tables: {str(e)}")

    # --- User Loader for Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        try:
            from .models import User
            return db.session.get(User, int(user_id))
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {str(e)}")
            return None

    # --- Register Blueprints ---
    try:
        from .auth.routes import auth_bp
        from .dashboard.routes import dashboard_bp
        from .student.routes import student_bp
        from .teacher.routes import teacher_bp
        from .profile.routes import profile_bp
        from .admin.routes import admin_bp
        
        app.register_blueprint(auth_bp, url_prefix='/auth') 
        app.register_blueprint(dashboard_bp)
        app.register_blueprint(student_bp, url_prefix='/student')
        app.register_blueprint(teacher_bp, url_prefix='/teacher')
        app.register_blueprint(profile_bp, url_prefix='/profile')
        app.register_blueprint(admin_bp, url_prefix='/admin')
        
        logger.info("✅ All blueprints registered successfully")
    except ImportError as e:
        logger.error(f"❌ Error importing blueprints: {str(e)}")
        raise

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
        logger.warning(f"404 error: {error}")
        try:
            return render_template('errors/404.html'), 404
        except Exception:
            return '<h1>404 - Page Not Found</h1>', 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors gracefully"""
        db.session.rollback()
        logger.error(f"500 Error: {str(error)}", exc_info=True)
        try:
            return render_template('errors/500.html'), 500
        except Exception:
            return '<h1>500 - Internal Server Error</h1>', 500

    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 forbidden errors"""
        logger.warning(f"403 Forbidden error: {error}")
        try:
            return render_template('errors/403.html'), 403
        except Exception:
            return '<h1>403 - Access Forbidden</h1>', 403

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Catch-all error handler for debugging"""
        logger.error(f"Unhandled exception: {str(error)}", exc_info=True)
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
            logger.error(f"Error loading user: {str(e)}", exc_info=True)
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
        try:
            db.drop_all()
            db.create_all()
            
            default_subjects = [
                'Mathematics', 'English', 'Science', 
                'History', 'Geography', 'Computer Science',
                'Physical Education', 'Arts'
            ]
            
            for subject_name in default_subjects:
                if not Subject.query.filter_by(name=subject_name).first():
                    subject = Subject(name=subject_name)
                    db.session.add(subject)
            
            db.session.commit()
            click.echo('✅ Database Initialized Successfully.')
            click.echo(f'📚 Created {len(default_subjects)} default subjects.')
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            click.echo(f'❌ Error: {str(e)}')

    @app.cli.command('test-email')
    @click.argument('recipient')
    def test_email_command(recipient):
        """Sends a test email to the specified recipient address."""
        try:
            from .email import send_test_email
            if send_test_email(recipient):
                click.echo(f"✅ Test email sent to {recipient}. Check inbox!")
            else:
                click.echo("❌ Failed to send email. Check logs for details.")
        except Exception as e:
            logger.error(f"Test email error: {str(e)}")
            click.echo(f"❌ Error: {str(e)}")

    @app.cli.command('populate-attendly-ids')
    def populate_attendly_ids_command():
        """Populate attendly_id for all existing users."""
        try:
            from .models import User
            
            users = User.query.filter(
                (User.attendly_id == None) | (User.attendly_id == '')
            ).all()
            
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
        except Exception as e:
            logger.error(f"Error populating attendly_ids: {str(e)}")
            click.echo(f"❌ Error: {str(e)}")

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.argument('email')
    @click.password_option()
    def create_admin_command(username, email, password):
        """Create an admin user."""
        try:
            from .models import User
            from werkzeug.security import generate_password_hash
            
            if User.query.filter_by(username=username).first():
                click.echo(f"❌ User '{username}' already exists.")
                return
            
            admin = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role='admin'
            )
            
            db.session.add(admin)
            db.session.commit()
            click.echo(f"✅ Admin user '{username}' created successfully!")
        except Exception as e:
            logger.error(f"Error creating admin: {str(e)}")
            click.echo(f"❌ Error: {str(e)}")

    # --- Log Startup Info ---
    logger.info("=" * 70)
    logger.info("🚀 ATTENDLY APPLICATION STARTED")
    logger.info("=" * 70)
    logger.info(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    logger.info(f"Mail Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
    logger.info(f"Debug Mode: {app.config.get('DEBUG', False)}")
    logger.info(f"Upload Folder: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"Scheduler Running: {scheduler.running}")
    logger.info("=" * 70)

    return app
