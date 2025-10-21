# # -*- coding: utf-8 -*-

# # --- Standard Library Imports ---
# import os
# import uuid
# import random
# import string
# import base64
# import pytz
# import csv
# import time
# from io import BytesIO, StringIO
# from datetime import datetime, timedelta, date
# from functools import wraps
# import click

# # --- Third-Party Library Imports ---
# from flask import (Flask, render_template, request, redirect, url_for, flash,
#                    session, jsonify, g, Response, send_file)
# from flask_sqlalchemy import SQLAlchemy
# from sqlalchemy import func, case, extract, desc
# from sqlalchemy.orm import joinedload
# from flask_login import login_required
# from flask_mail import Mail, Message
# from flask_apscheduler import APScheduler
# from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
# from apscheduler.executors.pool import ThreadPoolExecutor
# from werkzeug.security import generate_password_hash, check_password_hash
# from werkzeug.utils import secure_filename
# import qrcode
# from fpdf import FPDF

# # --- Local Application Imports ---
# # (Agar aapne alag files banayi hain jaise models.py, toh unke imports yahan aayenge)
# # from .models import User, Student, etc...
# # --- App Initialization & Configuration ---
# app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-and-long-random-key-for-production')
# app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
# app.config['UPLOAD_FOLDER'] = 'static/uploads'
# app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
# os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# # --- Mail Configuration ---
# app.config['MAIL_SERVER'] = 'smtp.gmail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'scena7800@gmail.com')
# app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'amiskslxnpjqwqga')
# app.config['MAIL_DEFAULT_SENDER'] = ('Attendance Wand', app.config['MAIL_USERNAME'])

# # --- Extensions & Global Variables ---
# db = SQLAlchemy(app)
# mail = Mail(app)
# scheduler = APScheduler()
# IST = pytz.timezone('Asia/Kolkata')

# # --- SCHEDULER CONFIGURATION ---
# app.config['SCHEDULER_JOBSTORES'] = {
#     'default': SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
# }
# app.config['SCHEDULER_EXECUTORS'] = {
#     'default': ThreadPoolExecutor(20)
# }
# app.config['SCHEDULER_API_ENABLED'] = True
# app.config['SCHEDULER_TIMEZONE'] = 'Asia/Kolkata' # <-- ADD THIS LINE
# # --- Helper Functions ---
# def get_current_ist():
#     return datetime.now(IST)

# def make_timezone_aware(dt):
#     if dt and dt.tzinfo is None:
#         return IST.localize(dt)
#     return dt

# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# def generate_unique_code():
#     while True:
#         code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
#         if not Institution.query.filter_by(institution_code=code).first():
#             return code

# def get_attendance_leaderboard(institution_id, class_id=None):
#     subquery = db.session.query(
#         Attendance.student_id,
#         func.count(Attendance.id).label('total_days'),
#         func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present_days')
#     ).join(Student).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)

#     if class_id:
#         subquery = subquery.filter(Student.class_batch_id == class_id)
    
#     subquery = subquery.group_by(Attendance.student_id).subquery()

#     leaderboard_query = db.session.query(
#         Student.name,
#         ((subquery.c.present_days * 100.0) / subquery.c.total_days).label('percentage')
#     ).join(subquery, Student.id == subquery.c.student_id)

#     leaderboard = leaderboard_query.order_by(desc('percentage')).limit(3).all()
#     return [{'name': name, 'percentage': round(p, 1)} for name, p in leaderboard]

# def get_pending_leaves(institution_id, class_id=None):
#     leaves_query = MedicalLeave.query.join(Student).join(ClassBatch)\
#     .filter(ClassBatch.institution_id == institution_id)

#     # Only get requests that are pending AND have not expired yet
#     leaves_query = leaves_query.filter(
#                  MedicalLeave.status == 'pending',
#                  MedicalLeave.expiry_time > get_current_ist()
#              )

#     if class_id:
#         leaves_query = leaves_query.filter(Student.class_batch_id == class_id)
        
#     leaves = leaves_query.order_by(desc(MedicalLeave.created_at)).limit(3).all()
#     return [{'student_name': leave.student.name, 'start_date': leave.start_date.strftime('%d/%m/%Y'), 'reason': leave.reason} for leave in leaves]

# def get_ai_insights(institution_id, class_id=None):
#     insights = {}
#     subquery = db.session.query(
#         Attendance.student_id,
#         (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
#     ).join(Student).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)

#     if class_id:
#         subquery = subquery.filter(Student.class_batch_id == class_id)
        
#     subquery = subquery.group_by(Attendance.student_id).subquery()
    
#     at_risk_count = db.session.query(func.count(subquery.c.student_id)).filter(subquery.c.percentage.between(75, 80)).scalar()
#     insights['at_risk_count'] = at_risk_count
#     insights['anomaly_message'] = None
#     return insights

# def get_live_chart_data(institution_id, class_id=None):
#     today = get_current_ist().date()
#     labels, values = [], []
    
#     total_students_query = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
#     if class_id:
#         total_students_query = total_students_query.filter(Student.class_batch_id == class_id)
#     total_students = total_students_query.count()

#     for i in range(6, -1, -1):
#         day = today - timedelta(days=i)
#         labels.append(day.strftime('%a'))
        
#         present_query = db.session.query(func.count(Attendance.id)).join(Student).join(ClassBatch).filter(
#             ClassBatch.institution_id == institution_id,
#             Attendance.date == day,
#             Attendance.status == 'present'
#         )
#         if class_id:
#             present_query = present_query.filter(Student.class_batch_id == class_id)
        
#         present_count = present_query.scalar() or 0
#         percentage = (present_count / total_students * 100) if total_students > 0 else 0
#         values.append(round(percentage, 1))
        
#     return {'labels': labels, 'values': values}

# # YEH NAYA HELPER FUNCTION ADD KAREIN
# def get_dashboard_statistics(institution_id, date, class_id=None):
#     """
#     Ek central function jo dashboard ke stats theek se calculate karta hai.
#     """
#     # Step 1: Filter ke hisaab se sabhi relevant students ke ID's nikaalo
#     students_query = db.session.query(Student.id).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
#     if class_id:
#         students_query = students_query.filter(Student.class_batch_id == class_id)
    
#     all_student_ids = [s_id for s_id, in students_query.all()]
#     total_students = len(all_student_ids)

#     # Step 2: Ab, in students mein se 'present' kaun hai, unka count nikaalo
#     present_today_count = 0
#     if total_students > 0:
#         present_student_ids_query = db.session.query(Attendance.student_id)\
#             .filter(
#                 Attendance.student_id.in_(all_student_ids),
#                 Attendance.date == date,
#                 Attendance.status == 'present'
#             ).distinct() # Use distinct to count each student once
#         present_today_count = present_student_ids_query.count()

#     # Step 3: Sahi calculation return karo
#     return {
#         "total": total_students,
#         "present": present_today_count
#     }



# def get_live_student_lists(institution_id, date, class_id=None):
#     # Step 1: Ek hi query mein sabhi students aur unki class ki details fetch karo.
#     # joinedload se performance behtar hoti hai.
#     all_students_query = Student.query.options(joinedload(Student.class_batch))\
#         .join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
#     if class_id:
#         all_students_query = all_students_query.filter(Student.class_batch_id == class_id)
    
#     all_students = all_students_query.order_by(Student.name).all()
#     all_student_ids = [s.id for s in all_students]

#     # Step 2: Aaj present students ke ID's nikaalo
#     present_student_ids = set() # Use a set for faster lookups
#     if all_student_ids:
#         present_query = db.session.query(Attendance.student_id).filter(
#             Attendance.student_id.in_(all_student_ids),
#             Attendance.date == date,
#             Attendance.status == 'present'
#         )
#         present_student_ids = {row[0] for row in present_query.all()}

#     # Step 3: Ab har list ke liye detailed dictionaries banao
#     all_list = []
#     present_list = []
#     absent_list = []

#     for student in all_students:
#         student_details = {
#             'id': student.id,
#             'name': student.name,
#             'student_id': student.student_id,
#             'class_name': student.class_batch.name if student.class_batch else 'N/A'
#         }
#         all_list.append(student_details)
        
#         if student.id in present_student_ids:
#             present_list.append(student_details)
#         else:
#             absent_list.append(student_details)

#     return {
#         "all": all_list,
#         "present": present_list,
#         "absent": absent_list
#     }

# # --- Database Models (including all necessary tables) ---
# teacher_classes = db.Table('teacher_classes',
#     db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
#     db.Column('class_batch_id', db.Integer, db.ForeignKey('class_batch.id'), primary_key=True)
# )

# class User(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80), nullable=False)
#     email = db.Column(db.String(120), nullable=True)
#     password_hash = db.Column(db.String(200), nullable=False)
#     role = db.Column(db.String(20), nullable=False, default='student')
#     created_at = db.Column(db.DateTime, default=get_current_ist)
#     student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
#     institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=True)
#     email_verified = db.Column(db.Boolean, default=False)
#     otp = db.Column(db.String(6), nullable=True)
#     otp_expiry = db.Column(db.DateTime, nullable=True)
#     password_reset_token = db.Column(db.String(100), nullable=True, unique=True)
#     reset_token_expiry = db.Column(db.DateTime, nullable=True)
#     __table_args__ = (db.UniqueConstraint('username', 'institution_id'),)

#     def set_password(self, password): 
#         self.password_hash = generate_password_hash(password)
        
#     def check_password(self, password): 
#         return check_password_hash(self.password_hash, password)

# class Institution(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(150), nullable=False)
#     type = db.Column(db.String(50), nullable=False)
#     institution_code = db.Column(db.String(10), unique=True, nullable=False)
#     users = db.relationship('User', backref='institution', lazy='dynamic')
#     class_batches = db.relationship('ClassBatch', backref='institution', lazy='dynamic')

