# -*- coding: utf-8 -*-
"""
This blueprint handles all student-related functionality, including
student management for teachers/admins and attendance viewing for students.
"""

# --- Standard Library Imports ---
import os
import base64
import csv
from io import BytesIO, StringIO
from datetime import datetime, timedelta

# --- Third-Party Library Imports ---
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, jsonify, Response, send_file, current_app)
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
import qrcode
from fpdf import FPDF

# --- Local Application Imports ---
from ..extensions import db
from ..models import Student, ClassBatch, Attendance, Subject, QRToken, MedicalLeave
from ..utils import (teacher_or_admin_required, login_required, get_current_ist,
                   allowed_file, admin_required)

# --- Blueprint Configuration ---
student_bp = Blueprint('student', __name__)


# --- Helper Class for PDF Generation ---
class PDF(FPDF):
    """Custom PDF class with a header and footer."""
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Attendance Report', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')


# ====================================================================
# STUDENT MANAGEMENT ROUTES (for Teachers/Admins)
# ====================================================================

@student_bp.route('/students')
@teacher_or_admin_required
def list_students():
    """Displays a paginated list of all students in the institution."""
    all_classes = ClassBatch.query.filter_by(
        institution_id=g.user.institution_id
    ).order_by(ClassBatch.name).all()
    
    selected_class_id = request.args.get('class_id', default=None, type=int)

    base_query = Student.query.join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id
    )

    if selected_class_id:
        base_query = base_query.filter(Student.class_batch_id == selected_class_id)
    
    page = request.args.get('page', 1, type=int)
    query = request.args.get('query', '')
    
    if query:
        search_term = f"%{query}%"
        base_query = base_query.filter(
            db.or_(
                Student.name.ilike(search_term),
                Student.student_id.ilike(search_term)
            )
        )
    
    students_pagination = base_query.order_by(Student.name).paginate(
        page=page, per_page=15, error_out=False
    )
    
    return render_template(
        'student/students.html',
        students=students_pagination,
        query=query,
        all_classes=all_classes,
        selected_class_id=selected_class_id
    )


@student_bp.route('/add_student', methods=['GET', 'POST'])
@teacher_or_admin_required
def add_student():
    """Handles the creation of new student records."""
    classes = ClassBatch.query.filter_by(
        institution_id=g.user.institution_id
    ).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        sid = request.form.get('student_id', '').strip()
        email = request.form.get('email', '').strip()
        cid = request.form.get('class_batch_id', '').strip()
        
        if not all([name, sid, cid]):
            flash('❌ Name, Student ID, and Class are required.', 'danger')
            return render_template('student/add_student.html', classes_batches=classes)

        # Check for duplicate student_id
        existing_student = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == sid
        ).first()
        
        if existing_student:
            flash(f'❌ Student ID "{sid}" is already taken in your institution.', 'danger')
            return render_template('student/add_student.html', classes_batches=classes)

        # Check if class exists and belongs to institution
        class_batch = db.session.get(ClassBatch, int(cid))
        if not class_batch or class_batch.institution_id != g.user.institution_id:
            flash('❌ Invalid class selected.', 'danger')
            return render_template('student/add_student.html', classes_batches=classes)

        # Create new student
        new_student = Student(
            name=name,
            student_id=sid,
            email=email,
            class_batch_id=int(cid)
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash(f'✅ Student "{name}" has been added successfully!', 'success')
        return redirect(url_for('student.list_students'))
    
    return render_template('student/add_student.html', classes_batches=classes)


@student_bp.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@teacher_or_admin_required
def edit_student(student_id):
    """Handles editing an existing student's details."""
    student = db.session.get(Student, student_id)
    
    if not student or student.class_batch.institution_id != g.user.institution_id:
        flash('❌ Student not found.', 'danger')
        return redirect(url_for('student.list_students'))

    classes = ClassBatch.query.filter_by(
        institution_id=g.user.institution_id
    ).all()

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        new_sid = request.form.get('student_id', '').strip()
        new_email = request.form.get('email', '').strip()
        new_cid = request.form.get('class_batch_id', '').strip()

        if not all([new_name, new_sid, new_cid]):
            flash('❌ Name, Student ID, and Class are required.', 'danger')
            return render_template('student/edit_student.html', student=student, classes_batches=classes)

        # Check for duplicate student_id
        existing_student = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == new_sid,
            Student.id != student_id
        ).first()
        
        if existing_student:
            flash(f'❌ Student ID "{new_sid}" is already taken by another student.', 'danger')
            return render_template('student/edit_student.html', student=student, classes_batches=classes)

        # Update student
        student.name = new_name
        student.student_id = new_sid
        student.email = new_email
        student.class_batch_id = int(new_cid)
        
        # Update associated user if exists
        if student.user:
            student.user.username = new_sid
            student.user.email = new_email

        db.session.commit()
        flash(f'✅ Student "{student.name}" updated successfully!', 'success')
        return redirect(url_for('student.list_students'))

    return render_template('student/edit_student.html', student=student, classes_batches=classes)


