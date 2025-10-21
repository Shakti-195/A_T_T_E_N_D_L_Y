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
# CORRECTED: Removed template_folder and static_folder arguments
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


# --- Student Management Routes (for Teachers/Admins) ---

@student_bp.route('/students')
@teacher_or_admin_required
def list_students():
    """Displays a paginated list of all students in the institution."""
    all_classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).order_by(ClassBatch.name).all()
    selected_class_id = request.args.get('class_id', default=None, type=int)

    base_query = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == g.user.institution_id)

    if selected_class_id:
        base_query = base_query.filter(Student.class_batch_id == selected_class_id)
    
    page = request.args.get('page', 1, type=int)
    query = request.args.get('query', '')
    if query:
        search_term = f"%{query}%"
        base_query = base_query.filter(db.or_(Student.name.ilike(search_term), Student.student_id.ilike(search_term)))
        
    students_pagination = base_query.order_by(Student.name).paginate(page=page, per_page=15, error_out=False)
    
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
    classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()
    if request.method == 'POST':
        name = request.form.get('name')
        sid = request.form.get('student_id')
        email = request.form.get('email')
        cid = request.form.get('class_batch_id')
        
        if not all([name, sid, cid]):
            flash('Name, Student ID, and Class are required.', 'danger')
            return render_template('student/add_student.html', **request.form, classes_batches=classes)

        existing_student = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == sid
        ).first()
        
        if existing_student:
            flash('This Student ID is already taken in your institution.', 'danger')
            return render_template('student/add_student.html', **request.form, classes_batches=classes)

        new_student = Student(name=name, student_id=sid, email=email, class_batch_id=cid)
        db.session.add(new_student)
        db.session.commit()
        
        flash(f'Student "{name}" has been pre-registered successfully.', 'success')
        return redirect(url_for('student.list_students'))
            
    return render_template('student/add_student.html', classes_batches=classes)

@student_bp.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
@teacher_or_admin_required
def edit_student(student_id):
    """Handles editing an existing student's details."""
    student = db.session.get(Student, student_id)
    if not student or student.class_batch.institution_id != g.user.institution_id:
       flash('Student not found.', 'danger')
       return redirect(url_for('student.list_students'))

    classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()

    if request.method == 'POST':
        new_name = request.form.get('name')
        new_sid = request.form.get('student_id')
        new_email = request.form.get('email')
        new_cid = request.form.get('class_batch_id')

        existing_student = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == g.user.institution_id,
            Student.student_id == new_sid,
            Student.id != student_id
        ).first()
        
        if existing_student:
            flash('This Student ID is already taken by another student.', 'danger')
            return render_template('student/edit_student.html', student=student, classes_batches=classes)

        student.name = new_name
        student.student_id = new_sid
        student.email = new_email
        student.class_batch_id = new_cid
        
        if student.user:
            student.user.username = new_sid
            student.user.email = new_email

        db.session.commit()
        flash(f'Student "{student.name}" updated successfully.', 'success')
        return redirect(url_for('student.list_students'))

    return render_template('student/edit_student.html', student=student, classes_batches=classes)

@student_bp.route('/delete_student/<int:student_id>', methods=['POST'])
@teacher_or_admin_required
def delete_student(student_id):
    """Handles the deletion of a student record."""
    student = db.session.get(Student, student_id)
    if student and student.class_batch and student.class_batch.institution_id == g.user.institution_id:
        db.session.delete(student)
        db.session.commit()
        flash(f'Student {student.name} has been deleted.', 'success')
    else:
        flash('Student not found or you do not have permission to delete.', 'danger')
    return redirect(url_for('student.list_students'))