# class ClassBatch(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=False)
#     students = db.relationship('Student', backref='class_batch', lazy='dynamic')
#     teachers = db.relationship('User', secondary=teacher_classes, backref=db.backref('taught_classes', lazy='subquery'))

# class Subject(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     attendances = db.relationship('Attendance', backref='subject', lazy='dynamic')

# class Student(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     student_id = db.Column(db.String(20), nullable=False)
#     email = db.Column(db.String(120), nullable=True)
#     photo = db.Column(db.String(100), nullable=False, default='default.png')
#     class_batch_id = db.Column(db.Integer, db.ForeignKey('class_batch.id'), nullable=True)
#     created_at = db.Column(db.DateTime, default=get_current_ist)
#     user = db.relationship('User', backref='student_profile', uselist=False, cascade="all, delete-orphan")
#     attendances = db.relationship('Attendance', backref='student', lazy='dynamic', cascade="all, delete-orphan")
#     medical_leaves = db.relationship('MedicalLeave', backref='student', lazy='dynamic', cascade="all, delete-orphan")
#     bio = db.Column(db.Text, nullable=True)
#     linkedin_url = db.Column(db.String(200), nullable=True)
#     github_url = db.Column(db.String(200), nullable=True)
#     achievements = db.Column(db.Text, nullable=True) # Simple text for now
#     skills = db.Column(db.String(300), nullable=True) # Comma-separated skills

# class Attendance(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
#     subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
#     date = db.Column(db.Date, nullable=False)
#     status = db.Column(db.String(20), default='present')
#     marked_by = db.Column(db.String(20), default='manual')
#     created_at = db.Column(db.DateTime, default=get_current_ist)

# class QRToken(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     token = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
#     class_batch_id = db.Column(db.Integer, nullable=False)
#     subject_id = db.Column(db.Integer, nullable=False)
#     expiry_time = db.Column(db.DateTime, nullable=False)

# class MedicalLeave(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
#     start_date = db.Column(db.Date, nullable=False)
#     end_date = db.Column(db.Date, nullable=False)
#     reason = db.Column(db.Text, nullable=False)
#     status = db.Column(db.String(20), nullable=False, default='pending') # <-- Make sure this line is here
#     created_at = db.Column(db.DateTime, default=get_current_ist)
#     expiry_time = db.Column(db.DateTime, nullable=True)

# # --- Email Sending Functions ---
# def send_email(subject, recipients, body):
#     try:
#         msg = Message(subject, recipients=recipients, body=body)
#         mail.send(msg)
#         return True
#     except Exception as e:
#         app.logger.error(f"Error sending email: {e}")
#         return False

# def send_verification_email(user):
#     otp = ''.join(random.choices(string.digits, k=6))
#     user.otp = otp
#     user.otp_expiry = get_current_ist() + timedelta(minutes=10)
#     db.session.commit()
#     body = f"Hello {user.username},\n\nYour One-Time Password (OTP) is: {otp}\n\nThis is valid for 10 minutes."
#     return send_email("Verify Your Account", [user.email], body)

# def send_password_reset_email(user):
#     token = str(uuid.uuid4())
#     user.password_reset_token = token
#     user.reset_token_expiry = get_current_ist() + timedelta(hours=1)
#     db.session.commit()
#     reset_url = url_for('reset_password', token=token, _external=True)
#     body = f"Hello {user.username},\n\nClick this link to reset your password:\n{reset_url}\n\nThis link will expire in one hour."
#     return send_email("Password Reset Request", [user.email], body)

# def send_username_email(user):
#     body = f"Hello,\n\nYour username is: {user.username}"
#     return send_email("Your Username", [user.email], body)

# # --- Decorators & Hooks ---
# def login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if g.user is None:
#             session.clear()
#             flash('Your session is invalid, please log in again.', 'warning')
#             return redirect(url_for('login'))
#         return f(*args, **kwargs)
#     return decorated_function

# def admin_required(f):
#     @wraps(f)
#     @login_required
#     def decorated_function(*args, **kwargs):
#         if g.user.role != 'admin':
#             flash('You do not have permission to access this page.', 'danger')
#             return redirect(url_for('dashboard'))
#         return f(*args, **kwargs)
#     return decorated_function

# def teacher_or_admin_required(f):
#     @wraps(f)
#     @login_required
#     def decorated_function(*args, **kwargs):
#         if g.user.role not in ['admin', 'teacher']:
#             flash('You do not have permission to access this page.', 'danger')
#             return redirect(url_for('dashboard'))
#         return f(*args, **kwargs)
#     return decorated_function

# # In app.py

# @app.before_request
# def load_logged_in_user():
#     user_id = session.get('user_id')
#     g.user = db.session.get(User, user_id) if user_id else None
    
#     if g.user:
#         # This is the key change:
#         # If an admin has switched roles, use the role from the session.
#         # Otherwise, use the user's actual role from the database.
#         if 'role' in session and g.user.role == 'admin':
#             g.role = session.get('role')
#         else:
#             g.role = g.user.role
#             session['role'] = g.user.role # Ensure session is in sync
#     else:
#         g.role = None

# # --- Main & Authentication Routes ---
# @app.route('/')
# def index():
#     return redirect(url_for('dashboard') if g.user else url_for('login'))

# @app.route('/dashboard')
# @login_required
# def dashboard():
#     inst_id = g.user.institution_id
#     if not inst_id:
#         # Upar waali line ko is poore block se replace karein
#                return render_template(
#                    'dashboard.html',
#                    student_counts={"total": 0, "present": 0},
#                    all_classes=[],
#                    # Yeh saare variables add karein taaki error na aaye
#                    student_lists={"all": [], "present": [], "absent": []},
#                    chart_data={"labels": [], "values": []},
#                    leaderboard=[],
#                    pending_leaves=[],
#                    insights={"at_risk_count": 0, "anomaly_message": None},
#                    selected_class_id=None,
#                    selected_date=get_current_ist().strftime('%Y-%m-%d'),
#                    on_leave_count=0,
#                    subjects_today=[]
#                )

#     # --- Filters ---
#     selected_class_id = request.args.get('class_id', default=None, type=int)
#     selected_date_str = request.args.get('filter_date', default=get_current_ist().strftime('%Y-%m-%d'))
    
#     try:
#         selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
#     except (ValueError, TypeError):
#         selected_date = get_current_ist().date()
#         selected_date_str = selected_date.strftime('%Y-%m-%d')

#     # --- Calculations for Cards ---
#     # 1. Get all relevant student IDs
#     students_query = db.session.query(Student.id).join(ClassBatch).filter(ClassBatch.institution_id == inst_id)
#     if selected_class_id:
#         students_query = students_query.filter(Student.class_batch_id == selected_class_id)
#     all_student_ids = [s_id for s_id, in students_query.all()]
#     total_students = len(all_student_ids)

#     # 2. Get present student count
#     present_today_count = 0
#     if total_students > 0:
#         present_today_count = Attendance.query.filter(
#             Attendance.student_id.in_(all_student_ids),
#             Attendance.date == selected_date,
#             Attendance.status == 'present'
#         ).distinct(Attendance.student_id).count()

#     student_counts = {"total": total_students, "present": present_today_count}
    
#     # 3. Get students on leave count
#     on_leave_count = MedicalLeave.query.filter(
#         MedicalLeave.student_id.in_(all_student_ids),
#         MedicalLeave.start_date <= selected_date,
#         MedicalLeave.end_date >= selected_date,
#         MedicalLeave.status == 'approved' # Sirf approved leaves count karein
#     ).count()

#     # 4. Get subjects taught today
#     subjects_today_query = db.session.query(Subject.name).distinct().join(Attendance).filter(
#         Attendance.student_id.in_(all_student_ids),
#         Attendance.date == selected_date
#     )
#     subjects_today = [row[0] for row in subjects_today_query.all()]

#     # --- Baaki saara code waise hi rahega ---
#     leaderboard = get_attendance_leaderboard(inst_id, class_id=selected_class_id)
#     insights = get_ai_insights(inst_id, class_id=selected_class_id)
#     chart_data = get_live_chart_data(inst_id, class_id=selected_class_id)
#     student_lists = get_live_student_lists(inst_id, date=selected_date, class_id=selected_class_id)
#     all_classes = ClassBatch.query.filter_by(institution_id=inst_id).order_by(ClassBatch.name).all()

#     return render_template(
#         'dashboard.html',
#         student_counts=student_counts,
#         student_lists=student_lists,
#         chart_data=chart_data,
#         leaderboard=leaderboard,
#         insights=insights,
#         all_classes=all_classes,
#         selected_class_id=selected_class_id,
#         selected_date=selected_date_str,
#         # Naya data cards ke liye
#         on_leave_count=on_leave_count,
#         subjects_today=subjects_today
#     )

# @app.route('/api/dashboard-data')
# @login_required
# def api_dashboard_data():
#     try:
#         inst_id = g.user.institution_id
#         if not inst_id:
#             return jsonify({
#                 "student_counts": {"total": 0, "present": 0},
#                 "student_lists": {"all": [], "present": [], "absent": []},
#                 "chart_data": {"labels": [], "values": []}
#             })

#         # API ko a filter parameters receive karne honge
#         selected_class_id = request.args.get('class_id', default=None, type=int)
#         selected_date_str = request.args.get('date', default=get_current_ist().strftime('%Y-%m-%d'))
        
#         try:
#             selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
#         except (ValueError, TypeError):
#             selected_date = get_current_ist().date()
            
#         # BUG FIX: Yahan bhi naya, correct helper function use karein
#         student_counts = get_dashboard_statistics(inst_id, selected_date, class_id=selected_class_id)
        