@student_bp.route('/delete_student/<int:student_id>', methods=['POST'])
@teacher_or_admin_required
def delete_student(student_id):
    """Handles the deletion of a student record."""
    student = db.session.get(Student, student_id)
    
    if student and student.class_batch and student.class_batch.institution_id == g.user.institution_id:
        name = student.name
        db.session.delete(student)
        db.session.commit()
        flash(f'✅ Student "{name}" has been deleted successfully.', 'success')
    else:
        flash('❌ Student not found or you do not have permission to delete.', 'danger')
    
    return redirect(url_for('student.list_students'))


@student_bp.route('/import_students', methods=['GET', 'POST'])
@admin_required
def import_students():
    """Allows bulk import of students from a CSV file."""
    if request.method == 'POST':
        if 'student_csv' not in request.files:
            flash('❌ No file selected', 'danger')
            return redirect(request.url)
            
        file = request.files['student_csv']
        
        if file.filename == '':
            flash('❌ No file selected', 'danger')
            return redirect(request.url)
            
        if not file.filename.endswith('.csv'):
            flash('❌ Please upload a CSV file', 'danger')
            return redirect(request.url)
        
        try:
            # Read CSV file
            stream = StringIO(
                file.stream.read().decode("UTF8"),
                newline=None
            )
            csv_reader = csv.DictReader(stream)
            
            if not csv_reader or not csv_reader.fieldnames:
                flash('❌ CSV file is empty', 'danger')
                return redirect(request.url)
            
            # Validate headers
            required_fields = {'name', 'student_id', 'email', 'class_batch_id'}
            if not required_fields.issubset(set(csv_reader.fieldnames or [])):
                flash('❌ CSV must have: name, student_id, email, class_batch_id', 'danger')
                return redirect(request.url)
            
            imported_count = 0
            skipped_count = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    # Get values
                    name = row.get('name', '').strip()
                    student_id = row.get('student_id', '').strip()
                    email = row.get('email', '').strip()
                    class_batch_id = row.get('class_batch_id', '').strip()
                    
                    # Validate required fields
                    if not all([name, student_id, class_batch_id]):
                        errors.append(f"Row {row_num}: Missing required fields")
                        skipped_count += 1
                        continue
                    
                    # Validate email format
                    if email and ('@' not in email or '.' not in email):
                        errors.append(f"Row {row_num}: Invalid email format")
                        skipped_count += 1
                        continue
                    
                    # Check if class exists
                    try:
                        class_batch = db.session.get(ClassBatch, int(class_batch_id))
                    except (ValueError, TypeError):
                        errors.append(f"Row {row_num}: Invalid class ID")
                        skipped_count += 1
                        continue
                    
                    if not class_batch or class_batch.institution_id != g.user.institution_id:
                        errors.append(f"Row {row_num}: Class not found")
                        skipped_count += 1
                        continue
                    
                    # Check for duplicate student_id
                    existing = Student.query.filter_by(student_id=student_id).first()
                    if existing:
                        errors.append(f"Row {row_num}: Student ID already exists")
                        skipped_count += 1
                        continue
                    
                    # Check for duplicate email
                    if email:
                        existing_email = Student.query.filter_by(email=email).first()
                        if existing_email:
                            errors.append(f"Row {row_num}: Email already registered")
                            skipped_count += 1
                            continue
                    
                    # Create student
                    new_student = Student(
                        name=name,
                        student_id=student_id,
                        email=email,
                        class_batch_id=int(class_batch_id)
                    )
                    db.session.add(new_student)
                    imported_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    skipped_count += 1
            
            # Commit all changes
            db.session.commit()
            
            # Flash result messages
            if imported_count > 0:
                flash(f'✅ Successfully imported {imported_count} student(s)!', 'success')
            
            if skipped_count > 0:
                error_msg = f'⚠️ Skipped {skipped_count} row(s). '
                if errors:
                    error_msg += 'Errors: ' + ' | '.join(errors[:5])
                    if len(errors) > 5:
                        error_msg += f'... and {len(errors) - 5} more'
                flash(error_msg, 'warning')
            
            if imported_count == 0 and skipped_count > 0:
                flash('❌ No students were imported. Please check your CSV file.', 'danger')
            
            return redirect(url_for('student.list_students'))
        
        except Exception as e:
            current_app.logger.error(f"CSV import error: {str(e)}")
            flash(f'❌ Error processing CSV: {str(e)}', 'danger')
            return redirect(request.url)
    
    return render_template('student/import_students.html')


