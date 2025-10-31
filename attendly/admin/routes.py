# -*- coding: utf-8 -*-
"""
Handles all administrative tasks for an institution.
Includes setup, reports, scheduling, CSV import, and helper functions for profile stats.
"""

# --- Standard Library Imports ---
from datetime import datetime, timedelta, date
import time
import secrets
import csv
import io

# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify, current_app
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case, extract, desc, and_, or_
from werkzeug.utils import secure_filename

# --- Local Application Imports ---
from ..extensions import db, scheduler
from ..models import Student, ClassBatch, Subject, User, Attendance, MedicalLeave, TeacherAssignment
from ..utils import admin_required

admin_bp = Blueprint('admin', __name__)


# ====================================================================
# STATS CALCULATION HELPERS
# ====================================================================

def get_admin_system_stats(user):
    """Calculates high-level system metrics for the Admin Profile hero section."""
    inst_id = user.institution_id
    stats = {
        'totalStudents': 0,
        'totalTeachers': 0,
        'systemAttendance': 0,
        'pendingReports': 0
    }
    
    if not inst_id:
        return stats
    
    try:
        # Total Students
        stats['totalStudents'] = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        ).count()
        
        # Total Teachers
        stats['totalTeachers'] = User.query.filter_by(
            role='teacher',
            institution_id=inst_id
        ).count()
        
        # System Attendance (last 30 days)
        thirty_days_ago = date.today() - timedelta(days=30)
        attendance_query = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id,
            Attendance.date >= thirty_days_ago
        )
        total_records = attendance_query.count()
        total_present = attendance_query.filter_by(status='present').count()
        
        if total_records > 0:
            stats['systemAttendance'] = round((total_present / total_records) * 100, 1)
        
        # Pending Leaves
        stats['pendingReports'] = MedicalLeave.query.filter_by(
            status='pending',
            institution_id=inst_id
        ).count()
        
    except Exception as e:
        current_app.logger.error(f"Error calculating admin stats: {str(e)}")
    
    return stats


def get_teacher_profile_stats(user):
    """Calculates key metrics for the Teacher Profile hero section."""
    stats = {
        'totalStudents': 0,
        'avgClassAttendance': 0,
        'totalClasses': 0,
        'yearsExperience': 0
    }
    
    if not user.institution_id:
        return stats
    
    try:
        teacher_id = user.id
        
        # Total Classes Assigned
        assigned_classes_count = ClassBatch.query.filter(
            and_(
                ClassBatch.institution_id == user.institution_id,
                ClassBatch.teachers.any(User.id == teacher_id)
            )
        ).count()
        
        # Total Unique Students Taught
        total_students_taught = db.session.query(
            func.count(func.distinct(Student.id))
        ).join(ClassBatch).filter(
            ClassBatch.teachers.any(User.id == teacher_id)
        ).scalar() or 0
        
        # Average Class Attendance
        total_records = db.session.query(
            func.count(Attendance.id)
        ).join(Student).join(ClassBatch).filter(
            ClassBatch.teachers.any(User.id == teacher_id)
        ).scalar() or 0
        
        total_present = db.session.query(
            func.count(Attendance.id)
        ).join(Student).join(ClassBatch).filter(
            ClassBatch.teachers.any(User.id == teacher_id),
            Attendance.status == 'present'
        ).scalar() or 0
        
        stats['totalClasses'] = assigned_classes_count
        stats['totalStudents'] = total_students_taught
        
        if total_records > 0:
            stats['avgClassAttendance'] = round((total_present / total_records) * 100, 1)
        
        # Experience (extract years from experience field)
        if user.experience and user.experience.split():
            for word in user.experience.split():
                if word.isdigit():
                    stats['yearsExperience'] = int(word)
                    break
        
    except Exception as e:
        current_app.logger.error(f"Error calculating teacher stats: {str(e)}")
    
    return stats


# ====================================================================
# PENDING LEAVES MANAGEMENT ROUTE
# ====================================================================