#         # Baaki helper functions
#         student_lists = get_live_student_lists(inst_id, date=selected_date, class_id=selected_class_id)
#         chart_data = get_live_chart_data(inst_id, class_id=selected_class_id)

#         final_data = {
#             "student_counts": student_counts,
#             "student_lists": student_lists,
#             "chart_data": chart_data,
#         }
#         return jsonify(final_data)

#     except Exception as e:
#         app.logger.error(f"API Error in /api/dashboard-data: {e}")
#         return jsonify({"error": "Could not retrieve dashboard data."}), 500

# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     if g.user: 
#         return redirect(url_for('dashboard'))
#     if request.method == 'POST':
#         user = User.query.filter(func.lower(User.username) == func.lower(request.form.get('username'))).first()
#         if user and user.check_password(request.form.get('password')):
#             if not user.email_verified:
#                 send_verification_email(user)
#                 flash('Email not verified. A new OTP has been sent.', 'warning')
#                 return redirect(url_for('verify_email_otp', email=user.email))
#             session.permanent = True
#             session['user_id'] = user.id
#             flash(f'Welcome back, {user.username}!', 'success')
#             return redirect(url_for('dashboard'))
#         else:
#             flash('Invalid username or password.', 'danger')
#     return render_template('login.html')

# @app.route('/verification_sent')
# def verification_sent():
#     email = request.args.get('email')
#     if not email:
#         return redirect(url_for('login'))
#     return render_template('verification_sent.html', email=email)

# @app.route('/register', methods=['GET', 'POST'])
# def register():
#     if g.user:
#         return redirect(url_for('dashboard'))

#     if request.method == 'POST':
#         try:
#             role = request.form.get('role', 'student')
#             username = request.form.get('username')
#             email = request.form.get('email')
#             password = request.form.get('password')

#             # Basic validation for all roles
#             if not all([username, email, password]):
#                 flash('Username, Email, and Password are required.', 'danger')
#                 return render_template('register.html', **request.form)

#             # Check if username or email is already taken anywhere
#             if User.query.filter((User.username == username) | (User.email == email)).first():
#                 flash('Username or email already exists.', 'danger')
#                 return render_template('register.html', **request.form)

#             target_institution = None
#             # Admin-specific logic
#             if role == 'admin':
#                 inst_name = request.form.get('institution_name')
#                 inst_type = request.form.get('institution_type')
#                 if not all([inst_name, inst_type]):
#                     flash('Institution Name and Type are required for admins.', 'danger')
#                     return render_template('register.html', **request.form)
                
#                 # Create the new institution for the admin
#                 target_institution = Institution(name=inst_name, type=inst_type, institution_code=generate_unique_code())
#                 db.session.add(target_institution)
#                 db.session.flush()

#             # Create the base User object for any role
#             new_user = User(username=username, email=email, role=role)
#             new_user.set_password(password)

#             # If the user is an admin, link them to their new institution immediately
#             if role == 'admin':
#                 new_user.institution_id = target_institution.id
#             else:
#                 new_user.institution_id = None
            
#             db.session.add(new_user)
#             db.session.commit()

#             send_verification_email(new_user)
#             return redirect(url_for('verification_sent', email=new_user.email))

#         except Exception as e:
#             db.session.rollback()
#             app.logger.error(f"Error during registration: {e}")
#             flash('An unexpected error occurred. Please try again.', 'danger')

#     return render_template('register.html')

# @app.route('/join_institution', methods=['GET', 'POST'])
# @login_required
# def join_institution():
#     if g.user.institution_id is not None:
#         return redirect(url_for('dashboard'))

#     if request.method == 'POST':
#         try:
#             student_record_id = request.form.get('student_record_id', type=int)
#             student_record = db.session.get(Student, student_record_id)

#             # Security check: ensure the record is valid and not already claimed
#             if not student_record or student_record.user is not None:
#                 flash('Invalid selection or student record already claimed.', 'danger')
#                 return redirect(url_for('join_institution'))

#             # Link the accounts
#             g.user.student_profile = student_record
#             g.user.institution_id = student_record.class_batch.institution_id
#             db.session.commit()
            
#             flash('Successfully joined institution and linked your academic record!', 'success')
#             return redirect(url_for('dashboard'))
#         except Exception as e:
#             db.session.rollback()
#             app.logger.error(f"Error joining institution: {e}")
#             flash('An error occurred. Please try again.', 'danger')
#             return redirect(url_for('join_institution'))

#     return render_template('join_institution.html')

# @app.route('/logout')
# @login_required
# def logout():
#     session.clear()
#     flash('You have been successfully logged out.', 'success')
#     return redirect(url_for('login'))

# @app.route('/verify_otp', methods=['GET', 'POST'])
# def verify_email_otp():
#     email = request.args.get('email')
#     user = User.query.filter_by(email=email).first_or_404()
#     if request.method == 'POST':
#         otp = request.form.get('otp')
#         otp_expiry_aware = make_timezone_aware(user.otp_expiry)
#         if user.otp == otp and otp_expiry_aware and otp_expiry_aware > get_current_ist():
#             user.email_verified = True
#             user.otp = None
#             user.otp_expiry = None
#             db.session.commit()
#             flash('Email successfully verified! You can now log in.', 'success')
#             return redirect(url_for('login'))
#         else:
#             flash('Invalid or expired OTP. A new one has been sent.', 'danger')
#             send_verification_email(user)
#             return redirect(url_for('verify_email_otp', email=email))
#     return render_template('verify_otp.html', email=email)

# @app.route('/resend_verification_otp')
# def resend_verification_otp():
#     email = request.args.get('email')
#     user = User.query.filter_by(email=email).first()
#     if user and not user.email_verified:
#         send_verification_email(user)
#         flash('A new OTP has been sent.', 'success')
#     return redirect(url_for('verify_email_otp', email=email))

# @app.route('/forgot_password', methods=['GET', 'POST'])
# def forgot_password():
#     if request.method == 'POST':
#         user = User.query.filter_by(email=request.form.get('email')).first()
#         if user: 
#             send_password_reset_email(user)
#         flash('If an account with this email exists, a reset link has been sent.', 'info')
#         return redirect(url_for('login'))
#     return render_template('forgot_password.html')

# @app.route('/forgot_username', methods=['GET', 'POST'])
# def forgot_username():
#     if request.method == 'POST':
#         user = User.query.filter_by(email=request.form.get('email')).first()
#         if user: 
#             send_username_email(user)
#         flash('If an account with this email exists, your username has been sent.', 'info')
#         return redirect(url_for('login'))
#     return render_template('forgot_username.html')

# @app.route('/reset_password/<token>', methods=['GET', 'POST'])
# def reset_password(token):
#     user = User.query.filter_by(password_reset_token=token).first()
#     reset_expiry_aware = make_timezone_aware(user.reset_token_expiry) if user else None
#     if not user or not reset_expiry_aware or reset_expiry_aware < get_current_ist():
#         flash('Password reset link is invalid or has expired.', 'danger')
#         return redirect(url_for('forgot_password'))
#     if request.method == 'POST':
#         user.set_password(request.form.get('password'))
#         user.password_reset_token = None
#         user.reset_token_expiry = None
#         db.session.commit()
#         flash('Password reset successfully. Please log in.', 'success')
#         return redirect(url_for('login'))
#     return render_template('reset_password.html', token=token)

# @app.route('/favicon.ico')
# def favicon():
#     return '', 204

# # --- Student & Attendance Management ---
# @app.route('/students')
# @teacher_or_admin_required
# def students():
#     all_classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).order_by(ClassBatch.name).all()
#     selected_class_id = request.args.get('class_id', default=None, type=int)

#     # Fixed query - filters students based on the institution of their assigned batch
#     base_query = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == g.user.institution_id)

#     if selected_class_id:
#         base_query = base_query.filter(Student.class_batch_id == selected_class_id)
    
#     page = request.args.get('page', 1, type=int)
#     query = request.args.get('query', '')
#     if query:
#         search_term = f"%{query}%"
#         base_query = base_query.filter(db.or_(Student.name.ilike(search_term), Student.student_id.ilike(search_term)))
        
#     students_pagination = base_query.order_by(Student.name).paginate(page=page, per_page=15, error_out=False)
    
#     return render_template(
#         'students.html', 
#         students=students_pagination, 
#         query=query,
#         all_classes=all_classes,
#         selected_class_id=selected_class_id
#     )

# @app.route('/add_student', methods=['GET', 'POST'])
# @teacher_or_admin_required
# def add_student():
#     classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()
#     if request.method == 'POST':
#         name = request.form.get('name')
#         sid = request.form.get('student_id')
#         email = request.form.get('email')
#         cid = request.form.get('class_batch_id')
        
#         if not all([name, sid, cid]):
#             flash('Name, Student ID, and Class are required.', 'danger')
#             return render_template('add_student.html', **request.form, classes_batches=classes)

#         # Check if student ID is already taken in this institution
#         existing_student = Student.query.join(ClassBatch).filter(
#             ClassBatch.institution_id == g.user.institution_id,
#             Student.student_id == sid
#         ).first()
        
#         if existing_student:
#             flash('This Student ID is already taken in your institution.', 'danger')
#             return render_template('add_student.html', **request.form, classes_batches=classes)

#         # Create only the Student record, not a User account
#         new_student = Student(name=name, student_id=sid, email=email, class_batch_id=cid)
#         db.session.add(new_student)
#         db.session.commit()
        
#         flash(f'Student "{name}" has been pre-registered successfully.', 'success')
#         return redirect(url_for('students'))
            
#     return render_template('add_student.html', classes_batches=classes)