@student_bp.route('/import_students', methods=['GET', 'POST'])
@admin_required
def import_students():
    """Allows bulk import of students from a CSV file."""
    if request.method == 'POST':
        if 'student_csv' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        file = request.files['student_csv']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        if file and file.filename.endswith('.csv'):
            try:
                stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_reader = csv.DictReader(stream)
                count = 0
                errors = []
                
                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        if not all(key in row for key in ['name', 'student_id', 'class_batch_id']):
                            errors.append(f"Row {row_num}: Missing required fields")
                            continue
                            
                        class_batch = db.session.get(ClassBatch, int(row['class_batch_id']))
                        if not class_batch or class_batch.institution_id != g.user.institution_id:
                            errors.append(f"Row {row_num}: Invalid class batch")
                            continue
                            
                        student = Student(
                            name=row['name'], 
                            student_id=row['student_id'], 
                            email=row.get('email', ''), 
                            class_batch_id=int(row['class_batch_id'])
                        )
                        db.session.add(student)
                        count += 1
                        
                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        
                db.session.commit()
                
                if errors:
                    flash(f'Imported {count} students with {len(errors)} errors. Errors: {"; ".join(errors[:5])}', 'warning')
                else:
                    flash(f'Successfully imported {count} students.', 'success')
                    
                return redirect(url_for('student.list_students'))
                
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')
                
    return render_template('student/import_students.html')


# --- Attendance Marking and Viewing Routes ---

@student_bp.route('/mark_attendance', methods=['GET', 'POST'])
@teacher_or_admin_required
def mark_attendance():
    """Handles manual attendance marking by teachers/admins."""
    if request.method == 'POST':
        class_id = request.form.get('class_batch_id')
        subject_id = request.form.get('subject_id')
        date_str = request.form.get('date')
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
            return redirect(url_for('student.mark_attendance'))
                
        students_in_class = Student.query.filter_by(class_batch_id=class_id).all()
        for student in students_in_class:
            status = request.form.get(f'status_{student.id}')
            if status:
                record = Attendance.query.filter_by(
                    student_id=student.id, 
                    date=date_obj, 
                    subject_id=subject_id
                ).first()
                if record: 
                    record.status = status
                else: 
                    db.session.add(Attendance(
                        student_id=student.id, 
                        subject_id=subject_id, 
                        date=date_obj, 
                        status=status
                    ))
        db.session.commit()
        flash('Attendance saved!', 'success')
        return redirect(url_for('student.mark_attendance', 
                                class_batch_id=class_id, 
                                subject_id=subject_id, 
                                date=date_str))
    
    selected_class_id = request.args.get('class_batch_id', type=int)
    selected_subject_id = request.args.get('subject_id', type=int)
    selected_date = request.args.get('date', get_current_ist().strftime('%Y-%m-%d'))
    students = []
    attendance_statuses = {}
    classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).all()
    subjects = Subject.query.all()

    if selected_class_id and selected_subject_id:
        students = Student.query.filter_by(class_batch_id=selected_class_id).order_by(Student.name).all()
        try:
            date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
            student_ids = [s.id for s in students]
            existing_records = Attendance.query.filter(
                Attendance.student_id.in_(student_ids), 
                Attendance.date == date_obj, 
                Attendance.subject_id == selected_subject_id
            ).all()
            attendance_statuses = {r.student_id: r.status for r in existing_records}
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')

    return render_template('student/mark_attendance.html', 
                           taught_classes=classes, 
                           subjects=subjects, 
                           students=students, 
                           selected_class_id=selected_class_id, 
                           selected_subject_id=selected_subject_id,
                           selected_date=selected_date, 
                           attendance_statuses=attendance_statuses)

@student_bp.route('/attendance_history')
@teacher_or_admin_required
def attendance_history():
    """Displays a paginated list of all attendance records."""
    page = request.args.get('page', 1, type=int)
    selected_date_str = request.args.get('date')

    base_query = Attendance.query.options(joinedload(Attendance.subject))\
    .join(Student).join(ClassBatch)\
    .filter(ClassBatch.institution_id == g.user.institution_id)

    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            base_query = base_query.filter(Attendance.date == selected_date)
        except (ValueError, TypeError):
            flash('Invalid date format used for filtering.', 'danger')
            selected_date_str = None
    
    records = base_query.order_by(desc(Attendance.date), desc(Attendance.created_at)).paginate(
        page=page, per_page=20, error_out=False)
    
    return render_template('student/attendance_history.html', records=records, selected_date=selected_date_str)


# --- QR Code Attendance Routes ---