@admin_bp.route('/pending-leaves')
@admin_required
def pending_leaves():
    """Display and manage pending leave requests for the institution."""
    inst_id = g.user.institution_id
    
    # Get filter parameters
    status_filter = request.args.get('status', 'pending')
    search_query = request.args.get('search', '')
    
    # Build base query
    query = MedicalLeave.query.filter_by(institution_id=inst_id)
    
    # Apply status filter
    if status_filter in ['pending', 'approved', 'denied']:
        query = query.filter_by(status=status_filter)
    
    # Apply search filter (by student name)
    if search_query:
        query = query.join(Student).filter(Student.name.ilike(f'%{search_query}%'))
    else:
        query = query.join(Student)
    
    # Order by most recent first
    leaves = query.order_by(desc(MedicalLeave.created_at)).all()
    
    # Calculate statistics
    total_pending = MedicalLeave.query.filter_by(
        institution_id=inst_id,
        status='pending'
    ).count()
    
    total_approved = MedicalLeave.query.filter_by(
        institution_id=inst_id,
        status='approved'
    ).count()
    
    total_denied = MedicalLeave.query.filter_by(
        institution_id=inst_id,
        status='denied'
    ).count()
    
    return render_template(
        'admin/pending_leaves.html',
        leaves=leaves,
        status_filter=status_filter,
        search_query=search_query,
        total_pending=total_pending,
        total_approved=total_approved,
        total_denied=total_denied
    )


@admin_bp.route('/handle-leave/<int:leave_id>/<action>', methods=['POST'])
@admin_required
def handle_leave_request(leave_id, action):
    """Handle approving or denying a leave request."""
    leave = db.session.get(MedicalLeave, leave_id)
    
    if not leave or leave.institution_id != g.user.institution_id:
        flash("❌ Leave request not found.", "danger")
        return redirect(url_for('admin.pending_leaves'))
    
    if action == 'approve':
        leave.status = 'approved'
        flash(f"✅ Leave for {leave.student.name} has been approved.", "success")
    elif action == 'deny':
        leave.status = 'denied'
        flash(f"❌ Leave for {leave.student.name} has been denied.", "warning")
    else:
        flash("❌ Invalid action.", "danger")
        return redirect(url_for('admin.pending_leaves'))
    
    db.session.commit()
    return redirect(url_for('admin.pending_leaves'))


# ====================================================================
# CSV IMPORT ROUTE
# ====================================================================