# @app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
# @teacher_or_admin_required
# def edit_student(student_id):
#     student = db.session.get(Student, student_id)
#     # Verify the student belongs to the institution via their class/batch
#     if not student or student.class_batch.institution_id != g.user.institution_id:
#        flash('Student not found.', 'danger')
#        return redirect(url_for('students'))

#     classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()

#     if request.method == 'POST':
#         # Get data from form
#         new_name = request.form.get('name')
#         new_sid = request.form.get('student_id')
#         new_email = request.form.get('email')
#         new_cid = request.form.get('class_batch_id')

#         # Check if new student ID conflicts with existing student
#         existing_student = Student.query.join(ClassBatch).filter(
#             ClassBatch.institution_id == g.user.institution_id,
#             Student.student_id == new_sid,
#             Student.id != student_id
#         ).first()
        
#         if existing_student:
#             flash('This Student ID is already taken by another student.', 'danger')
#             return render_template('edit_student.html', student=student, classes_batches=classes)

#         # Update student details
#         student.name = new_name
#         student.student_id = new_sid
#         student.email = new_email
#         student.class_batch_id = new_cid
        
#         # Also update the associated User record if it exists
#         if student.user:
#             student.user.username = new_sid
#             student.user.email = new_email

#         db.session.commit()
#         flash(f'Student "{student.name}" updated successfully.', 'success')
#         return redirect(url_for('students'))

#     return render_template('edit_student.html', student=student, classes_batches=classes)

# @app.route('/student_profile/<int:student_id>')
# @teacher_or_admin_required
# def student_profile(student_id):
#     student = db.session.get(Student, student_id)
    
#     # Security check
#     if not student or not student.class_batch or student.class_batch.institution_id != g.user.institution_id:
#         flash('Student not found.', 'danger')
#         return redirect(url_for('students'))
    
#     return render_template('student_profile.html', student=student)

# @app.route('/edit_profile', methods=['GET', 'POST'])
# @login_required
# def edit_profile():
#     # Pehle check karo ki student ka profile linked hai ya nahi
#     student_profile = g.user.student_profile
#     if not student_profile:
#         flash('Your student profile is not linked yet. Please join an institution first.', 'warning')
#         return redirect(url_for('dashboard'))

#     # Sirf student hi is page ko access kar sakta hai
#     if g.user.role != 'student':
#         flash('You do not have permission to access this page.', 'danger')
#         return redirect(url_for('dashboard'))

#     if request.method == 'POST':
#         # Form se naya data get karo
#         student_profile.name = request.form.get('name')
#         student_profile.email = request.form.get('email')
        
#         # Associated User account ko bhi update karo
#         if student_profile.user:
#             student_profile.user.email = request.form.get('email')

#         # Profile photo upload ka logic
#         if 'photo' in request.files:
#             file = request.files['photo']
#             if file and file.filename != '' and allowed_file(file.filename):
#                 filename = secure_filename(f"{student_profile.id}_{file.filename}")
#                 file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
#                 student_profile.photo = filename
        
#         db.session.commit()
#         flash('Profile updated successfully!', 'success')
#         return redirect(url_for('profile'))

#     # GET request par, edit form dikhao
#     return render_template('edit_profile.html', student=student_profile)

# @app.route('/delete_student/<int:student_id>', methods=['POST'])
# @teacher_or_admin_required
# def delete_student(student_id):
#     student = db.session.get(Student, student_id)
#     if student and student.class_batch and student.class_batch.institution_id == g.user.institution_id:
#         db.session.delete(student)
#         db.session.commit()
#         flash(f'Student {student.name} has been deleted.', 'success')
#     else:
#         flash('Student not found or you do not have permission to delete.', 'danger')
#     return redirect(url_for('students'))

# @app.route('/mark_attendance', methods=['GET', 'POST'])
# @teacher_or_admin_required
# def mark_attendance():
#     """
#     Route: /mark_attendance
#     Methods: GET, POST

#     Description:
#         Handles attendance marking for students in a selected class and subject.

#     Parameters:
#         - class_batch_id (int): ID of the class batch (GET/POST)
#         - subject_id (int): ID of the subject (GET/POST)
#         - date (str): Date for attendance in 'YYYY-MM-DD' format (GET/POST)

#     GET:
#         Renders the attendance marking form. Requires class_batch_id, subject_id, and date to load students.

#     POST:
#         Accepts attendance data for each student. Updates or creates attendance records.

#     Returns:
#         - On success: Redirects to /mark_attendance with a success message.
#         - On error: Redirects to /mark_attendance with an error message (e.g., invalid date).

#     Access:
#         Only teachers or admins can access this endpoint.
#     """
#     if request.method == 'POST':
#         class_id = request.form.get('class_batch_id')
#         subject_id = request.form.get('subject_id')
#         date_str = request.form.get('date')
        
#         try:
#             date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
#         except (ValueError, TypeError):
#             flash('Invalid date format.', 'danger')
#             return redirect(url_for('mark_attendance'))
            
#         students_in_class = Student.query.filter_by(class_batch_id=class_id).all()
#         for student in students_in_class:
#             status = request.form.get(f'status_{student.id}')
#             if status:
#                 record = Attendance.query.filter_by(
#                     student_id=student.id, 
#                     date=date_obj, 
#                     subject_id=subject_id
#                 ).first()
#                 if record: 
#                     record.status = status
#                 else: 
#                     db.session.add(Attendance(
#                         student_id=student.id, 
#                         subject_id=subject_id, 
#                         date=date_obj, 
#                         status=status
#                     ))
#         db.session.commit()
#         flash('Attendance saved!', 'success')
#         return redirect(url_for('mark_attendance', 
#                               class_batch_id=class_id, 
#                               subject_id=subject_id, 
#                               date=date_str))
    
#     selected_class_id = request.args.get('class_batch_id', type=int)
#     selected_subject_id = request.args.get('subject_id', type=int)
#     selected_date = request.args.get('date', get_current_ist().strftime('%Y-%m-%d'))
#     students = []
#     attendance_statuses = {}
#     classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()
#     subjects = Subject.query.all()

#     if selected_class_id and selected_subject_id:
#         students = Student.query.filter_by(class_batch_id=selected_class_id).order_by(Student.name).all()
#         try:
#             date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
#             student_ids = [s.id for s in students]
#             existing_records = Attendance.query.filter(
#                 Attendance.student_id.in_(student_ids), 
#                 Attendance.date == date_obj, 
#                 Attendance.subject_id == selected_subject_id
#             ).all()
#             attendance_statuses = {r.student_id: r.status for r in existing_records}
#         except (ValueError, TypeError):
#             flash('Invalid date format.', 'danger')

#     return render_template('mark_attendance.html', 
#                          taught_classes=classes, 
#                          subjects=subjects, 
#                          students=students, 
#                          selected_class_id=selected_class_id, 
#                          selected_subject_id=selected_subject_id,
#                          selected_date=selected_date, 
#                          attendance_statuses=attendance_statuses)

# @app.route('/attendance')
# @teacher_or_admin_required
# def attendance():
#     page = request.args.get('page', 1, type=int)
#     selected_date_str = request.args.get('date')

#     # Fixed query - joins through ClassBatch to get the institution_id
#     base_query = Attendance.query.options(joinedload(Attendance.subject))\
#     .join(Student).join(ClassBatch)\
#     .filter(ClassBatch.institution_id == g.user.institution_id)

#     # Apply date filter if provided
#     if selected_date_str:
#         try:
#             selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
#             base_query = base_query.filter(Attendance.date == selected_date)
#         except (ValueError, TypeError):
#             flash('Invalid date format used for filtering.', 'danger')
#             selected_date_str = None
    
#     records = base_query.order_by(desc(Attendance.date), desc(Attendance.created_at)).paginate(
#         page=page, per_page=20, error_out=False)
    
#     return render_template('attendance.html', records=records, selected_date=selected_date_str)

# @app.route('/reports')
# @teacher_or_admin_required
# def reports():
#     today = get_current_ist().date()
#     start_date = request.args.get('start_date', (today - timedelta(days=29)).strftime('%Y-%m-%d'))
#     end_date = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    
#     try:
#         start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
#         end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
#     except (ValueError, TypeError):
#         flash('Invalid date format.', 'danger')
#         start_date = today - timedelta(days=29)
#         end_date = today

#     # Fixed base query that joins through ClassBatch
#     base_query = Attendance.query.join(Student).join(ClassBatch).filter(
#         ClassBatch.institution_id == g.user.institution_id,
#         Attendance.date.between(start_date, end_date)
#     )

#     total_records = base_query.count()
#     total_present = base_query.filter(Attendance.status == 'present').count()
    
#     summary = {
#         'overall_attendance_percent': (total_present / total_records * 100) if total_records > 0 else 0,
#         'total_present': total_present,
#         'total_absent': total_records - total_present
#     }
    
#     # Subject performance query
#     subject_performance = db.session.query(
#         Subject.name,
#         (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
#     ).select_from(Attendance).join(Subject).join(Student).join(ClassBatch).filter(
#         ClassBatch.institution_id == g.user.institution_id,
#         Attendance.date.between(start_date, end_date)
#     ).group_by(Subject.name).all()
    
#     # Student report data
#     report_data_query = db.session.query(
#         Student.name,
#         func.count(Attendance.id).label('total_days'),
#         func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present_days')
#     ).select_from(Attendance).join(Student).join(ClassBatch).filter(
#         ClassBatch.institution_id == g.user.institution_id,
#         Attendance.date.between(start_date, end_date)
#     ).group_by(Student.name).all()
    
#     processed_report = []
#     for name, total_days, present_days in report_data_query:
#         present = present_days or 0
#         absent = total_days - present
#         percentage = (present / total_days * 100) if total_days > 0 else 0
#         processed_report.append({
#             'student': name,
#             'total_days': total_days,
#             'present': present,
#             'absent': absent,
#             'attendance_percent': round(percentage, 1)
#         })
    