# ====================================================================
# STUDENT ATTENDANCE VIEWING ROUTES
# ====================================================================

@student_bp.route('/mark_attendance', methods=['GET'])
@login_required
def mark_attendance():
    """View student's own attendance records"""
    
    if g.user.role != 'student':
        flash('❌ Only students can view their attendance.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    # Get current student profile
    student = g.user.student_profile
    if not student:
        flash('❌ Student profile not found', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    # Get filter parameters
    subject_id = request.args.get('subject_id', type=int)
    from_date = request.args.get('from_date')
    
    # Build query
    query = Attendance.query.filter_by(student_id=student.id)
    
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    
    if from_date:
        try:
            date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date >= date_obj)
        except (ValueError, TypeError):
            from_date = None
    
    # Get records sorted by date (newest first)
    attendance_records = query.order_by(Attendance.date.desc()).all()
    
    # Calculate statistics
    total_records = Attendance.query.filter_by(student_id=student.id).count()
    total_present = Attendance.query.filter_by(
        student_id=student.id,
        status='present'
    ).count()
    total_absent = Attendance.query.filter_by(
        student_id=student.id,
        status='absent'
    ).count()
    total_leave = Attendance.query.filter_by(
        student_id=student.id,
        status='leave'
    ).count()
    
    # Calculate percentage
    attendance_percentage = (total_present / total_records * 100) if total_records > 0 else 0
    
    # Get all subjects for filter dropdown
    subjects = Subject.query.all()
    
    return render_template(
        'student/mark_attendance.html',
        attendance_records=attendance_records,
        subjects=subjects,
        selected_subject=subject_id,
        from_date=from_date,
        total_present=total_present,
        total_absent=total_absent,
        total_leave=total_leave,
        attendance_percentage=round(attendance_percentage, 1)
    )


@student_bp.route('/attendance_history')
@teacher_or_admin_required
def attendance_history():
    """Displays a paginated list of all attendance records."""
    page = request.args.get('page', 1, type=int)
    selected_date_str = request.args.get('date')

    base_query = Attendance.query.options(
        joinedload(Attendance.subject)
    ).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id
    )

    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            base_query = base_query.filter(Attendance.date == selected_date)
        except (ValueError, TypeError):
            flash('❌ Invalid date format used for filtering.', 'danger')
            selected_date_str = None
    
    records = base_query.order_by(
        desc(Attendance.date),
        desc(Attendance.created_at)
    ).paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'student/attendance_history.html',
        records=records,
        selected_date=selected_date_str
    )


# ====================================================================
# QR CODE ATTENDANCE ROUTES
# ====================================================================