@student_bp.route('/api/generate_qr', methods=['POST'])
@teacher_or_admin_required
def generate_qr():
    """API endpoint to generate a short-lived QR code for attendance."""
    data = request.json
    class_id = data.get('class_batch_id')
    subject_id = data.get('subject_id')
    
    if not class_id or not subject_id:
        return jsonify({'error': 'Class and Subject are required.'}), 400
        
    try:
        class_batch = db.session.get(ClassBatch, int(class_id))
        if not class_batch or class_batch.institution_id != g.user.institution_id:
            return jsonify({'error': 'Invalid class selection.'}), 400
            
        token = QRToken(
            class_batch_id=int(class_id), 
            subject_id=int(subject_id), 
            expiry_time=get_current_ist() + timedelta(minutes=2)
        )
        db.session.add(token)
        db.session.commit()
        
        scan_url = url_for('student.scan_attendance_token', token=token.token, _external=True)
        img = qrcode.make(scan_url)
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        return jsonify({'qr_image': img_str})
        
    except Exception as e:
        current_app.logger.error(f"Error generating QR code: {e}")
        return jsonify({'error': 'Failed to generate QR code.'}), 500

@student_bp.route('/scan_attendance/<token>')
@login_required
def scan_attendance_token(token):
    """Handles the attendance marking when a student scans a QR code."""
    if g.user.role != 'student':
        flash('Only students can scan QR codes.', 'warning')
        return redirect(url_for('dashboard.dashboard'))
        
    qr_token = QRToken.query.filter_by(token=token).first()
    if not qr_token or get_current_ist() > qr_token.expiry_time:
        flash('QR code is invalid or has expired.', 'danger')
        return redirect(url_for('student.my_attendance'))
        
    student = g.user.student_profile
    if not student or student.class_batch_id != qr_token.class_batch_id:
        flash('You are not in the correct class for this QR code.', 'danger')
        return redirect(url_for('student.my_attendance'))
        
    today = get_current_ist().date()
    record = Attendance.query.filter_by(
        student_id=student.id, 
        date=today, 
        subject_id=qr_token.subject_id
    ).first()
    
    if record:
        record.status = 'present'
        record.marked_by = 'qr'
        flash('Attendance updated to present.', 'success')
    else:
        new_record = Attendance(
            student_id=student.id, 
            subject_id=qr_token.subject_id, 
            date=today, 
            status='present', 
            marked_by='qr'
        )
        db.session.add(new_record)
        flash('Attendance marked successfully!', 'success')
        
    db.session.delete(qr_token)
    db.session.commit()
    return redirect(url_for('student.my_attendance'))


# --- Student-Facing Routes ---

@student_bp.route('/my_attendance')
@login_required
def my_attendance():
    """Displays the current student's own attendance records."""
    if g.role != 'student':
        flash("This page is only for the student view.", "warning")
        return redirect(url_for('dashboard.dashboard'))

    if g.user.student_profile:
        records = g.user.student_profile.attendances.order_by(desc(Attendance.date)).all()
        return render_template('student/my_attendance.html', records=records, student=g.user.student_profile)
    
    else:
        return render_template('student/my_attendance.html', records=None, student=None)

@student_bp.route('/check_attendance/', methods=['GET', 'POST'])
def check_attendance():
    """Public page for anyone to check a student's attendance by their ID."""
    student = None
    attendance_records = None
    student_id_searched = ""

    if request.method == 'POST':
        student_id_searched = request.form.get('student_id')
        if student_id_searched:
            student = Student.query.filter_by(student_id=student_id_searched).first()
            if student:
                attendance_records = student.attendances.order_by(desc(Attendance.date)).paginate(
                    page=1, per_page=15, error_out=False
                )
            else:
                flash(f'No student found with ID: {student_id_searched}', 'warning')
    
    return render_template(
        'student/check_attendance.html', 
        student=student, 
        attendance_records=attendance_records, 
        student_id_searched=student_id_searched
    )