#     return render_template('reports.html', 
#                          summary=summary, 
#                          start_date=start_date.strftime('%Y-%m-%d'), 
#                          end_date=end_date.strftime('%Y-%m-%d'), 
#                          subject_performance=[{'subject': s, 'percentage': round(p, 1)} for s, p in subject_performance], 
#                          report_data=processed_report)

# @app.route('/export/csv')
# @teacher_or_admin_required
# def export_csv():
#     try:
#         # 1. Query the database for all attendance records
#         records = Attendance.query.join(Student).join(ClassBatch)\
#             .filter(ClassBatch.institution_id == g.user.institution_id)\
#             .order_by(Attendance.date, Student.name).all()
        
#         # 2. Use StringIO to build the CSV file in memory
#         output = StringIO()
#         writer = csv.writer(output)
        
#         # 3. Write the header row
#         writer.writerow(['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status', 'Marked At'])
        
#         # 4. Write the data rows
#         for record in records:
#             writer.writerow([
#                 record.student.name,
#                 record.student.student_id,
#                 record.student.class_batch.name if record.student.class_batch else 'N/A',
#                 record.subject.name if record.subject else 'N/A',
#                 record.date.strftime('%Y-%m-%d'),
#                 record.status.capitalize(),
#                 record.created_at.strftime('%Y-%m-%d %H:%M:%S')
#             ])
        
#         # 5. Get the final CSV string
#         csv_output = output.getvalue()
        
#         # 6. Create a Response that the browser will download
#         return Response(
#             csv_output,
#             mimetype="text/csv",
#             headers={"Content-disposition":
#                      "attachment; filename=attendance_report.csv"})

#     except Exception as e:
#         app.logger.error(f"Error exporting CSV: {e}")
#         flash("An error occurred while generating the report.", "danger")
#         return redirect(url_for('dashboard'))
    
#   # Helper class to create PDF with a header
# class PDF(FPDF):
#     def header(self):
#         self.set_font('Helvetica', 'B', 12)
#         self.cell(0, 10, 'Attendance Report', 0, 1, 'C')
#         self.ln(10)

#     def footer(self):
#         self.set_y(-15)
#         self.set_font('Helvetica', 'I', 8)
#         self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

# @app.route('/export/pdf')
# @teacher_or_admin_required
# def export_pdf():
#     try:
#         records = Attendance.query.join(Student).join(ClassBatch)\
#             .filter(ClassBatch.institution_id == g.user.institution_id)\
#             .order_by(Attendance.date, Student.name).all()

#         pdf = PDF(orientation='L', unit='mm', format='A4')
#         pdf.add_page()
#         pdf.set_font('Helvetica', '', 10) 
        
#         headers = ['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status']
#         col_widths = [60, 30, 60, 40, 30, 20]

#         pdf.set_font('Helvetica', 'B', 10)
#         for i, header in enumerate(headers):
#             pdf.cell(col_widths[i], 10, header, border=1, align='C')
#         pdf.ln()

#         pdf.set_font('Helvetica', '', 9)
#         if not records:
#              pdf.cell(sum(col_widths), 10, 'No attendance data found.', border=1, ln=1, align='C')
#         else:
#             for record in records:
#                 pdf.cell(col_widths[0], 10, record.student.name.encode('latin-1', 'replace').decode('latin-1'), border=1)
#                 pdf.cell(col_widths[1], 10, record.student.student_id.encode('latin-1', 'replace').decode('latin-1'), border=1)
#                 pdf.cell(col_widths[2], 10, (record.student.class_batch.name if record.student.class_batch else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
#                 pdf.cell(col_widths[3], 10, (record.subject.name if record.subject else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
#                 pdf.cell(col_widths[4], 10, record.date.strftime('%Y-%m-%d'), border=1)
#                 pdf.cell(col_widths[5], 10, record.status.capitalize(), border=1, ln=1)

#         # --- THIS IS THE CORRECTED PART ---
#         # We now use BytesIO and send_file for a more robust download
#         pdf_output = pdf.output()
        
#         return send_file(
#             BytesIO(pdf_output),
#             mimetype='application/pdf',
#             as_attachment=True,
#             download_name='attendance_report.pdf'
#         )

#     except Exception as e:
#         app.logger.error(f"Error exporting PDF: {e}")
#         flash("An error occurred while generating the PDF report.", "danger")
#         return redirect(url_for('dashboard'))
    
#     # In app.py

# # This is the function that will run on a schedule
# def email_reports_job():
#     """
#     This background task runs automatically. It finds all institutions,
#     generates a PDF report for each, and emails it to all admins of that institution.
#     """
#     print(f"Running scheduled job at {get_current_ist()}...")
#     with app.app_context():
#         try:
#             institutions = Institution.query.all()
#             for institution in institutions:
#                 # Find all admins for this institution
#                 admins = User.query.filter_by(institution_id=institution.id, role='admin').all()
#                 if not admins:
#                     continue # Skip if no admins

#                 # 1. Get the data for the report
#                 records = Attendance.query.join(Student).join(ClassBatch)\
#                     .filter(ClassBatch.institution_id == institution.id)\
#                     .order_by(Attendance.date, Student.name).all()

#                 # 2. Generate the PDF in memory (using our existing PDF class)
#                 pdf = PDF(orientation='L', unit='mm', format='A4')
#                 pdf.add_page()
#                 pdf.set_font('Helvetica', '', 10)
#                 headers = ['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status']
#                 col_widths = [60, 30, 60, 40, 30, 20]
#                 pdf.set_font('Helvetica', 'B', 10)
#                 for i, header in enumerate(headers):
#                     pdf.cell(col_widths[i], 10, header, border=1, align='C')
#                 pdf.ln()
#                 pdf.set_font('Helvetica', '', 9)
#                 if not records:
#                     pdf.cell(sum(col_widths), 10, 'No attendance data for this period.', border=1, ln=1, align='C')
#                 else:
#                     for record in records:
#                         pdf.cell(col_widths[0], 10, record.student.name.encode('latin-1', 'replace').decode('latin-1'), border=1)
#                         pdf.cell(col_widths[1], 10, record.student.student_id.encode('latin-1', 'replace').decode('latin-1'), border=1)
#                         pdf.cell(col_widths[2], 10, (record.student.class_batch.name if record.student.class_batch else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
#                         pdf.cell(col_widths[3], 10, (record.subject.name if record.subject else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
#                         pdf.cell(col_widths[4], 10, record.date.strftime('%Y-%m-%d'), border=1)
#                         pdf.cell(col_widths[5], 10, record.status.capitalize(), border=1, ln=1)

#                 pdf_output = pdf.output()
                
#                 # 3. Send the email with the PDF as an attachment
#                 recipient_emails = [admin.email for admin in admins]
#                 msg = Message(
#                     f"Weekly Attendance Report for {institution.name}",
#                     recipients=recipient_emails
#                 )
#                 msg.body = "Please find the weekly attendance report attached."
#                 msg.attach(
#                     "attendance_report.pdf",
#                     "application/pdf",
#                     pdf_output
#                 )
#                 mail.send(msg)
#                 print(f"Report sent for institution: {institution.name}")
#         except Exception as e:
#             app.logger.error(f"Error in scheduled job: {e}")

# # In app.py

# @app.route('/my_attendance')
# @login_required
# def my_attendance():
#     # This page should only be accessible when in the student view.
#     if g.role != 'student':
#         flash("This page is only for the student view.", "warning")
#         return redirect(url_for('dashboard'))

#     # If a REAL student is logged in, their g.user.student_profile will exist.
#     # We show them their actual attendance data.
#     if g.user.student_profile:
#         records = g.user.student_profile.attendances.order_by(desc(Attendance.date)).all()
#         return render_template('my_attendance.html', records=records, student=g.user.student_profile)
    
#     # If an ADMIN is impersonating a student, they won't have a student_profile.
#     # We just show them an empty version of the page so they can see what it looks like without crashing.
#     else:
#         return render_template('my_attendance.html', records=None, student=None)

# # TO THIS (add a slash at the end):
# @app.route('/check_attendance/', methods=['GET', 'POST'])
# def check_attendance():
#     student = None
#     attendance_records = None
#     student_id_searched = "" # Start with an empty search

#     # This code only runs when you click the "View My Attendance" button
#     if request.method == 'POST':
#         student_id_searched = request.form.get('student_id')
#         if student_id_searched:
#             student = Student.query.filter_by(student_id=student_id_searched).first()
#             if student:
#                 # Fetch records for this student
#                 attendance_records = student.attendances.order_by(desc(Attendance.date)).paginate(
#                     page=1, per_page=15, error_out=True
#                 )
#             else:
#                 flash(f'No student found with ID: {student_id_searched}', 'warning')
    
#     # The page is rendered, and results are only sent if they were found
#     return render_template(
#         'check_attendance.html', 
#         student=student, 
#         attendance_records=attendance_records, 
#         student_id_searched=student_id_searched
#     )




# # --- Analytics ---
# @app.route('/analytics')
# @teacher_or_admin_required
# def analytics():
#     inst_id = g.user.institution_id
    
#     # Fixed heatmap data query
#     heatmap_data = db.session.query(
#         extract('isodow', Attendance.date).label('day_of_week'),  # Monday=1, Sunday=7
#         extract('hour', Attendance.created_at).label('hour_of_day'),
#         (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
#     ).join(Student).join(ClassBatch).filter(
#         ClassBatch.institution_id == inst_id
#     ).group_by('day_of_week', 'hour_of_day').all()
    
#     heatmap_json = [{'day_of_week': d % 7, 'hour_of_day': h, 'percentage': p} for d, h, p in heatmap_data]
    