@student_bp.route('/api/generate_qr', methods=['POST'])
@teacher_or_admin_required
def generate_qr():
    """API endpoint to generate a short-lived QR code for attendance."""
    data = request.json or {}
    class_id = data.get('class_batch_id')
    subject_id = data.get('subject_id')
    
    if not class_id or not subject_id:
        return jsonify({'error': '❌ Class and Subject are required.'}), 400
    
    try:
        # Verify class belongs to institution
        class_batch = db.session.get(ClassBatch, int(class_id))
        if not class_batch or class_batch.institution_id != g.user.institution_id:
            return jsonify({'error': '❌ Invalid class selection.'}), 400
        
        # Create QR token (valid for 2 minutes)
        token = QRToken(
            class_batch_id=int(class_id),
            subject_id=int(subject_id),
            expiry_time=get_current_ist() + timedelta(minutes=2)
        )
        db.session.add(token)
        db.session.commit()
        
        # Generate QR code
        scan_url = url_for(
            'student.scan_attendance_token',
            token=token.token,
            _external=True
        )
        img = qrcode.make(scan_url)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        return jsonify({'qr_image': img_str}), 200
    
    except Exception as e:
        current_app.logger.error(f"Error generating QR code: {e}")
        return jsonify({'error': '❌ Failed to generate QR code.'}), 500


