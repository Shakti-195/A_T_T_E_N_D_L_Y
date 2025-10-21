# -*- coding: utf-8 -*-
"""
This file contains utility functions, decorators, and other helper code
that is shared across the application.
"""

# --- Standard Library Imports ---
import random
import string
import pytz
from datetime import datetime, timedelta
from functools import wraps
import uuid

# --- Third-Party Library Imports ---
from flask import g, session, flash, redirect, url_for, current_app
from flask_mail import Message
from sqlalchemy import func, case, desc, extract
from sqlalchemy.orm import joinedload

# --- Local Application Imports ---
# NOTE: We only import extensions at the top level to avoid circular imports.
# Models will be imported INSIDE the functions that need them.
from .extensions import mail, db


# --- Timezone and File Helpers ---

IST = pytz.timezone('Asia/Kolkata')

def get_current_ist():
    """Returns the current time in the IST timezone."""
    return datetime.now(IST)

def make_timezone_aware(dt):
    """Makes a naive datetime object timezone-aware."""
    if dt and dt.tzinfo is None:
        return IST.localize(dt)
    return dt

def allowed_file(filename):
    """Checks if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


# --- Code and Token Generators ---

def generate_unique_code():
    """Generates a unique 6-character code for an institution."""
    # Import model here to break the circular dependency
    from .models import Institution
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not Institution.query.filter_by(institution_code=code).first():
            return code

# --- Dashboard Data Helper Functions ---

def get_attendance_leaderboard(institution_id, class_id=None):
    """Fetches the top 3 students by attendance percentage."""
    from .models import Attendance, Student, ClassBatch
    
    subquery = db.session.query(
        Attendance.student_id,
        func.count(Attendance.id).label('total_days'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present_days')
    ).join(Student).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)

    if class_id:
        subquery = subquery.filter(Student.class_batch_id == class_id)
    
    subquery = subquery.group_by(Attendance.student_id).subquery()

    leaderboard_query = db.session.query(
        Student.name,
        ((subquery.c.present_days * 100.0) / subquery.c.total_days).label('percentage')
    ).join(subquery, Student.id == subquery.c.student_id)

    leaderboard = leaderboard_query.order_by(desc('percentage')).limit(3).all()
    return [{'name': name, 'percentage': round(p, 1)} for name, p in leaderboard]

def get_pending_leaves(institution_id, class_id=None):
    """Fetches the 3 most recent, non-expired pending medical leaves."""
    from .models import MedicalLeave, Student, ClassBatch

    leaves_query = MedicalLeave.query.join(Student).join(ClassBatch)\
        .filter(ClassBatch.institution_id == institution_id)

    leaves_query = leaves_query.filter(
        MedicalLeave.status == 'pending',
        MedicalLeave.expiry_time > get_current_ist()
    )

    if class_id:
        leaves_query = leaves_query.filter(Student.class_batch_id == class_id)
        
    leaves = leaves_query.order_by(desc(MedicalLeave.created_at)).limit(3).all()
    return [{'student_name': leave.student.name, 'start_date': leave.start_date.strftime('%d/%m/%Y'), 'reason': leave.reason} for leave in leaves]

def get_ai_insights(institution_id, class_id=None):
    """Calculates AI-driven insights like at-risk student counts."""
    from .models import Attendance, Student, ClassBatch
    insights = {}
    
    subquery = db.session.query(
        Attendance.student_id,
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
    ).join(Student).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)

    if class_id:
        subquery = subquery.filter(Student.class_batch_id == class_id)
        
    subquery = subquery.group_by(Attendance.student_id).subquery()
    
    at_risk_count = db.session.query(func.count(subquery.c.student_id)).filter(subquery.c.percentage.between(75, 80)).scalar()
    insights['at_risk_count'] = at_risk_count
    insights['anomaly_message'] = None # Placeholder for future anomaly detection
    return insights

def get_live_chart_data(institution_id, class_id=None):
    """Generates data for the weekly attendance percentage chart."""
    from .models import Attendance, Student, ClassBatch
    today = get_current_ist().date()
    labels, values = [], []
    
    total_students_query = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
    if class_id:
        total_students_query = total_students_query.filter(Student.class_batch_id == class_id)
    total_students = total_students_query.count()

    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime('%a'))
        
        present_query = db.session.query(func.count(Attendance.id)).join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == institution_id,
            Attendance.date == day,
            Attendance.status == 'present'
        )
        if class_id:
            present_query = present_query.filter(Student.class_batch_id == class_id)
        
        present_count = present_query.scalar() or 0
        percentage = (present_count / total_students * 100) if total_students > 0 else 0
        values.append(round(percentage, 1))
        
    return {'labels': labels, 'values': values}

def get_dashboard_statistics(institution_id, date, class_id=None):
    """A central function to correctly calculate total and present students."""
    from .models import Student, ClassBatch, Attendance
    
    students_query = db.session.query(Student.id).join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
    if class_id:
        students_query = students_query.filter(Student.class_batch_id == class_id)
    
    all_student_ids = [s_id for s_id, in students_query.all()]
    total_students = len(all_student_ids)

    present_today_count = 0
    if total_students > 0:
        present_student_ids_query = db.session.query(Attendance.student_id)\
            .filter(
                Attendance.student_id.in_(all_student_ids),
                Attendance.date == date,
                Attendance.status == 'present'
            ).distinct()
        present_today_count = present_student_ids_query.count()

    return {
        "total": total_students,
        "present": present_today_count
    }

def get_live_student_lists(institution_id, date, class_id=None):
    """Generates the 'All', 'Present', and 'Absent' student lists."""
    from .models import Student, ClassBatch, Attendance
    
    all_students_query = Student.query.options(joinedload(Student.class_batch))\
        .join(ClassBatch).filter(ClassBatch.institution_id == institution_id)
    if class_id:
        all_students_query = all_students_query.filter(Student.class_batch_id == class_id)
    
    all_students = all_students_query.order_by(Student.name).all()
    all_student_ids = [s.id for s in all_students]

    present_student_ids = set()
    if all_student_ids:
        present_query = db.session.query(Attendance.student_id).filter(
            Attendance.student_id.in_(all_student_ids),
            Attendance.date == date,
            Attendance.status == 'present'
        )
        present_student_ids = {row[0] for row in present_query.all()}

    all_list, present_list, absent_list = [], [], []
    for student in all_students:
        student_details = {
            'id': student.id,
            'name': student.name,
            'student_id': student.student_id,
            'class_name': student.class_batch.name if student.class_batch else 'N/A'
        }
        all_list.append(student_details)
        
        if student.id in present_student_ids:
            present_list.append(student_details)
        else:
            absent_list.append(student_details)

    return {
        "all": all_list,
        "present": present_list,
        "absent": absent_list
    }


# --- Decorators for Route Protection ---

def login_required(f):
    """Decorator to ensure a user is logged in before accessing a page."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            session.clear()
            flash('Your session is invalid, please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to ensure the logged-in user is an admin."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if g.user.role != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_or_admin_required(f):
    """Decorator to ensure the logged-in user is a teacher or an admin."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if g.user.role not in ['admin', 'teacher']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# --- Email Sending Functions ---

def send_email(subject, recipients, body):
    """Generic function to send an email."""
    try:
        msg = Message(subject, recipients=recipients, body=body)
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Error sending email: {e}")
        return False

def send_verification_email(user):
    """Sends an email with a 6-digit OTP for account verification."""
    otp = ''.join(random.choices(string.digits, k=6))
    user.otp = otp
    user.otp_expiry = get_current_ist() + timedelta(minutes=10)
    db.session.commit()
    body = f"Hello {user.username},\n\nYour One-Time Password (OTP) is: {otp}\n\nThis is valid for 10 minutes."
    return send_email("Verify Your Account", [user.email], body)

def send_password_reset_email(user):
    """Sends an email with a password reset link."""
    token = str(uuid.uuid4())
    user.password_reset_token = token
    user.reset_token_expiry = get_current_ist() + timedelta(hours=1)
    db.session.commit()
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    body = f"Hello {user.username},\n\nClick this link to reset your password:\n{reset_url}\n\nThis link will expire in one hour."
    return send_email("Password Reset Request", [user.email], body)

def send_username_email(user):
    """Sends an email containing the user's username."""
    body = f"Hello,\n\nYour username is: {user.username}"
    return send_email("Your Username", [user.email], body)


# --- Scheduled Tasks ---

def email_reports_job():
    """
    A background task that generates and emails a PDF attendance report
    to all admins of every institution.
    """
    # This job needs its own app context to work outside of a request
    from flask import current_app
    from fpdf import FPDF
    # Import models HERE, inside the function
    from .models import Institution, Attendance, Student, ClassBatch, User

    # Helper PDF class for the report
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 12)
            self.cell(0, 10, 'Weekly Attendance Report', 0, 1, 'C')
            self.ln(10)
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    with current_app.app_context():
        print(f"Running scheduled job at {get_current_ist()}...")
        try:
            institutions = Institution.query.all()
            for institution in institutions:
                admins = User.query.filter_by(institution_id=institution.id, role='admin').all()
                if not admins:
                    continue

                records = Attendance.query.join(Student).join(ClassBatch)\
                    .filter(ClassBatch.institution_id == institution.id)\
                    .order_by(Attendance.date, Student.name).all()

                # --- PDF Generation Logic ---
                pdf = PDF(orientation='L', unit='mm', format='A4')
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 10)
                headers = ['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status']
                col_widths = [60, 30, 60, 40, 30, 20]
                for i, header in enumerate(headers):
                    pdf.cell(col_widths[i], 10, header, border=1, align='C')
                pdf.ln()

                pdf.set_font('Helvetica', '', 9)
                if not records:
                    pdf.cell(sum(col_widths), 10, 'No attendance data for this period.', border=1, ln=1, align='C')
                else:
                    for record in records:
                        # Encode to latin-1 to handle potential unicode characters that FPDF doesn't support
                        pdf.cell(col_widths[0], 10, record.student.name.encode('latin-1', 'replace').decode('latin-1'), border=1)
                        pdf.cell(col_widths[1], 10, record.student.student_id.encode('latin-1', 'replace').decode('latin-1'), border=1)
                        pdf.cell(col_widths[2], 10, (record.student.class_batch.name if record.student.class_batch else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
                        pdf.cell(col_widths[3], 10, (record.subject.name if record.subject else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
                        pdf.cell(col_widths[4], 10, record.date.strftime('%Y-%m-%d'), border=1)
                        pdf.cell(col_widths[5], 10, record.status.capitalize(), border=1, ln=1)
                
                pdf_output = pdf.output(dest='S').encode('latin-1')
                
                recipient_emails = [admin.email for admin in admins]
                msg = Message(
                    f"Weekly Attendance Report for {institution.name}",
                    recipients=recipient_emails
                )
                msg.body = "Please find the weekly attendance report attached."
                msg.attach(
                    "attendance_report.pdf",
                    "application/pdf",
                    pdf_output
                )
                mail.send(msg)
                print(f"Report sent for institution: {institution.name}")
        except Exception as e:
            current_app.logger.error(f"Error in scheduled job: {e}")