@admin_bp.route('/import-students', methods=['GET', 'POST'])
@admin_required
def import_students():
    """Import students from CSV file"""
    inst_id = g.user.institution_id
    
    if request.method == 'POST':
        # Check if file was provided
        if 'student_csv' not in request.files:
            flash('❌ No file selected. Please upload a CSV file.', 'danger')
            return redirect(url_for('admin.import_students'))
        
        file = request.files['student_csv']
        
        if file.filename == '':
            flash('❌ No file selected. Please upload a CSV file.', 'danger')
            return redirect(url_for('admin.import_students'))
        
        if not file.filename.endswith('.csv'):
            flash('❌ Invalid file type. Please upload a CSV file.', 'danger')
            return redirect(url_for('admin.import_students'))
        
        try:
            # Read and parse CSV
            stream = io.TextIOWrapper(file.stream, encoding='utf-8')
            csv_reader = csv.DictReader(stream)
            
            if not csv_reader:
                flash('❌ CSV file is empty or invalid.', 'danger')
                return redirect(url_for('admin.import_students'))
            
            # Validate headers
            required_headers = {'name', 'student_id', 'email', 'class_batch_id'}
            if not required_headers.issubset(set(csv_reader.fieldnames or [])):
                flash('❌ CSV file must contain: name, student_id, email, class_batch_id', 'danger')
                return redirect(url_for('admin.import_students'))
            
            imported_count = 0
            skipped_count = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):
                try:
                    name = row.get('name', '').strip()
                    student_id = row.get('student_id', '').strip()
                    email = row.get('email', '').strip()
                    class_batch_id = row.get('class_batch_id', '').strip()
                    
                    # Validate required fields
                    if not all([name, student_id, email, class_batch_id]):
                        errors.append(f"Row {row_num}: Missing required fields")
                        skipped_count += 1
                        continue
                    
                    # Validate email format
                    if '@' not in email or '.' not in email:
                        errors.append(f"Row {row_num}: Invalid email format")
                        skipped_count += 1
                        continue
                    
                    # Check if class exists
                    class_batch = ClassBatch.query.get(int(class_batch_id))
                    if not class_batch:
                        errors.append(f"Row {row_num}: Class ID {class_batch_id} not found")
                        skipped_count += 1
                        continue
                    
                    # Check for duplicate student_id
                    existing_student = Student.query.filter_by(student_id=student_id).first()
                    if existing_student:
                        errors.append(f"Row {row_num}: Student ID {student_id} already exists")
                        skipped_count += 1
                        continue
                    
                    # Check for duplicate email
                    existing_email = Student.query.filter_by(email=email).first()
                    if existing_email:
                        errors.append(f"Row {row_num}: Email {email} already registered")
                        skipped_count += 1
                        continue
                    
                    # Create new student
                    new_student = Student(
                        name=name,
                        student_id=student_id,
                        email=email,
                        class_batch_id=int(class_batch_id)
                    )
                    db.session.add(new_student)
                    imported_count += 1
                    
                except ValueError as e:
                    errors.append(f"Row {row_num}: Invalid data format - {str(e)}")
                    skipped_count += 1
                except Exception as e:
                    errors.append(f"Row {row_num}: Error - {str(e)}")
                    skipped_count += 1
            
            # Commit all changes
            db.session.commit()
            
            # Flash messages
            if imported_count > 0:
                flash(f'✅ Successfully imported {imported_count} student(s)!', 'success')
            
            if skipped_count > 0:
                error_msg = f'⚠️ Skipped {skipped_count} row(s). Details: ' + ' | '.join(errors[:5])
                if len(errors) > 5:
                    error_msg += f'... and {len(errors) - 5} more errors'
                flash(error_msg, 'warning')
            
            if imported_count == 0 and skipped_count > 0:
                flash('❌ No students were imported. Please check the CSV file format.', 'danger')
            
            return redirect(url_for('admin.import_students'))
        
        except Exception as e:
            current_app.logger.error(f"CSV import error: {str(e)}")
            flash(f'❌ Error processing CSV file: {str(e)}', 'danger')
            return redirect(url_for('admin.import_students'))
    
    return render_template('admin/import_students.html')


# ====================================================================
# SETUP ROUTES
# ====================================================================

@admin_bp.route('/setup', methods=['GET', 'POST'])
@admin_required
def setup():
    """Setup classes, subjects, and assignments"""
    
    if request.method == 'POST':
        # Create new class
        if 'class_batch_name' in request.form and request.form['class_batch_name']:
            new_class = ClassBatch(
                name=request.form['class_batch_name'],
                institution_id=g.user.institution_id
            )
            db.session.add(new_class)
            flash('✅ New class/batch created successfully!', 'success')
        
        # Create new subject
        if 'subject_name' in request.form and request.form['subject_name']:
            new_subject = Subject(name=request.form['subject_name'])
            db.session.add(new_subject)
            flash('✅ New subject created successfully!', 'success')
        
        db.session.commit()
        return redirect(url_for('admin.setup'))
    
    # Get all students (assigned and unassigned)
    all_students = Student.query.all()
    unassigned_students = [s for s in all_students if not s.class_batch_id]
    assigned_students = [s for s in all_students if s.class_batch_id]
    
    # Get classes with relationships
    classes = ClassBatch.query.filter_by(
        institution_id=g.user.institution_id
    ).options(
        joinedload(ClassBatch.teacher_assignments).joinedload(TeacherAssignment.teacher),
        joinedload(ClassBatch.teacher_assignments).joinedload(TeacherAssignment.subject)
    ).all()
    
    # Get teachers and subjects
    teachers = User.query.filter_by(
        role='teacher',
        institution_id=g.user.institution_id
    ).all()
    subjects = Subject.query.all()
    
    return render_template(
        'admin/setup.html',
        all_students=all_students,
        unassigned_students=unassigned_students,
        assigned_students=assigned_students,
        classes_batches=classes,
        teachers=teachers,
        subjects=subjects,
        institution=g.user.institution
    )


