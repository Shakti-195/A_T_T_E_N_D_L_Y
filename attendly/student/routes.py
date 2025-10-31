# -*- coding: utf-8 -*-
"""
Student Routes - Student management, attendance viewing, and medical leaves
Version: 3.0 - Complete, Corrected & Production Ready
"""

import os
import base64
import csv
import logging
from io import BytesIO, StringIO
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, jsonify, Response, send_file, current_app)
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
import qrcode
from fpdf import FPDF

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..extensions import db
from ..models import Student, ClassBatch, Attendance, Subject, QRToken, MedicalLeave
from ..utils import (teacher_or_admin_required, login_required, get_current_ist,
                   allowed_file, admin_required)

logger = logging.getLogger(__name__)
student_bp = Blueprint('student', __name__)


# ====================================================================
# PDF HELPER CLASS
# ====================================================================

class PDF(FPDF):
    """Custom PDF class with header and footer"""
    def header(self):
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Attendance Report', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')


# ====================================================================
# STUDENT MANAGEMENT ROUTES (Teachers/Admins)
# ====================================================================

@student_bp.route('/students')
@teacher_or_admin_required
def list_students():
    """Display paginated list of all students"""
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
    
    total_students = Student.query.join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id
    ).count()
    
    return render_template(
        'student/students.html',
        students=students_pagination,
        query=query,
        all_classes=all_classes,
        selected_class_id=selected_class_id,
        total_students=total_students,
        linked_accounts=0
    )


@student_bp.route('/add_student', methods=['GET', 'POST'])
@teacher_or_admin_required
def add_student():
    """Create new student record"""
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
        
        existing = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == sid
        ).first()
        
        if existing:
            flash(f'❌ Student ID "{sid}" already exists.', 'danger')
            return render_template('student/add_student.html', classes_batches=classes)
        
        class_batch = db.session.get(ClassBatch, int(cid))
        if not class_batch or class_batch.institution_id != g.user.institution_id:
            flash('❌ Invalid class selected.', 'danger')
            return render_template('student/add_student.html', classes_batches=classes)
        
        new_student = Student(
            name=name,
            student_id=sid,
            email=email if email else None,
            class_batch_id=int(cid)
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash(f'✅ Student "{name}" added successfully!', 'success')
        return redirect(url_for('student.list_students'))
    
    return render_template('student/add_student.html', classes_batches=classes)


@student_bp.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@teacher_or_admin_required
def edit_student(student_id):
    """Edit student details"""
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
            flash('❌ Name, Student ID, and Class required.', 'danger')
            return render_template('student/edit_student.html', student=student, classes_batches=classes)
        
        existing = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == new_sid,
            Student.id != student_id
        ).first()
        
        if existing:
            flash(f'❌ Student ID "{new_sid}" already taken.', 'danger')
            return render_template('student/edit_student.html', student=student, classes_batches=classes)
        
        student.name = new_name
        student.student_id = new_sid
        student.email = new_email if new_email else None
        student.class_batch_id = int(new_cid)
        
        db.session.commit()
        flash(f'✅ Student updated!', 'success')
        return redirect(url_for('student.list_students'))
    
    return render_template('student/edit_student.html', student=student, classes_batches=classes)


@student_bp.route('/delete_student/<int:student_id>', methods=['POST'])
@teacher_or_admin_required
def delete_student(student_id):
    """Delete student record"""
    student = db.session.get(Student, student_id)
    
    if student and student.class_batch and student.class_batch.institution_id == g.user.institution_id:
        name = student.name
        db.session.delete(student)
        db.session.commit()
        flash(f'✅ Student "{name}" deleted.', 'success')
    else:
        flash('❌ Student not found or no permission.', 'danger')
    
    return redirect(url_for('student.list_students'))