#     thirty_days_ago = get_current_ist().date() - timedelta(days=30)
    
#     # Fixed student engagement query
#     student_engagement = db.session.query(
#         Student.name,
#         (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('engagement_score')
#     ).join(Attendance).join(ClassBatch).filter(
#         ClassBatch.institution_id == inst_id, 
#         Attendance.date >= thirty_days_ago
#     ).group_by(Student.name).order_by(desc('engagement_score')).limit(10).all()
    
#     return render_template('analytics.html', 
#                          heatmap_data=heatmap_json, 
#                          student_engagement=student_engagement)

# # --- Admin Setup & Management ---
# @app.route('/setup', methods=['GET', 'POST'])
# @admin_required
# def setup():
#     if request.method == 'POST':
#         if 'class_batch_name' in request.form and request.form['class_batch_name']:
#             new_class = ClassBatch(
#                 name=request.form['class_batch_name'], 
#                 institution_id=g.user.institution_id
#             )
#             db.session.add(new_class)
#             flash('New class/batch created.', 'success')
            
#         if 'subject_name' in request.form and request.form['subject_name']:
#             new_subject = Subject(name=request.form['subject_name'])
#             db.session.add(new_subject)
#             flash('New subject created.', 'success')
            
#         db.session.commit()
#         return redirect(url_for('setup'))
    
#     # Fixed query for unassigned students
#     unassigned = Student.query.join(ClassBatch).filter(
#         Student.class_batch_id == None, 
#         ClassBatch.institution_id == g.user.institution_id
#     ).all()
    
#     classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).options(
#         joinedload(ClassBatch.teachers)
#     ).all()
    
#     teachers = User.query.filter_by(
#         role='teacher', 
#         institution_id=g.user.institution_id
#     ).all()
    
#     subjects = Subject.query.all()
    
#     return render_template('setup.html', 
#                          unassigned_students=unassigned, 
#                          classes_batches=classes, 
#                          teachers=teachers, 
#                          subjects=subjects, 
#                          institution=g.user.institution)

# # In app.py
# @app.route('/schedule', methods=['GET', 'POST'])
# @admin_required
# def schedule():
#     job_id = 'Weekly Report Job'
    
#     try:
#         if request.method == 'POST':
#             action = request.form.get('action')
            
#             # FIX 1: Validate action parameter
#             if not action:
#                 flash('Invalid action specified.', 'error')
#                 job = scheduler.get_job(job_id)
#                 return render_template('schedule.html', job=job)
            
#             # FIX 2: Get current job with error handling
#             try:
#                 job = scheduler.get_job(job_id)
#             except Exception as e:
#                 app.logger.error(f"Error getting job {job_id}: {str(e)}")
#                 job = None
            
#             if action == 'schedule':
#                 # FIX 3: Enhanced form validation
#                 day_of_week = request.form.get('day_of_week')
#                 hour_str = request.form.get('hour')
                
#                 # Validate required fields
#                 if not day_of_week:
#                     flash('Please select a day of the week.', 'error')
#                     return render_template('schedule.html', job=job)
                
#                 # Validate and convert hour
#                 try:
#                     hour = int(hour_str) if hour_str else None
#                     if hour is None:
#                         flash('Please select an hour.', 'error')
#                         return render_template('schedule.html', job=job)
                    
#                     # FIX 4: Validate hour range (0-23)
#                     if not (0 <= hour <= 23):
#                         flash('Hour must be between 0 and 23.', 'error')
#                         return render_template('schedule.html', job=job)
                        
#                 except (ValueError, TypeError):
#                     flash('Invalid hour format. Please enter a valid number.', 'error')
#                     return render_template('schedule.html', job=job)
                
#                 # FIX 5: Validate day_of_week format
#                 valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun', 
#                              'monday', 'tuesday', 'wednesday', 'thursday', 
#                              'friday', 'saturday', 'sunday', '0', '1', '2', '3', '4', '5', '6']
#                 if day_of_week.lower() not in valid_days:
#                     flash('Invalid day of week selected.', 'error')
#                     return render_template('schedule.html', job=job)
                
#                 try:
#                     # FIX 6: Check if email_reports_job function exists
#                     if 'email_reports_job' not in globals():
#                         flash('Email reports function not available. Please contact administrator.', 'error')
#                         return render_template('schedule.html', job=job)
                    
#                     if job:
#                         # Update existing job
#                         scheduler.modify_job(
#                             job_id, 
#                             trigger='cron', 
#                             day_of_week=day_of_week, 
#                             hour=hour, 
#                             minute=0,
#                             replace_existing=True  # FIX 7: Ensure job is replaced properly
#                         )
#                         flash(f'Report schedule updated successfully! Next run: {day_of_week.capitalize()} at {hour:02d}:00', 'success')
#                         app.logger.info(f"Job {job_id} modified: {day_of_week} at {hour}:00")
#                     else:
#                         # Create new job
#                         scheduler.add_job(
#                             id=job_id, 
#                             func=email_reports_job, 
#                             trigger='cron', 
#                             day_of_week=day_of_week, 
#                             hour=hour, 
#                             minute=0,
#                             replace_existing=True,  # FIX 8: Prevent duplicate job errors
#                             max_instances=1  # FIX 9: Prevent multiple instances running
#                         )
#                         flash(f'Report scheduled successfully! Next run: {day_of_week.capitalize()} at {hour:02d}:00', 'success')
#                         app.logger.info(f"Job {job_id} created: {day_of_week} at {hour}:00")
                        
#                 except Exception as e:
#                     # FIX 10: Better error handling for scheduler operations
#                     error_msg = f"Failed to schedule report: {str(e)}"
#                     flash(error_msg, 'error')
#                     app.logger.error(f"Scheduler error: {error_msg}")
#                     return render_template('schedule.html', job=job)
            
#             elif action == 'cancel':
#                 if job:
#                     try:
#                         scheduler.remove_job(job_id)
#                         flash('Report schedule canceled successfully.', 'warning')
#                         app.logger.info(f"Job {job_id} canceled")
#                     except Exception as e:
#                         error_msg = f"Failed to cancel scheduled report: {str(e)}"
#                         flash(error_msg, 'error')
#                         app.logger.error(f"Job cancellation error: {error_msg}")
#                 else:
#                     flash('No scheduled report found to cancel.', 'info')
            
#             elif action == 'run_now':
#                 # FIX 11: Add immediate execution option
#                 try:
#                     if 'email_reports_job' in globals():
#                         # Run the job immediately in background
#                         scheduler.add_job(
#                             id=f"{job_id}_immediate_{int(time.time())}", 
#                             func=email_reports_job, 
#                             trigger='date',  # Run once immediately
#                             run_date=datetime.now() + timedelta(seconds=5)  # Small delay
#                         )
#                         flash('Report generation started. You will receive it shortly.', 'info')
#                         app.logger.info(f"Immediate report job started")
#                     else:
#                         flash('Report generation function not available.', 'error')
#                 except Exception as e:
#                     error_msg = f"Failed to generate immediate report: {str(e)}"
#                     flash(error_msg, 'error')
#                     app.logger.error(f"Immediate report error: {error_msg}")
            
#             else:
#                 # FIX 12: Handle unknown actions
#                 flash(f'Unknown action: {action}', 'error')
#                 app.logger.warning(f"Unknown action received: {action}")
        
#         # FIX 13: Always get fresh job status after any operation
#         try:
#             job = scheduler.get_job(job_id)
#         except Exception as e:
#             app.logger.error(f"Error getting job status: {str(e)}")
#             job = None
        
#         # FIX 14: Add job status information for template
#         job_info = None
#         if job:
#             try:
#                 next_run = job.next_run_time
#                 job_info = {
#                     'id': job.id,
#                     'next_run': next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else 'Not scheduled',
#                     'trigger': str(job.trigger),
#                     'is_active': True
#                 }
#             except Exception as e:
#                 app.logger.error(f"Error parsing job info: {str(e)}")
#                 job_info = {
#                     'id': job_id,
#                     'next_run': 'Error getting schedule',
#                     'trigger': 'Unknown',
#                     'is_active': False
#                 }
        
#         return render_template('schedule.html', job=job, job_info=job_info)
        
#     except Exception as e:
#         # FIX 15: Global error handler
#         error_msg = f"An unexpected error occurred: {str(e)}"
#         flash(error_msg, 'error')
#         app.logger.error(f"Schedule route error: {error_msg}")
        
#         # Try to get job status even if there was an error
#         try:
#             job = scheduler.get_job(job_id)
#             job_info = None
#         except:
#             job = None
#             job_info = None
            
#         return render_template('schedule.html', job=job, job_info=job_info)


# # FIX 16: Add helper function to validate scheduler state
# def check_scheduler_health():
#     """Check if scheduler is running and healthy"""
#     try:
#         if not scheduler.running:
#             app.logger.warning("Scheduler is not running")
#             return False, "Scheduler is not running"
        
#         # Try to get jobs list to test connectivity
#         jobs = scheduler.get_jobs()
#         return True, f"Scheduler healthy with {len(jobs)} jobs"
        
#     except Exception as e:
#         error_msg = f"Scheduler health check failed: {str(e)}"
#         app.logger.error(error_msg)
#         return False, error_msg


# # FIX 17: Add route to check scheduler status (for debugging)
# @app.route('/admin/scheduler-status')
# @admin_required
# def scheduler_status():
#     """Admin endpoint to check scheduler health"""
#     is_healthy, message = check_scheduler_health()
#     jobs = []
    
#     try:
#         if scheduler.running:
#             jobs = [
#                 {
#                     'id': job.id,
#                     'next_run': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else 'Not scheduled',
#                     'trigger': str(job.trigger)
#                 }
#                 for job in scheduler.get_jobs()
#             ]
#     except Exception as e:
#         app.logger.error(f"Error getting jobs list: {str(e)}")
    