@admin_bp.route('/assign_student_to_class/<int:student_id>', methods=['POST'])
@admin_required
def assign_student_to_class(student_id):
    """Assign student to class"""
    student = db.session.get(Student, student_id)
    class_id = request.form.get('class_batch_id')
    
    if student and class_id:
        student.class_batch_id = class_id
        db.session.commit()
        flash(f'✅ {student.name} assigned to class successfully!', 'success')
    else:
        flash('❌ Error assigning student.', 'danger')
    
    return redirect(url_for('admin.setup'))


@admin_bp.route('/unassign_student/<int:student_id>', methods=['POST'])
@admin_required
def unassign_student(student_id):
    """Unassign student from class"""
    student = db.session.get(Student, student_id)
    
    if student:
        student.class_batch_id = None
        db.session.commit()
        flash(f'✅ {student.name} unassigned from class.', 'success')
    else:
        flash('❌ Error unassigning student.', 'danger')
    
    return redirect(url_for('admin.setup'))


@admin_bp.route('/assign_teacher_subject/<int:class_id>', methods=['POST'])
@admin_required
def assign_teacher_subject(class_id):
    """Assign teacher to class with specific subject"""
    teacher_id = request.form.get('teacher_id')
    subject_id = request.form.get('subject_id')
    
    if not teacher_id or not subject_id:
        flash('❌ Please select both teacher and subject.', 'danger')
        return redirect(url_for('admin.setup'))
    
    # Check if already assigned
    existing = TeacherAssignment.query.filter_by(
        teacher_id=teacher_id,
        class_batch_id=class_id,
        subject_id=subject_id
    ).first()
    
    if existing:
        flash('⚠️ This teacher is already assigned to this subject in this class.', 'warning')
        return redirect(url_for('admin.setup'))
    
    # Check if subject already assigned to another teacher
    existing_subject = TeacherAssignment.query.filter_by(
        class_batch_id=class_id,
        subject_id=subject_id
    ).first()
    
    if existing_subject:
        flash('⚠️ This subject is already assigned to another teacher in this class.', 'warning')
        return redirect(url_for('admin.setup'))
    
    # Create assignment
    assignment = TeacherAssignment(
        teacher_id=teacher_id,
        class_batch_id=class_id,
        subject_id=subject_id
    )
    
    db.session.add(assignment)
    db.session.commit()
    flash('✅ Teacher assigned to subject successfully!', 'success')
    
    return redirect(url_for('admin.setup'))


@admin_bp.route('/unassign_teacher_subject/<int:assignment_id>', methods=['POST'])
@admin_required
def unassign_teacher_subject(assignment_id):
    """Remove teacher-subject assignment"""
    assignment = TeacherAssignment.query.get_or_404(assignment_id)
    db.session.delete(assignment)
    db.session.commit()
    flash('✅ Teacher unassigned from subject successfully!', 'success')
    
    return redirect(url_for('admin.setup'))


@admin_bp.route('/delete_class_batch/<int:class_id>', methods=['POST'])
@admin_required
def delete_class_batch(class_id):
    """Delete class batch"""
    class_to_delete = db.session.get(ClassBatch, class_id)
    
    if class_to_delete and class_to_delete.institution_id == g.user.institution_id:
        # Unassign all students
        students = Student.query.filter_by(class_batch_id=class_id).all()
        for student in students:
            student.class_batch_id = None
        
        # Delete teacher assignments
        TeacherAssignment.query.filter_by(class_batch_id=class_id).delete()
        
        # Delete class
        db.session.delete(class_to_delete)
        db.session.commit()
        flash('✅ Class/Batch deleted successfully.', 'success')
    else:
        flash('❌ Class not found.', 'danger')
    
    return redirect(url_for('admin.setup'))