@student_bp.route('/scan_attendance/<token>')
@login_required
def scan_attendance_token(token):
    """Handles the attendance marking when a student scans a QR code."""
    if g.user.role != 'student':
        flash('❌ Only students can scan QR codes.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    # Get QR token
    qr_token = QRToken.query.filter_by(token=token).first()
    
    if not qr_token:
        flash('❌ QR code not found.', 'danger')
        return redirect(url_for('student.mark_attendance'))
    
    # Check if expired
    if get_current_ist() > qr_token.expiry_time:
        flash('❌ QR code has expired.', 'danger')
        db.session.delete(qr_token)
        db.session.commit()
        return redirect(url_for('student.mark_attendance'))
    
    # Get student
    student = g.user.student_profile
    if not student or student.class_batch_id != qr_token.class_batch_id:
        flash('❌ You are not in the correct class for this QR code.', 'danger')
        return redirect(url_for('student.mark_attendance'))
    
    # Mark attendance
    today = get_current_ist().date()
    record = Attendance.query.filter_by(
        student_id=student.id,
        date=today,
        subject_id=qr_token.subject_id
    ).first()
    
    if record:
        record.status = 'present'
        record.marked_by = 'qr'
        flash('✅ Attendance updated to present.', 'success')
    else:
        new_record = Attendance(
            student_id=student.id,
            subject_id=qr_token.subject_id,
            date=today,
            status='present',
            marked_by='qr'
        )
        db.session.add(new_record)
        flash('✅ Attendance marked successfully!', 'success')
    
    db.session.delete(qr_token)
    db.session.commit()
    
    return redirect(url_for('student.mark_attendance'))


# ====================================================================
# STUDENT-FACING ROUTES
# ====================================================================

@student_bp.route('/my_attendance')
@login_required
def my_attendance():
    """Displays the current student's own attendance records."""
    if g.user.role != 'student':
        flash("❌ This page is only for students.", "warning")
        return redirect(url_for('dashboard.dashboard'))

    if g.user.student_profile:
        records = g.user.student_profile.attendances.order_by(desc(Attendance.date)).all()
        return render_template(
            'student/my_attendance.html',
            records=records,
            student=g.user.student_profile
        )
    else:
        return render_template('student/my_attendance.html', records=None, student=None)


@student_bp.route('/check_attendance/', methods=['GET', 'POST'])
def check_attendance():
    """Public page for anyone to check a student's attendance by their ID."""
    student = None
    attendance_records = None
    student_id_searched = ""

    if request.method == 'POST':
        student_id_searched = request.form.get('student_id', '').strip()
        if student_id_searched:
            student = Student.query.filter_by(student_id=student_id_searched).first()
            if student:
                attendance_records = student.attendances.order_by(
                    desc(Attendance.date)
                ).paginate(page=1, per_page=15, error_out=False)
            else:
                flash(f'⚠️ No student found with ID: {student_id_searched}', 'warning')
    
    return render_template(
        'student/check_attendance.html',
        student=student,
        attendance_records=attendance_records,
        student_id_searched=student_id_searched
    )


# ====================================================================
# LEAVE MANAGEMENT ROUTES
# ====================================================================

@student_bp.route('/apply-leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    """Allows a student to apply for medical leave."""
    if g.user.role != 'student' or not g.user.student_profile:
        flash('❌ Only students can apply for leave.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        try:
            start_date = datetime.strptime(
                request.form.get('start_date', ''),
                '%Y-%m-%d'
            ).date()
            end_date = datetime.strptime(
                request.form.get('end_date', ''),
                '%Y-%m-%d'
            ).date()
            reason = request.form.get('reason', '').strip()

            # Validate fields
            if not all([start_date, end_date, reason]):
                flash('❌ All fields are required.', 'danger')
                return render_template(
                    'student/apply_leave.html',
                    today=datetime.today().strftime('%Y-%m-%d')
                )

            # Validate dates
            if start_date > end_date:
                flash('❌ End date must be after start date.', 'danger')
                return render_template(
                    'student/apply_leave.html',
                    today=datetime.today().strftime('%Y-%m-%d')
                )

            # Create leave request
            leave = MedicalLeave(
                student_id=g.user.student_profile.id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                institution_id=g.user.institution_id,
                status='pending'
            )
            db.session.add(leave)
            db.session.commit()
            flash('✅ Leave request submitted successfully!', 'success')
            return redirect(url_for('student.view_leaves'))
        
        except (ValueError, TypeError):
            flash('❌ Invalid date format.', 'danger')
            return render_template(
                'student/apply_leave.html',
                today=datetime.today().strftime('%Y-%m-%d')
            )
    
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('student/apply_leave.html', today=today)


@student_bp.route('/leaves')
@login_required
def view_leaves():
    """View student's leave history."""
    if g.user.role != 'student' or not g.user.student_profile:
        flash('❌ Only students can view their leaves.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    leaves = MedicalLeave.query.filter_by(
        student_id=g.user.student_profile.id
    ).order_by(desc(MedicalLeave.created_at)).all()
    
    # Calculate stats
    pending_count = MedicalLeave.query.filter_by(
        student_id=g.user.student_profile.id,
        status='pending'
    ).count()
    
    approved_count = MedicalLeave.query.filter_by(
        student_id=g.user.student_profile.id,
        status='approved'
    ).count()
    
    return render_template(
        'student/my_leaves.html',
        leaves=leaves,
        pending_count=pending_count,
        approved_count=approved_count
    )


@student_bp.route('/add_medical_leave/<int:student_id>', methods=['GET', 'POST'])
@teacher_or_admin_required
def add_medical_leave(student_id):
    """Allows teachers/admins to add medical leave for a student."""
    student = db.session.get(Student, student_id)
    
    if not student or student.class_batch.institution_id != g.user.institution_id:
        flash('❌ Student not found.', 'danger')
        return redirect(url_for('student.list_students'))
    
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(
                request.form.get('start_date', ''),
                '%Y-%m-%d'
            ).date()
            end_date = datetime.strptime(
                request.form.get('end_date', ''),
                '%Y-%m-%d'
            ).date()
            reason = request.form.get('reason', '').strip()
            
            # Validate
            if not all([start_date, end_date, reason]):
                flash('❌ All fields are required.', 'danger')
                return render_template('student/add_leave.html', student=student)

            if start_date > end_date:
                flash('❌ End date must be after start date.', 'danger')
                return render_template('student/add_leave.html', student=student)

            # Create leave
            leave = MedicalLeave(
                student_id=student_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                institution_id=g.user.institution_id,
                status='approved'
            )
            db.session.add(leave)
            db.session.commit()
            flash('✅ Medical leave added successfully.', 'success')
            return redirect(url_for('student.student_profile_view', student_id=student_id))
        
        except (ValueError, TypeError):
            flash('❌ Invalid date format.', 'danger')
    
    return render_template('student/add_leave.html', student=student)


@student_bp.route('/profile/<int:student_id>')
@teacher_or_admin_required
def student_profile_view(student_id):
    """
    Displays a detailed profile page for a specific student,
    viewable by a teacher or admin.
    """
    student = db.session.get(Student, student_id)
    
    if not student:
        flash('❌ Student not found.', 'danger')
        return redirect(url_for('student.list_students'))
    
    if not student.class_batch:
        flash(f'⚠️ Student {student.name} is not assigned to a class.', 'warning')
        return redirect(url_for('student.list_students'))
    
    if student.class_batch.institution_id != g.user.institution_id:
        flash('❌ You do not have permission to view this student.', 'danger')
        return redirect(url_for('student.list_students'))
    
    leave_requests = MedicalLeave.query.filter_by(
        student_id=student.id
    ).order_by(desc(MedicalLeave.created_at)).all()
    
    return render_template(
        'student/student_profile.html',
        student=student,
        leave_requests=leave_requests
    )


@student_bp.route('/handle_leave/<int:leave_id>/<action>', methods=['POST'])
@teacher_or_admin_required
def handle_leave(leave_id, action):
    """Handles approving or denying a leave request."""
    leave = db.session.get(MedicalLeave, leave_id)
    
    if not leave or leave.student.class_batch.institution_id != g.user.institution_id:
        flash("❌ Leave request not found.", "danger")
        return redirect(url_for('dashboard.dashboard'))

    if action == 'approve':
        leave.status = 'approved'
        flash(f"✅ Leave for {leave.student.name} approved.", "success")
    elif action == 'deny':
        leave.status = 'denied'
        flash(f"❌ Leave for {leave.student.name} denied.", "warning")
    else:
        flash("❌ Invalid action.", "danger")
        return redirect(url_for('dashboard.dashboard'))
    
    db.session.commit()
    return redirect(url_for('dashboard.dashboard'))


# ====================================================================
# EXPORT ROUTES
# ====================================================================

@student_bp.route('/export/csv')
@teacher_or_admin_required
def export_csv():
    """Exports all attendance records to a CSV file."""
    try:
        records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id
        ).order_by(Attendance.date, Student.name).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([
            'Student Name', 'Student ID', 'Class', 'Subject',
            'Date', 'Status', 'Marked At'
        ])
        
        # Write data
        for record in records:
            writer.writerow([
                record.student.name,
                record.student.student_id,
                record.student.class_batch.name if record.student.class_batch else 'N/A',
                record.subject.name if record.subject else 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.status.capitalize(),
                record.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        csv_output = output.getvalue()
        
        return Response(
            csv_output,
            mimetype="text/csv",
            headers={
                "Content-disposition": "attachment; filename=attendance_report.csv"
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting CSV: {e}")
        flash('❌ Error generating CSV report.', 'danger')
        return redirect(url_for('dashboard.dashboard'))


@student_bp.route('/export/pdf')
@teacher_or_admin_required
def export_pdf():
    """Exports all attendance records to a PDF file."""
    try:
        records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id
        ).order_by(Attendance.date, Student.name).all()

        # Create PDF
        pdf = PDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        headers = ['Student Name', 'Student ID', 'Class', 'Subject', 'Date', 'Status']
        col_widths = [60, 30, 60, 40, 30, 20]

        # Write headers
        pdf.set_font('Helvetica', 'B', 10)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, border=1, align='C')
        pdf.ln()

        # Write data
        pdf.set_font('Helvetica', '', 9)
        if not records:
            pdf.cell(
                sum(col_widths),
                10,
                'No attendance data found.',
                border=1,
                ln=1,
                align='C'
            )
        else:
            for record in records:
                # Safe encoding for non-Latin characters
                safe_name = record.student.name.encode('latin-1', 'replace').decode('latin-1')
                safe_id = record.student.student_id.encode('latin-1', 'replace').decode('latin-1')
                safe_class = (
                    record.student.class_batch.name if record.student.class_batch else 'N/A'
                ).encode('latin-1', 'replace').decode('latin-1')
                safe_subject = (
                    record.subject.name if record.subject else 'N/A'
                ).encode('latin-1', 'replace').decode('latin-1')
                
                pdf.cell(col_widths[0], 10, safe_name, border=1)
                pdf.cell(col_widths[1], 10, safe_id, border=1)
                pdf.cell(col_widths[2], 10, safe_class, border=1)
                pdf.cell(col_widths[3], 10, safe_subject, border=1)
                pdf.cell(col_widths[4], 10, record.date.strftime('%Y-%m-%d'), border=1)
                pdf.cell(col_widths[5], 10, record.status.capitalize(), border=1, ln=1)

        pdf_output = pdf.output(dest='S').encode('latin-1')
        
        return send_file(
            BytesIO(pdf_output),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='attendance_report.pdf'
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting PDF: {e}")
        flash('❌ Error generating PDF report.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