@student_bp.route('/import_students', methods=['GET', 'POST'])
@admin_required
def import_students():
    """Bulk import students from CSV"""
    if request.method == 'POST':
        if 'student_csv' not in request.files:
            flash('❌ No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['student_csv']
        
        if file.filename == '' or not file.filename.endswith('.csv'):
            flash('❌ Please upload a CSV file', 'danger')
            return redirect(request.url)
        
        try:
            stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)
            
            if not csv_reader or not csv_reader.fieldnames:
                flash('❌ CSV file is empty', 'danger')
                return redirect(request.url)
            
            required_fields = {'name', 'student_id', 'email', 'class_batch_id'}
            if not required_fields.issubset(set(csv_reader.fieldnames or [])):
                flash('❌ CSV must have: name, student_id, email, class_batch_id', 'danger')
                return redirect(request.url)
            
            imported_count = 0
            skipped_count = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    name = row.get('name', '').strip()
                    student_id = row.get('student_id', '').strip()
                    email = row.get('email', '').strip()
                    class_batch_id = row.get('class_batch_id', '').strip()
                    
                    if not all([name, student_id, class_batch_id]):
                        errors.append(f"Row {row_num}: Missing required fields")
                        skipped_count += 1
                        continue
                    
                    if email and ('@' not in email):
                        errors.append(f"Row {row_num}: Invalid email")
                        skipped_count += 1
                        continue
                    
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
                    
                    if Student.query.filter_by(student_id=student_id).first():
                        errors.append(f"Row {row_num}: Student ID exists")
                        skipped_count += 1
                        continue
                    
                    new_student = Student(
                        name=name,
                        student_id=student_id,
                        email=email if email else None,
                        class_batch_id=int(class_batch_id)
                    )
                    db.session.add(new_student)
                    imported_count += 1
                
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    skipped_count += 1
            
            db.session.commit()
            
            if imported_count > 0:
                flash(f'✅ Imported {imported_count} student(s)!', 'success')
            if skipped_count > 0:
                flash(f'⚠️ Skipped {skipped_count} row(s)', 'warning')
            
            return redirect(url_for('student.list_students'))
        
        except Exception as e:
            logger.error(f"CSV import error: {str(e)}")
            flash(f'❌ Error: {str(e)}', 'danger')
            return redirect(request.url)
    
    return render_template('student/import_students.html')


@student_bp.route('/profile/<int:student_id>')
@teacher_or_admin_required
def student_profile_view(student_id):
    """View student profile with leave history"""
    student = db.session.get(Student, student_id)
    
    if not student:
        flash('❌ Student not found.', 'danger')
        return redirect(url_for('student.list_students'))
    
    if not student.class_batch:
        flash(f'⚠️ Student not assigned to class.', 'warning')
        return redirect(url_for('student.list_students'))
    
    if student.class_batch.institution_id != g.user.institution_id:
        flash('❌ No permission.', 'danger')
        return redirect(url_for('student.list_students'))
    
    leave_requests = MedicalLeave.query.filter_by(
        student_id=student.id
    ).order_by(desc(MedicalLeave.created_at)).all()
    
    return render_template(
        'student/student_profile.html',
        student=student,
        leave_requests=leave_requests
    )


# ====================================================================
# ATTENDANCE ROUTES
# ====================================================================