@admin_bp.route('/delete_subject/<int:subject_id>', methods=['POST'])
@admin_required
def delete_subject(subject_id):
    """Delete subject"""
    subject_to_delete = db.session.get(Subject, subject_id)
    
    if subject_to_delete:
        # Delete all teacher assignments
        TeacherAssignment.query.filter_by(subject_id=subject_id).delete()
        
        # Delete subject
        db.session.delete(subject_to_delete)
        db.session.commit()
        flash('✅ Subject deleted successfully.', 'success')
    else:
        flash('❌ Subject not found.', 'danger')
    
    return redirect(url_for('admin.setup'))


# ====================================================================
# REPORTS ROUTE (COMPREHENSIVE)
# ====================================================================

@admin_bp.route('/reports')
@admin_required
def reports():
    """Comprehensive attendance reports"""
    inst_id = g.user.institution_id
    
    # Get date range
    today = datetime.now().date()
    start_date_str = request.args.get('start_date', (today - timedelta(days=29)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    class_id = request.args.get('class_id', type=int)
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('❌ Invalid date format.', 'danger')
        start_date = today - timedelta(days=29)
        end_date = today
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Get all classes
    classes = ClassBatch.query.filter_by(institution_id=inst_id).all()
    
    # Build base query
    base_query = Attendance.query.join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date.between(start_date, end_date)
    )
    
    if class_id:
        base_query = base_query.filter(ClassBatch.id == class_id)
    
    total_records = base_query.count()
    total_present = base_query.filter(Attendance.status == 'present').count()
    
    summary = {
        'overall_attendance_percent': (total_present / total_records * 100) if total_records > 0 else 0,
        'total_present': total_present,
        'total_absent': total_records - total_present,
        'total_records': total_records
    }
    
    # Get student records
    student_records = []
    student_query = db.session.query(
        Student.name,
        ClassBatch.name.label('class_name'),
        func.count(Attendance.id).label('total_days'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present_days')
    ).select_from(Attendance).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date.between(start_date, end_date)
    )
    
    if class_id:
        student_query = student_query.filter(ClassBatch.id == class_id)
    
    student_query = student_query.group_by(Student.id, Student.name, ClassBatch.id, ClassBatch.name).all()
    
    for name, class_name, total_days, present_days in student_query:
        present = present_days or 0
        absent = total_days - present
        percentage = (present / total_days * 100) if total_days > 0 else 0
        student_records.append({
            'student': name,
            'class_name': class_name,
            'total_days': total_days,
            'present': present,
            'absent': absent,
            'attendance_percent': round(percentage, 1)
        })
    
    # Get teacher records
    teacher_records = []
    teachers = User.query.filter_by(institution_id=inst_id, role='teacher').all()
    
    for teacher in teachers:
        assignments = TeacherAssignment.query.filter_by(teacher_id=teacher.id).all()
        
        if assignments:
            assigned_classes = {}
            subjects_set = set()
            total_students = 0
            
            for assignment in assignments:
                if assignment.class_batch_id not in assigned_classes:
                    assigned_classes[assignment.class_batch_id] = assignment.class_batch.name
                    total_students += len(assignment.class_batch.students)
                
                if assignment.subject:
                    subjects_set.add(assignment.subject.name)
            
            # Classes taken count
            classes_taken = db.session.query(
                func.count(func.distinct(Attendance.date))
            ).select_from(Attendance).join(Student).join(ClassBatch).filter(
                ClassBatch.id.in_(list(assigned_classes.keys())),
                Attendance.date.between(start_date, end_date)
            ).scalar() or 0
            
            # Attendance rate
            attendance_total = db.session.query(
                func.count(Attendance.id),
                func.sum(case((Attendance.status == 'present', 1), else_=0))
            ).select_from(Attendance).join(Student).join(ClassBatch).filter(
                ClassBatch.id.in_(list(assigned_classes.keys())),
                Attendance.date.between(start_date, end_date)
            ).all()
            
            total_att = attendance_total[0][0] or 0
            present_att = attendance_total[0][1] or 0
            attendance_rate = (present_att / total_att * 100) if total_att > 0 else 0
            
            teacher_records.append({
                'teacher': teacher.username,
                'classes': list(assigned_classes.values()),
                'subjects': list(subjects_set),
                'total_students': total_students,
                'classes_taken': classes_taken,
                'attendance_rate': round(attendance_rate, 1)
            })
    
    # Role distribution
    student_count = User.query.filter_by(institution_id=inst_id, role='student').count()
    teacher_count = User.query.filter_by(institution_id=inst_id, role='teacher').count()
    
    role_distribution = {
        'students': student_count,
        'teachers': teacher_count
    }
    
    total_users = student_count + teacher_count
    
    return render_template(
        'admin/reports.html',
        student_records=student_records,
        teacher_records=teacher_records,
        summary=summary,
        role_distribution=role_distribution,
        classes=classes,
        selected_class_id=class_id,
        start_date=start_date_str,
        end_date=end_date_str,
        total_users=total_users,
        report_data=student_records + teacher_records
    )


# ====================================================================
# ANALYTICS ROUTE
# ====================================================================

@admin_bp.route('/analytics')
@admin_required
def analytics():
    """Analytics and insights dashboard"""
    inst_id = g.user.institution_id
    
    # Heatmap data
    heatmap_data = db.session.query(
        extract('isodow', Attendance.date).label('day_of_week'),
        extract('hour', Attendance.created_at).label('hour_of_day'),
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
    ).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id
    ).group_by('day_of_week', 'hour_of_day').all()
    
    heatmap_json = [
        {
            'day_of_week': int(d % 7),
            'hour_of_day': int(h or 0),
            'percentage': round(float(p or 0), 1)
        }
        for d, h, p in heatmap_data
    ]
    
    # Student engagement (top 10 by attendance)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    student_engagement = db.session.query(
        Student.name,
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('engagement_score')
    ).join(Attendance).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date >= thirty_days_ago
    ).group_by(Student.id, Student.name).order_by(desc('engagement_score')).limit(10).all()
    
    return render_template(
        'admin/analytics.html',
        heatmap_data=heatmap_json,
        student_engagement=student_engagement
    )