#     return jsonify({
#         'healthy': is_healthy,
#         'message': message,
#         'running': scheduler.running if hasattr(scheduler, 'running') else False,
#         'jobs': jobs
#     })


# # FIX 18: Ensure required imports at top of file
# """
# Make sure you have these imports at the top of your file:

# from datetime import datetime, timedelta
# import time
# from flask import jsonify
# """


# @app.route('/assign_student_to_class/<int:student_id>', methods=['POST'])
# @admin_required
# def assign_student_to_class(student_id):
#     student = db.session.get(Student, student_id)
#     class_id = request.form.get('class_batch_id')
#     if student and class_id:
#         student.class_batch_id = class_id
#         db.session.commit()
#         flash(f'{student.name} assigned.', 'success')
#     return redirect(url_for('setup'))

# @app.route('/assign_teacher_to_class/<int:class_id>', methods=['POST'])
# @admin_required
# def assign_teacher_to_class(class_id):
#     class_batch = db.session.get(ClassBatch, class_id)
#     teacher_id = request.form.get('teacher_id')
#     teacher = db.session.get(User, teacher_id)
    
#     if class_batch and teacher and class_batch.institution_id == g.user.institution_id:
#         if teacher not in class_batch.teachers:
#             class_batch.teachers.append(teacher)
#             db.session.commit()
#             flash(f'Teacher assigned to {class_batch.name}.', 'success')
#         else:
#             flash('Teacher is already assigned to this class.', 'info')
#     return redirect(url_for('setup'))

# @app.route('/unassign_teacher_from_class/<int:class_id>/<int:teacher_id>', methods=['POST'])
# @admin_required
# def unassign_teacher_from_class(class_id, teacher_id):
#     class_batch = db.session.get(ClassBatch, class_id)
#     teacher = db.session.get(User, teacher_id)
    
#     if class_batch and teacher and class_batch.institution_id == g.user.institution_id:
#         if teacher in class_batch.teachers:
#             class_batch.teachers.remove(teacher)
#             db.session.commit()
#             flash(f'Teacher unassigned from {class_batch.name}.', 'success')
#         else:
#             flash('Teacher is not assigned to this class.', 'info')
#     return redirect(url_for('setup'))

# @app.route('/delete_class_batch/<int:class_id>', methods=['POST'])
# @admin_required
# def delete_class_batch(class_id):
#     class_to_delete = db.session.get(ClassBatch, class_id)
    
#     if class_to_delete and class_to_delete.institution_id == g.user.institution_id:
#         if not class_to_delete.students.first():
#             db.session.delete(class_to_delete)
#             db.session.commit()
#             flash('Class/Batch deleted.', 'success')
#         else:
#             flash('Cannot delete a class with students assigned to it.', 'danger')
#     return redirect(url_for('setup'))

# @app.route('/delete_subject/<int:subject_id>', methods=['POST'])
# @admin_required
# def delete_subject(subject_id):
#     subject_to_delete = db.session.get(Subject, subject_id)
#     if subject_to_delete and not subject_to_delete.attendances.first():
#         db.session.delete(subject_to_delete)
#         db.session.commit()
#         flash('Subject deleted.', 'success')
#     else:
#         flash('Cannot delete a subject with attendance records.', 'danger')
#     return redirect(url_for('setup'))

# @app.route('/add_medical_leave/<int:student_id>', methods=['GET', 'POST'])
# @teacher_or_admin_required
# def add_medical_leave(student_id):
#     student = db.session.get(Student, student_id)
    
#     if not student or student.class_batch.institution_id != g.user.institution_id:
#         flash('Student not found.', 'danger')
#         return redirect(url_for('students'))
    
#     if request.method == 'POST':
#         try:
#             start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
#             end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
#             reason = request.form.get('reason')
            
#             if start_date and end_date and reason:
#                 if start_date <= end_date:
#                     leave = MedicalLeave(
#                         student_id=student_id, 
#                         start_date=start_date, 
#                         end_date=end_date, 
#                         reason=reason
#                     )
#                     db.session.add(leave)
#                     db.session.commit()
#                     flash('Medical leave added successfully.', 'success')
#                     return redirect(url_for('student_profile', student_id=student_id))
#                 else:
#                     flash('End date must be after start date.', 'danger')
#         except (ValueError, TypeError):
#             flash('Invalid date format.', 'danger')
    
#     return render_template('add_leave.html', student=student)

# @app.route('/import_students', methods=['GET', 'POST'])
# @admin_required
# def import_students():
#     if request.method == 'POST':
#         if 'student_csv' not in request.files:
#             flash('No file part', 'danger')
#             return redirect(request.url)
            
#         file = request.files['student_csv']
#         if file.filename == '':
#             flash('No selected file', 'danger')
#             return redirect(request.url)
            
#         if file and file.filename.endswith('.csv'):
#             try:
#                 stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
#                 csv_reader = csv.DictReader(stream)
#                 count = 0
#                 errors = []
                
#                 for row_num, row in enumerate(csv_reader, start=2):
#                     try:
#                         # Validate required fields
#                         if not all(key in row for key in ['name', 'student_id', 'class_batch_id']):
#                             errors.append(f"Row {row_num}: Missing required fields")
#                             continue
                            
#                         # Check if class batch exists and belongs to this institution
#                         class_batch = db.session.get(ClassBatch, int(row['class_batch_id']))
#                         if not class_batch or class_batch.institution_id != g.user.institution_id:
#                             errors.append(f"Row {row_num}: Invalid class batch")
#                             continue
                            
#                         student = Student(
#                             name=row['name'], 
#                             student_id=row['student_id'], 
#                             email=row.get('email', ''), 
#                             class_batch_id=int(row['class_batch_id'])
#                         )
#                         db.session.add(student)
#                         count += 1
                        
#                     except Exception as e:
#                         errors.append(f"Row {row_num}: {str(e)}")
                        
#                 db.session.commit()
                
#                 if errors:
#                     flash(f'Imported {count} students with {len(errors)} errors. Errors: {"; ".join(errors[:5])}', 'warning')
#                 else:
#                     flash(f'Successfully imported {count} students.', 'success')
                    
#                 return redirect(url_for('students'))
                
#             except Exception as e:
#                 flash(f'Error processing file: {str(e)}', 'danger')
                
#     return render_template('import_students.html')

# # --- QR Code & Attendance Scanning ---
# @app.route('/api/generate_qr', methods=['POST'])
# @teacher_or_admin_required
# def generate_qr():
#     data = request.json
#     class_id = data.get('class_batch_id')
#     subject_id = data.get('subject_id')
    
#     if not class_id or not subject_id:
#         return jsonify({'error': 'Class and Subject are required.'}), 400
        
#     try:
#         # Verify the class belongs to the teacher's institution
#         class_batch = db.session.get(ClassBatch, int(class_id))
#         if not class_batch or class_batch.institution_id != g.user.institution_id:
#             return jsonify({'error': 'Invalid class selection.'}), 400
            
#         token = QRToken(
#             class_batch_id=int(class_id), 
#             subject_id=int(subject_id), 
#             expiry_time=get_current_ist() + timedelta(minutes=2)
#         )
#         db.session.add(token)
#         db.session.commit()
        
#         scan_url = url_for('scan_attendance_token', token=token.token, _external=True)
#         img = qrcode.make(scan_url)
#         buffered = BytesIO()
#         img.save(buffered, format="PNG")
#         img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
#         return jsonify({'qr_image': img_str})
        
#     except Exception as e:
#         app.logger.error(f"Error generating QR code: {e}")
#         return jsonify({'error': 'Failed to generate QR code.'}), 500

# @app.route('/scan_attendance/<token>')
# @login_required
# def scan_attendance_token(token):
#     if g.user.role != 'student':
#         flash('Only students can scan QR codes.', 'warning')
#         return redirect(url_for('dashboard'))
        
#     qr_token = QRToken.query.filter_by(token=token).first()
#     if not qr_token or get_current_ist() > qr_token.expiry_time:
#         flash('QR code is invalid or has expired.', 'danger')
#         return redirect(url_for('my_attendance'))
        
#     student = g.user.student_profile
#     if not student or student.class_batch_id != qr_token.class_batch_id:
#         flash('You are not in the correct class for this QR code.', 'danger')
#         return redirect(url_for('my_attendance'))
        
#     today = get_current_ist().date()
#     record = Attendance.query.filter_by(
#         student_id=student.id, 
#         date=today, 
#         subject_id=qr_token.subject_id
#     ).first()
    
#     if record:
#         record.status = 'present'
#         record.marked_by = 'qr'
#         flash('Attendance updated to present.', 'success')
#     else:
#         new_record = Attendance(
#             student_id=student.id, 
#             subject_id=qr_token.subject_id, 
#             date=today, 
#             status='present', 
#             marked_by='qr'
#         )
#         db.session.add(new_record)
#         flash('Attendance marked successfully!', 'success')
        
#     db.session.delete(qr_token)
#     db.session.commit()
#     return redirect(url_for('my_attendance'))

# # --- Role Switching & Profile Management ---
# @app.route('/switch_role/<new_role>')
# @login_required
# def switch_role(new_role):
#     # Rule: Sirf admin hi role switch kar sakta hai
#     if g.user.role == 'admin':

#         # Agar admin student ya teacher view mein switch karna chahta hai
#         if new_role in ['teacher', 'student']:
#             # Hum ek alag session variable 'view_as' set kar rahe hain
#             session['view_as'] = new_role
#             flash(f"Switched to {new_role.capitalize()} view.", "success")