@student_bp.route('/mark_attendance', methods=['GET'])
@login_required
def mark_attendance():
    """View student's attendance"""
    if g.user.role != 'student':
        flash('❌ Only students.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    student = g.user.student_profile
    if not student:
        flash('❌ Student profile not found', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    subject_id = request.args.get('subject_id', type=int)
    from_date = request.args.get('from_date')
    
    query = Attendance.query.filter_by(student_id=student.id)
    
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    
    if from_date:
        try:
            date_obj = datetime.strptime(from_date, '%Y-%m-%d').date()
            query = query.filter(Attendance.date >= date_obj)
        except (ValueError, TypeError):
            from_date = None
    
    attendance_records = query.order_by(Attendance.date.desc()).all()
    
    total_records = Attendance.query.filter_by(student_id=student.id).count()
    total_present = Attendance.query.filter_by(student_id=student.id, status='present').count()
    total_absent = Attendance.query.filter_by(student_id=student.id, status='absent').count()
    total_leave = Attendance.query.filter_by(student_id=student.id, status='leave').count()
    
    attendance_percentage = (total_present / total_records * 100) if total_records > 0 else 0
    
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
    """View all attendance records"""
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
            flash('❌ Invalid date format.', 'danger')
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
# QR CODE ATTENDANCE
# ====================================================================

@student_bp.route('/api/generate_qr', methods=['POST'])
@teacher_or_admin_required
def generate_qr():
    """Generate QR code"""
    data = request.json or {}
    class_id = data.get('class_batch_id')
    subject_id = data.get('subject_id')
    
    if not class_id or not subject_id:
        return jsonify({'error': '❌ Class and Subject required.'}), 400
    
    try:
        class_batch = db.session.get(ClassBatch, int(class_id))
        if not class_batch or class_batch.institution_id != g.user.institution_id:
            return jsonify({'error': '❌ Invalid class.'}), 400
        
        token = QRToken(
            class_batch_id=int(class_id),
            subject_id=int(subject_id),
            expiry_time=get_current_ist() + timedelta(minutes=2)
        )
        db.session.add(token)
        db.session.commit()
        
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
        logger.error(f"QR error: {e}")
        return jsonify({'error': '❌ Failed.'}), 500


@student_bp.route('/scan_attendance/<token>')
@login_required
def scan_attendance_token(token):
    """Mark attendance by QR"""
    if g.user.role != 'student':
        flash('❌ Only students.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    qr_token = QRToken.query.filter_by(token=token).first()
    
    if not qr_token:
        flash('❌ QR not found.', 'danger')
        return redirect(url_for('student.mark_attendance'))
    
    if get_current_ist() > qr_token.expiry_time:
        flash('❌ QR expired.', 'danger')
        db.session.delete(qr_token)
        db.session.commit()
        return redirect(url_for('student.mark_attendance'))
    
    student = g.user.student_profile
    if not student or student.class_batch_id != qr_token.class_batch_id:
        flash('❌ Not in correct class.', 'danger')
        return redirect(url_for('student.mark_attendance'))
    
    today = get_current_ist().date()
    record = Attendance.query.filter_by(
        student_id=student.id,
        date=today,
        subject_id=qr_token.subject_id
    ).first()
    
    if record:
        record.status = 'present'
        record.marked_by = 'qr'
        flash('✅ Updated!', 'success')
    else:
        new_record = Attendance(
            student_id=student.id,
            subject_id=qr_token.subject_id,
            date=today,
            status='present',
            marked_by='qr'
        )
        db.session.add(new_record)
        flash('✅ Marked!', 'success')
    
    db.session.delete(qr_token)
    db.session.commit()
    
    return redirect(url_for('student.mark_attendance'))


# ====================================================================
# STUDENT ROUTES
# ====================================================================

@student_bp.route('/my_attendance')
@login_required
def my_attendance():
    """View own attendance"""
    if g.user.role != 'student':
        flash("❌ Only for students.", "warning")
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
    """Check student attendance publicly"""
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
                flash(f'⚠️ No student: {student_id_searched}', 'warning')
    
    return render_template(
        'student/check_attendance.html',
        student=student,
        attendance_records=attendance_records,
        student_id_searched=student_id_searched
    )


# ====================================================================
# LEAVE MANAGEMENT
# ====================================================================

@student_bp.route('/apply-leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    """Apply for medical leave"""
    if g.user.role != 'student' or not g.user.student_profile:
        flash('❌ Only students.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    if request.method == 'POST':
        try:
            start_date_str = request.form.get('start_date', '').strip()
            end_date_str = request.form.get('end_date', '').strip()
            reason = request.form.get('reason', '').strip()
            
            if not all([start_date_str, end_date_str, reason]):
                flash('❌ All fields required.', 'danger')
                return redirect(url_for('student.apply_leave'))
            
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            today = datetime.now().date()
            if start_date > end_date:
                flash('❌ End date must be after start.', 'danger')
                return redirect(url_for('student.apply_leave'))
            
            if start_date < today:
                flash('❌ Cannot apply for past.', 'danger')
                return redirect(url_for('student.apply_leave'))
            
            if len(reason) < 10 or len(reason) > 500:
                flash('❌ Reason: 10-500 chars.', 'danger')
                return redirect(url_for('student.apply_leave'))
            
            existing = MedicalLeave.query.filter_by(
                student_id=g.user.student_profile.id,
                start_date=start_date,
                end_date=end_date,
                status='pending'
            ).first()
            
            if existing:
                flash('❌ Duplicate pending.', 'warning')
                return redirect(url_for('student.apply_leave'))
            
            leave = MedicalLeave(
                student_id=g.user.student_profile.id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                status='pending',
                institution_id=g.user.institution_id
            )
            
            db.session.add(leave)
            db.session.commit()
            
            flash('✅ Leave submitted!', 'success')
            return redirect(url_for('student.view_leaves'))
        
        except (ValueError, TypeError):
            flash('❌ Invalid date.', 'danger')
            return redirect(url_for('student.apply_leave'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Leave error: {str(e)}")
            flash(f'❌ Error: {str(e)}', 'danger')
            return redirect(url_for('student.apply_leave'))
    
    return render_template('student/apply_leave.html')


@student_bp.route('/leaves')
@login_required
def view_leaves():
    """View leave history"""
    if g.user.role != 'student' or not g.user.student_profile:
        flash('❌ Only students.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
    
    leaves = MedicalLeave.query.filter_by(
        student_id=g.user.student_profile.id
    ).order_by(desc(MedicalLeave.created_at)).all()
    
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
    """Admin adds leave"""
    student = db.session.get(Student, student_id)
    
    if not student or student.class_batch.institution_id != g.user.institution_id:
        flash('❌ Student not found.', 'danger')
        return redirect(url_for('student.list_students'))
    
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form.get('start_date', ''), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date', ''), '%Y-%m-%d').date()
            reason = request.form.get('reason', '').strip()
            
            if not all([start_date, end_date, reason]):
                flash('❌ All required.', 'danger')
                return render_template('student/add_leave.html', student=student)
            
            if start_date > end_date:
                flash('❌ End after start.', 'danger')
                return render_template('student/add_leave.html', student=student)
            
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
            flash('✅ Leave added!', 'success')
            return redirect(url_for('student.student_profile_view', student_id=student_id))
        
        except (ValueError, TypeError):
            flash('❌ Invalid date.', 'danger')
    
    return render_template('student/add_leave.html', student=student)


@student_bp.route('/handle_leave/<int:leave_id>/<action>', methods=['POST'])
@teacher_or_admin_required
def handle_leave(leave_id, action):
    """Approve/deny leave"""
    leave = db.session.get(MedicalLeave, leave_id)
    
    if not leave or leave.student.class_batch.institution_id != g.user.institution_id:
        flash("❌ Leave not found.", "danger")
        return redirect(url_for('dashboard.dashboard'))
    
    if action == 'approve':
        leave.status = 'approved'
        flash(f"✅ Approved.", "success")
    elif action == 'deny':
        leave.status = 'denied'
        flash(f"❌ Denied.", "warning")
    else:
        flash("❌ Invalid action.", "danger")
        return redirect(url_for('dashboard.dashboard'))
    
    db.session.commit()
    return redirect(url_for('dashboard.dashboard'))


# ====================================================================
# EXPORT ROUTES - ✅ WORKING
# ====================================================================

@student_bp.route('/export/csv')
@teacher_or_admin_required
def export_csv():
    """Export to CSV"""
    try:
        inst_id = g.user.institution_id
        
        records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        ).order_by(Attendance.date.desc()).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Student Name', 'Student ID', 'Class', 'Subject', 'Date', 'Status', 'Marked At'])
        
        for record in records:
            writer.writerow([
                record.student.name or 'N/A',
                record.student.student_id or 'N/A',
                record.student.class_batch.name if record.student.class_batch else 'N/A',
                record.subject.name if record.subject else 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.status.capitalize(),
                record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else 'N/A'
            ])
        
        csv_output = output.getvalue()
        output.close()
        
        logger.info(f"CSV export: {inst_id}")
        
        return send_file(
            BytesIO(csv_output.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    
    except Exception as e:
        logger.error(f"CSV error: {str(e)}")
        flash(f'❌ Export failed: {str(e)}', 'danger')
        return redirect(url_for('dashboard.dashboard'))


@student_bp.route('/export/excel')
@teacher_or_admin_required
def export_excel():
    """Export to Excel"""
    try:
        inst_id = g.user.institution_id
        
        records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        ).order_by(Attendance.date.desc()).limit(500).all()
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"
        
        headers = ['Student Name', 'Student ID', 'Class', 'Subject', 'Date', 'Status', 'Recorded At']
        ws.append(headers)
        
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        header_font = Font(color='FFFFFF', bold=True, size=12)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        light_fill = PatternFill(start_color='D9E1F2', end_color='D9E1F2', fill_type='solid')
        data_font = Font(size=11)
        
        for idx, record in enumerate(records, start=2):
            ws.append([
                record.student.name or 'N/A',
                record.student.student_id or 'N/A',
                record.student.class_batch.name if record.student.class_batch else 'N/A',
                record.subject.name if record.subject else 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.status.capitalize(),
                record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else 'N/A'
            ])
            
            if idx % 2 == 0:
                for cell in ws[idx]:
                    cell.fill = light_fill
            
            for cell in ws[idx]:
                cell.border = border
                cell.font = data_font
        
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 15
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 12
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 20
        
        ws.freeze_panes = 'A2'
        
        excel_io = BytesIO()
        wb.save(excel_io)
        excel_io.seek(0)
        
        logger.info(f"Excel export: {inst_id}")
        
        return send_file(
            excel_io,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    
    except Exception as e:
        logger.error(f"Excel error: {str(e)}")
        flash(f'❌ Export failed: {str(e)}', 'danger')
        return redirect(url_for('dashboard.dashboard'))


@student_bp.route('/export/pdf')
@teacher_or_admin_required
def export_pdf():
    """Export to PDF"""
    try:
        inst_id = g.user.institution_id
        
        records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        ).order_by(Attendance.date.desc()).limit(100).all()
        
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
        elements = []
        
        styles = getSampleStyleSheet()
        
        title = Paragraph("Attendance Report", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 0.3))
        
        table_data = [['Student Name', 'Student ID', 'Class', 'Subject', 'Date', 'Status']]
        
        for record in records:
            table_data.append([
                record.student.name or 'N/A',
                record.student.student_id or 'N/A',
                record.student.class_batch.name if record.student.class_batch else 'N/A',
                record.subject.name if record.subject else 'N/A',
                record.date.strftime('%Y-%m-%d'),
                record.status.capitalize()
            ])
        
        table = Table(table_data, colWidths=[1.5, 1.2, 1.5, 1.5, 1.2, 1])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        
        doc.build(elements)
        pdf_buffer.seek(0)
        
        logger.info(f"PDF export: {inst_id}")
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    except Exception as e:
        logger.error(f"PDF error: {str(e)}")
        flash(f'❌ Export failed: {str(e)}', 'danger')
        return redirect(url_for('dashboard.dashboard'))