# ====================================================================
# SCHEDULE ROUTE
# ====================================================================

# ====================================================================
# SCHEDULE ROUTE (UPDATED)
# ====================================================================


@admin_bp.route('/schedule', methods=['GET', 'POST'])
@admin_required
def schedule():
    """Schedule report generation with email delivery"""
    inst_id = g.user.institution_id
    job_id = f'report_job_{inst_id}'
    
    # Get existing job if any
    existing_job = None
    try:
        if scheduler:
            existing_job = scheduler.get_job(job_id)
    except Exception as e:
        current_app.logger.error(f"Error fetching job: {str(e)}")
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        try:
            if not scheduler:
                flash('❌ Scheduler not available. Please contact administrator.', 'danger')
                return redirect(url_for('admin.schedule'))
            
            # SCHEDULE NEW REPORT
            if action == 'schedule':
                report_type = request.form.get('report_type', '').strip()
                frequency = request.form.get('frequency', '').strip()
                time = request.form.get('time', '').strip()
                day = request.form.get('day', 'monday').strip()
                email = request.form.get('email', '').strip()
                report_format = request.form.get('format', 'pdf').strip()
                
                # Validation
                if not all([report_type, frequency, time, email, report_format]):
                    flash('❌ Please fill all required fields!', 'danger')
                    return redirect(url_for('admin.schedule'))
                
                # Validate email
                if '@' not in email or '.' not in email:
                    flash('❌ Invalid email format!', 'danger')
                    return redirect(url_for('admin.schedule'))
                
                # Parse time
                try:
                    hour, minute = map(int, time.split(':'))
                    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                        raise ValueError("Invalid time")
                except (ValueError, IndexError):
                    flash('❌ Invalid time format!', 'danger')
                    return redirect(url_for('admin.schedule'))
                
                # Remove existing job if any
                if existing_job:
                    try:
                        scheduler.remove_job(job_id)
                    except Exception as e:
                        current_app.logger.warning(f"Could not remove existing job: {str(e)}")
                
                # Determine trigger based on frequency
                trigger_config = {
                    'trigger': 'cron',
                    'hour': hour,
                    'minute': minute,
                    'id': job_id,
                    'replace_existing': True
                }
                
                if frequency == 'daily':
                    pass  # hour and minute are enough
                elif frequency == 'weekly':
                    trigger_config['day_of_week'] = get_day_number(day)
                elif frequency == 'monthly':
                    trigger_config['day'] = 1  # First day of month
                elif frequency == 'quarterly':
                    trigger_config['month'] = '1,4,7,10'  # Jan, Apr, Jul, Oct
                    trigger_config['day'] = 1
                else:
                    flash('❌ Invalid frequency selected!', 'danger')
                    return redirect(url_for('admin.schedule'))
                
                # Schedule the job
                try:
                    job_data = {
                        'report_type': report_type,
                        'frequency': frequency,
                        'time': time,
                        'day': day,
                        'email': email,
                        'format': report_format,
                        'institution_id': inst_id
                    }
                    
                    scheduler.add_job(
                        func=send_scheduled_report,
                        **trigger_config,
                        args=(inst_id, report_type, email, report_format),
                        coalesce=True,
                        max_instances=1
                    )
                    
                    # Store job info in session/database
                    flash(
                        f'✅ Report scheduled successfully!\n'
                        f'📊 Type: {report_type.upper()}\n'
                        f'⏰ Frequency: {frequency.upper()}\n'
                        f'📧 Email: {email}',
                        'success'
                    )
                    
                except Exception as e:
                    current_app.logger.error(f"Error scheduling job: {str(e)}")
                    flash(f'❌ Failed to schedule report: {str(e)}', 'danger')
            
            # CANCEL SCHEDULE
            elif action == 'cancel':
                if existing_job:
                    try:
                        scheduler.remove_job(job_id)
                        flash('⚠️ Report schedule has been canceled.', 'warning')
                    except Exception as e:
                        current_app.logger.error(f"Error removing job: {str(e)}")
                        flash(f'❌ Error canceling schedule: {str(e)}', 'danger')
                else:
                    flash('ℹ️ No active schedule to cancel.', 'info')
            
            # RUN NOW
            elif action == 'run_now':
                try:
                    report_type = request.form.get('report_type', 'attendance')
                    email = g.user.email
                    report_format = request.form.get('format', 'pdf')
                    
                    # Run immediately
                    send_scheduled_report(inst_id, report_type, email, report_format)
                    
                    flash(
                        f'✅ Report generation started!\n'
                        f'📧 Report will be sent to: {email}',
                        'success'
                    )
                except Exception as e:
                    current_app.logger.error(f"Error running report: {str(e)}")
                    flash(f'❌ Error generating report: {str(e)}', 'danger')
            
            else:
                flash('❌ Invalid action!', 'danger')
        
        except Exception as e:
            current_app.logger.error(f"Error in schedule route: {str(e)}")
            flash(f'❌ An error occurred: {str(e)}', 'danger')
        
        return redirect(url_for('admin.schedule'))
    
    # GET request - display form with existing job info
    job_info = None
    if existing_job:
        job_info = {
            'id': existing_job.id,
            'next_run_time': existing_job.next_run_time,
            'trigger': str(existing_job.trigger),
            'args': existing_job.args if hasattr(existing_job, 'args') else []
        }
    
    return render_template(
        'admin/schedule.html',
        job=job_info,
        institution=g.user.institution
    )