#         # Agar admin wapas apne view mein aana chahta hai
#         elif new_role == 'admin':
#             # Hum 'view_as' variable ko session se hata denge
#             session.pop('view_as', None)
#             flash("Switched back to Admin view.", "success")
            
#         else:
#             flash("Invalid role specified.", "danger")
#     else:
#         # Agar koi non-admin user is URL ko access karne ki koshish kare
#         flash("You do not have permission to switch roles.", "danger")
        
#     # Har action ke baad user ko dashboard par bhej do
#     return redirect(url_for('dashboard'))

# @app.context_processor
# def inject_current_role():
#     # Pehle user ka real role check karo
#     if g.user:
#         # Agar admin ne view switch kiya hai, toh woh role use karo
#         if 'view_as' in session:
#             return {'g_role': session['view_as']}
#         # Warna user ka original role use karo
#         return {'g_role': g.user.role}
#     return {'g_role': None}

# @app.route('/profile', methods=['GET', 'POST'])
# @login_required
# def profile():
#     # POST request (password change) ko pehle handle karein
#     if request.method == 'POST':
#         # ... (Aapka password change ka logic yahan aayega) ...
#         # Example:
#         current_password = request.form.get('current_password')
#         new_password = request.form.get('new_password')
#         if current_password and new_password:
#             if g.user.check_password(current_password):
#                 g.user.set_password(new_password)
#                 db.session.commit()
#                 flash('Password updated successfully!', 'success')
#             else:
#                 flash('Incorrect current password.', 'danger')
#             return redirect(url_for('profile'))
    
#     # --- GET REQUEST LOGIC ---
#     # Hamesha database se fresh user data fetch karein
#     user = db.session.get(User, g.user.id)
#     data = {}
    
#     try:
#         if user.role == 'student':
#             student_profile = user.student_profile
#             if student_profile:
#                 total_days = Attendance.query.filter_by(student_id=student_profile.id).count()
#                 present_days = Attendance.query.filter_by(student_id=student_profile.id, status='present').count()
#                 data = {
#                     'attendance_percentage': round((present_days / total_days * 100), 1) if total_days > 0 else 0,
#                     'total_present': present_days,
#                     'total_absent': total_days - present_days
#                 }
#             else:
#                 data = {'attendance_percentage': 0, 'total_present': 0, 'total_absent': 0}

#         elif user.role == 'teacher':
#             taught_classes = user.taught_classes
#             student_count = sum(c.students.count() for c in taught_classes)
#             data = {
#                 'class_count': len(taught_classes),
#                 'student_count': student_count
#             }

#         elif user.role == 'admin':
#             inst_id = user.institution_id
#             total_students = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == inst_id).count()
#             total_teachers = User.query.filter_by(institution_id=inst_id, role='teacher').count()
#             total_classes = ClassBatch.query.filter_by(institution_id=inst_id).count()
#             data = {
#                 'total_students': total_students,
#                 'total_teachers': total_teachers,
#                 'total_classes': total_classes
#             }
            
#     except Exception as e:
#         app.logger.error(f"Error fetching profile data for user {user.id}: {e}")
#         flash("An error occurred while loading profile data.", "danger")

#     return render_template('profile.html', data=data, user_profile=user)

# @app.route('/apply_leave', methods=['GET', 'POST'])
# @login_required
# def apply_leave():
#     # This route is only for students
#     if g.user.role != 'student' or not g.user.student_profile:
#         flash('Only students can apply for leave.', 'warning')
#         return redirect(url_for('dashboard'))

#     if request.method == 'POST':
#         try:
#             start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
#             end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
#             reason = request.form.get('reason')

#             if start_date and end_date and reason:
#                 if start_date <= end_date:
#                     leave = MedicalLeave(
#                         student_id=g.user.student_profile.id, 
#                         start_date=start_date, 
#                         end_date=end_date, 
#                         reason=reason,
#                         # Set expiry to 48 hours from the time of request
#                         expiry_time=get_current_ist() + timedelta(hours=48)
#                     )
#                     db.session.add(leave)
#                     db.session.commit()
#                     flash('Leave request submitted successfully.', 'success')
#                     return redirect(url_for('profile'))
#                 else:
#                     flash('End date must be after start date.', 'danger')
#         except (ValueError, TypeError):
#             flash('Invalid date format.', 'danger')
    
#     return render_template('apply_leave.html')

# @app.route('/delete_account', methods=['POST'])
# @login_required
# def delete_account():
#     email_confirmation = request.form.get('email_confirm')

#     if email_confirmation and email_confirmation.lower() == g.user.email.lower():
#         try:
#             user_to_delete = g.user
#             db.session.delete(user_to_delete)
#             db.session.commit()
            
#             # Use session.clear() for consistency with the /logout route
#             session.clear()
            
#             flash('Your account has been permanently deleted.', 'success')
#             return redirect(url_for('login'))
#         except Exception as e:
#             db.session.rollback()
#             app.logger.error(f"Error deleting account: {e}")
#             flash('An error occurred while deleting your account. Please try again.', 'danger')
#             return redirect(url_for('profile'))
#     else:
#         flash('The email address you entered was incorrect. Account deletion cancelled.', 'danger')
#         return redirect(url_for('profile'))

# # --- API Routes for Institution Management ---
# @app.route('/api/get_batches/<institution_code>')
# @login_required
# def get_batches_for_institution(institution_code):
#     institution = Institution.query.filter_by(institution_code=institution_code.upper()).first()
#     if not institution:
#         return jsonify({'error': 'Institution not found'}), 404
    
#     batches = [{'id': batch.id, 'name': batch.name} for batch in institution.class_batches]
#     return jsonify(batches)

# @app.route('/api/get_students/<int:batch_id>')
# @login_required
# def get_students_in_batch(batch_id):
#     # Find students in this batch who do NOT have a user account linked yet
#     students = Student.query.filter_by(class_batch_id=batch_id, user=None).all()
    
#     student_list = [{'id': student.id, 'name': student.name, 'student_id': student.student_id} for student in students]
#     return jsonify(student_list)

# # --- Error Handlers ---
# @app.errorhandler(404)
# def not_found(error):
#     return render_template('error.html', error_code=404, error_message="Page not found"), 404

# @app.errorhandler(500)
# def internal_error(error):
#     db.session.rollback()
#     return render_template('error.html', error_code=500, error_message="Internal server error"), 500

# @app.errorhandler(403)
# def forbidden(error):
#     return render_template('error.html', error_code=403, error_message="Access forbidden"), 403

# # --- Context Processors ---
# @app.context_processor
# def inject_user():
#     return dict(current_user=g.user)

# # --- CLI Commands ---
# @app.cli.command('init-db')
# def init_db_command():
#     """Initializes the database by dropping and recreating all tables."""
#     db.drop_all()
#     db.create_all()
    
#     # Create default subjects
#     default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
#     for subject_name in default_subjects:
#         if not Subject.query.filter_by(name=subject_name).first():
#             subject = Subject(name=subject_name)
#             db.session.add(subject)
    
#     db.session.commit()
#     click.echo('Database Initialised Successfully.')

# @app.cli.command('create-admin')
# @click.argument('username')
# @click.argument('email')
# @click.argument('password')
# @click.argument('institution_name')
# @click.argument('institution_type')
# def create_admin_command(username, email, password, institution_name, institution_type):
#     """Create an admin user with institution."""
#     try:
#         # Check if user already exists
#         if User.query.filter((User.username == username) | (User.email == email)).first():
#             click.echo('User with this username or email already exists.')
#             return
        
#         # Create institution
#         institution = Institution(
#             name=institution_name, 
#             type=institution_type, 
#             institution_code=generate_unique_code()
#         )
#         db.session.add(institution)
#         db.session.flush()
        
#         # Create admin user
#         admin_user = User(
#             username=username, 
#             email=email, 
#             role='admin',
#             email_verified=True,
#             institution_id=institution.id
#         )
#         admin_user.set_password(password)
#         db.session.add(admin_user)
        
#         db.session.commit()
#         click.echo(f'Admin user created successfully. Institution code: {institution.institution_code}')
        
#     except Exception as e:
#         db.session.rollback()
#         click.echo(f'Error creating admin user: {e}')

# @app.cli.command('reset-password')
# @click.argument('username')
# @click.argument('new_password')
# def reset_password_command(username, new_password):
#     """Reset a user's password."""
#     user = User.query.filter_by(username=username).first()
#     if user:
#         user.set_password(new_password)
#         db.session.commit()
#         click.echo(f'Password reset for user: {username}')
#     else:
#         click.echo('User not found.')

# # --- Application Factory Pattern Support ---
# def create_app(config_name=None):
#     """Application factory for creating Flask app instances."""
#     app = Flask(__name__)
    
#     # Load configuration
#     if config_name == 'testing':
#         app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
#         app.config['TESTING'] = True
#         app.config['WTF_CSRF_ENABLED'] = False
#     elif config_name == 'production':
#         app.config.from_object('config.ProductionConfig')
#     else:
#         app.config.from_object('config.DevelopmentConfig')
    
#     db.init_app(app)
#     mail.init_app(app)
    
#     return app

# # --- Main Application Runner ---
# if __name__ == '__main__':
#     # Create tables if they don't exist
#     with app.app_context():
#         db.create_all()
        
#         # Create default subjects if they don't exist
#         default_subjects = ['Mathematics', 'English', 'Science', 'History', 'Geography']
#         for subject_name in default_subjects:
#             if not Subject.query.filter_by(name=subject_name).first():
#                 subject = Subject(name=subject_name)
#                 db.session.add(subject)
        
#         try:
#             db.session.commit()
#         except Exception as e:
#             db.session.rollback()
#             app.logger.error(f"Error creating default subjects: {e}")
    
#     app.run(debug=True)