@student_bp.route('/apply_leave', methods=['GET', 'POST'])
@login_required
def apply_leave():
    """Allows a student to apply for medical leave."""
    if g.user.role != 'student' or not g.user.student_profile:
        flash('Only students can apply for leave.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            reason = request.form.get('reason')

            if start_date and end_date and reason:
                if start_date <= end_date:
                    leave = MedicalLeave(
                        student_id=g.user.student_profile.id, 
                        start_date=start_date, 
                        end_date=end_date, 
                        reason=reason,
                        expiry_time=get_current_ist() + timedelta(hours=48)
                    )
                    db.session.add(leave)
                    db.session.commit()
                    flash('Leave request submitted successfully.', 'success')
                    return redirect(url_for('profile.profile_view'))
                else:
                    flash('End date must be after start date.', 'danger')
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
    
    return render_template('student/apply_leave.html')

@student_bp.route('/add_medical_leave/<int:student_id>', methods=['GET', 'POST'])
@teacher_or_admin_required
def add_medical_leave(student_id):
    student = db.session.get(Student, student_id)
    
    if not student or student.class_batch.institution_id != g.user.institution_id:
        flash('Student not found.', 'danger')
        return redirect(url_for('student.list_students'))
    
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            reason = request.form.get('reason')
            
            if start_date and end_date and reason:
                if start_date <= end_date:
                    leave = MedicalLeave(
                        student_id=student_id, 
                        start_date=start_date, 
                        end_date=end_date, 
                        reason=reason
                    )
                    db.session.add(leave)
                    db.session.commit()
                    flash('Medical leave added successfully.', 'success')
                    return redirect(url_for('student.student_profile_view', student_id=student_id))
                else:
                    flash('End date must be after start date.', 'danger')
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
    
    return render_template('student/add_leave.html', student=student)

# --- NEWLY ADDED ROUTES ---

@student_bp.route('/handle_leave/<int:leave_id>/<action>', methods=['POST'])
@teacher_or_admin_required
def handle_leave(leave_id, action):
    """Handles approving or denying a leave request."""
    leave = db.session.get(MedicalLeave, leave_id)
    if not leave or leave.student.class_batch.institution_id != g.user.institution_id:
        flash("Leave request not found.", "danger")
        return redirect(url_for('dashboard.dashboard'))

    if action == 'approve':
        leave.status = 'approved'
        flash(f"Leave for {leave.student.name} approved.", "success")
    elif action == 'deny':
        leave.status = 'denied'
        flash(f"Leave for {leave.student.name} denied.", "warning")
    
    db.session.commit()
    return redirect(url_for('dashboard.dashboard'))

@student_bp.route('/export/csv')
@teacher_or_admin_required
def export_csv():
    """Exports all attendance records to a CSV file."""
    try:
        records = Attendance.query.join(Student).join(ClassBatch)\
            .filter(ClassBatch.institution_id == g.user.institution_id)\
            .order_by(Attendance.date, Student.name).all()
        
        output = StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status', 'Marked At'])
        
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
            headers={"Content-disposition": "attachment; filename=attendance_report.csv"}
        )
    except Exception as e:
        current_app.logger.error(f"Error exporting CSV: {e}")
        flash("An error occurred while generating the report.", "danger")
        return redirect(url_for('dashboard.dashboard'))

@student_bp.route('/export/pdf')
@teacher_or_admin_required
def export_pdf():
    """Exports all attendance records to a PDF file."""
    try:
        records = Attendance.query.join(Student).join(ClassBatch)\
            .filter(ClassBatch.institution_id == g.user.institution_id)\
            .order_by(Attendance.date, Student.name).all()

        pdf = PDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        headers = ['Student Name', 'Student ID', 'Batch', 'Subject', 'Date', 'Status']
        col_widths = [60, 30, 60, 40, 30, 20]

        pdf.set_font('Helvetica', 'B', 10)
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 10, header, border=1, align='C')
        pdf.ln()

        pdf.set_font('Helvetica', '', 9)
        if not records:
            pdf.cell(sum(col_widths), 10, 'No attendance data found.', border=1, ln=1, align='C')
        else:
            for record in records:
                pdf.cell(col_widths[0], 10, record.student.name.encode('latin-1', 'replace').decode('latin-1'), border=1)
                pdf.cell(col_widths[1], 10, record.student.student_id.encode('latin-1', 'replace').decode('latin-1'), border=1)
                pdf.cell(col_widths[2], 10, (record.student.class_batch.name if record.student.class_batch else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
                pdf.cell(col_widths[3], 10, (record.subject.name if record.subject else 'N/A').encode('latin-1', 'replace').decode('latin-1'), border=1)
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
        flash("An error occurred while generating the PDF report.", "danger")
        return redirect(url_for('dashboard.dashboard'))