# ====================================================================
# HELPER FUNCTIONS FOR SCHEDULING
# ====================================================================


def get_day_number(day_name):
    """Convert day name to cron day number (0=Monday, 6=Sunday)"""
    days = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    return days.get(day_name.lower(), 0)


def send_scheduled_report(inst_id, report_type, email, report_format):
    """
    Generate and send scheduled report.
    This function is called by the scheduler.
    """
    try:
        current_app.logger.info(
            f"Generating {report_type} report for institution {inst_id} "
            f"in {report_format} format to {email}"
        )
        
        # Generate report based on type
        if report_type == 'attendance':
            report_data = generate_attendance_report(inst_id)
        elif report_type == 'summary':
            report_data = generate_summary_report(inst_id)
        elif report_type == 'detailed':
            report_data = generate_detailed_report(inst_id)
        elif report_type == 'analytics':
            report_data = generate_analytics_report(inst_id)
        else:
            report_data = generate_attendance_report(inst_id)
        
        # Convert to requested format
        if report_format == 'pdf':
            report_file = generate_pdf_report(report_data)
            mime_type = 'application/pdf'
            extension = 'pdf'
        elif report_format == 'excel':
            report_file = generate_excel_report(report_data)
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            extension = 'xlsx'
        elif report_format == 'csv':
            report_file = generate_csv_report(report_data)
            mime_type = 'text/csv'
            extension = 'csv'
        else:
            report_file = generate_pdf_report(report_data)
            mime_type = 'application/pdf'
            extension = 'pdf'
        
        # Send email
        from ..utils import send_email
        
        filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
        
        send_email(
            subject=f'📊 {report_type.upper()} Report - {datetime.now().strftime("%d %b %Y")}',
            recipients=[email],
            text_body=f'Your {report_type} report is attached.',
            html_body=f'<h2>Your {report_type} report is attached.</h2><p>Generated on {datetime.now().strftime("%d %b %Y at %H:%M")}</p>',
            attachments=[(filename, mime_type, report_file)]
        )
        
        current_app.logger.info(f"Report sent successfully to {email}")
        
    except Exception as e:
        current_app.logger.error(f"Error in send_scheduled_report: {str(e)}")


def generate_attendance_report(inst_id):
    """Generate attendance report data"""
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    records = db.session.query(
        Student.name,
        ClassBatch.name.label('class_name'),
        func.count(Attendance.id).label('total'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present')
    ).select_from(Attendance).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date.between(thirty_days_ago, today)
    ).group_by(Student.id, Student.name, ClassBatch.id, ClassBatch.name).all()
    
    return records


def generate_summary_report(inst_id):
    """Generate summary report data"""
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    total_records = Attendance.query.join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date.between(thirty_days_ago, today)
    ).count()
    
    total_present = Attendance.query.join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id,
        Attendance.date.between(thirty_days_ago, today),
        Attendance.status == 'present'
    ).count()
    
    return {
        'total_records': total_records,
        'total_present': total_present,
        'attendance_rate': (total_present / total_records * 100) if total_records > 0 else 0
    }


def generate_detailed_report(inst_id):
    """Generate detailed report with all metrics"""
    return generate_attendance_report(inst_id)


def generate_analytics_report(inst_id):
    """Generate analytics report"""
    return generate_summary_report(inst_id)


def generate_pdf_report(data):
    """Convert report data to PDF"""
    # TODO: Implement PDF generation using reportlab or similar
    return b"PDF Report Data"


def generate_excel_report(data):
    """Convert report data to Excel"""
    # TODO: Implement Excel generation using openpyxl or similar
    return b"Excel Report Data"


def generate_csv_report(data):
    """Convert report data to CSV"""
    # TODO: Implement CSV generation
    return b"CSV Report Data"

    return render_template('admin/schedule.html', job=job)
