# -*- coding: utf-8 -*-
"""
This blueprint handles all teacher-related functionality.
Includes attendance marking, class management, and reporting.
"""

# --- Standard Library Imports ---
from datetime import datetime, timedelta
from sqlalchemy import desc

# --- Third-Party Library Imports ---
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, g, jsonify, current_app)
from sqlalchemy import and_, func

# --- Local Application Imports ---
from ..extensions import db
from ..models import Student, Attendance, Subject, TeacherAssignment, ClassBatch, MedicalLeave
from ..utils import teacher_required, get_current_ist


teacher_bp = Blueprint('teacher', __name__)


# ===== MARK ATTENDANCE =====
@teacher_bp.route('/mark_attendance', methods=['GET', 'POST'])
@teacher_required
def mark_attendance():
    """Mark attendance - only for assigned classes/subjects"""
    
    if request.method == 'POST':
        class_id = request.form.get('class_batch_id')
        subject_id = request.form.get('subject_id')
        date_str = request.form.get('date')
        
        # SECURITY: Verify teacher is assigned to this class+subject combination
        assignment = TeacherAssignment.query.filter_by(
            teacher_id=g.user.id,
            class_batch_id=class_id,
            subject_id=subject_id
        ).first()
        
        if not assignment:
            flash('❌ You are not assigned to teach this subject in this class!', 'danger')
            return redirect(url_for('teacher.mark_attendance'))
        
        # Parse date
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('❌ Invalid date format!', 'danger')
            return redirect(url_for('teacher.mark_attendance'))
        
        # Prevent marking attendance for future dates
        if date_obj > datetime.now().date():
            flash('❌ Cannot mark attendance for future dates!', 'danger')
            return redirect(url_for('teacher.mark_attendance'))
        
        # Process attendance
        students = Student.query.filter_by(class_batch_id=class_id).all()
        marked_count = 0
        
        for student in students:
            status = request.form.get(f'status_{student.id}', 'absent')
            
            # Validate status
            if status not in ['present', 'absent', 'leave']:
                status = 'absent'
            
            existing = Attendance.query.filter_by(
                student_id=student.id,
                subject_id=subject_id,
                date=date_obj
            ).first()
            
            if existing:
                existing.status = status
                existing.marked_by = 'teacher'
                existing.updated_at = datetime.now()
            else:
                new_attendance = Attendance(
                    student_id=student.id,
                    subject_id=subject_id,
                    date=date_obj,
                    status=status,
                    marked_by='teacher'
                )
                db.session.add(new_attendance)
            
            marked_count += 1
        
        db.session.commit()
        flash(f'✅ Attendance marked successfully for {marked_count} students!', 'success')
        return redirect(url_for('teacher.mark_attendance'))
    
    # GET request - load data
    # Get all teacher assignments for current teacher
    teacher_assignments = TeacherAssignment.query.filter_by(teacher_id=g.user.id).all()
    
    # Check if teacher has any assignments
    if not teacher_assignments:
        flash('⚠️ You are not assigned to teach any classes yet.', 'warning')
        return render_template('teacher/mark_attendance.html',
                              classes=[],
                              class_subjects={},
                              students=[],
                              attendance_data={},
                              subjects=[],
                              selected_class_id=None,
                              selected_subject_id=None,
                              selected_date=None)
    
    # Build class-subject mapping
    assigned_classes = {}  # {class_id: class_object}
    class_subjects = {}    # {class_id: [subjects]}
    
    for assignment in teacher_assignments:
        class_id = assignment.class_batch_id
        
        if class_id not in assigned_classes:
            assigned_classes[class_id] = assignment.class_batch
            class_subjects[class_id] = []
        
        # Avoid duplicates
        if assignment.subject not in class_subjects[class_id]:
            class_subjects[class_id].append(assignment.subject)
    
    classes = list(assigned_classes.values())
    
    # Get selected parameters
    selected_class_id = request.args.get('class_batch_id', type=int)
    selected_subject_id = request.args.get('subject_id', type=int)
    selected_date = request.args.get('date')
    
    # Default to today if no date selected
    if not selected_date:
        selected_date = get_current_ist().strftime('%Y-%m-%d')
    
    students = []
    attendance_data = {}
    subjects = []
    
    if selected_class_id and selected_subject_id:
        # Verify authorization - teacher must be assigned to this class+subject
        assignment = TeacherAssignment.query.filter_by(
            teacher_id=g.user.id,
            class_batch_id=selected_class_id,
            subject_id=selected_subject_id
        ).first()
        
        if assignment:
            # Get subjects for this class
            subjects = class_subjects.get(selected_class_id, [])
            
            # Get students in this class (ordered by name)
            students = Student.query.filter_by(class_batch_id=selected_class_id)\
                                   .order_by(Student.name).all()
            
            # Get existing attendance records for this date
            if selected_date:
                try:
                    date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
                    attendance_records = Attendance.query.filter_by(
                        subject_id=selected_subject_id,
                        date=date_obj
                    ).all()
                    
                    for record in attendance_records:
                        attendance_data[record.student_id] = record.status
                except (ValueError, TypeError):
                    flash('⚠️ Invalid date format.', 'warning')
        else:
            flash('❌ You are not authorized to mark attendance for this combination.', 'danger')
    else:
        # No selection yet - get all subjects teacher teaches (for the dropdown)
        all_subjects_set = set()
        for subjects_list in class_subjects.values():
            all_subjects_set.update(subjects_list)
        subjects = list(all_subjects_set)
    
    return render_template('teacher/mark_attendance.html',
                          classes=classes,
                          class_subjects=class_subjects,
                          students=students,
                          attendance_data=attendance_data,
                          subjects=subjects,
                          selected_class_id=selected_class_id,
                          selected_subject_id=selected_subject_id,
                          selected_date=selected_date)


# ===== TEACHER CLASSES =====
@teacher_bp.route('/classes')
@teacher_required
def teacher_classes():
    """Display teacher's assigned classes with statistics"""
    
    teacher_assignments = TeacherAssignment.query.filter_by(teacher_id=g.user.id).all()
    
    # Check if teacher has any assignments
    if not teacher_assignments:
        flash('⚠️ You are not assigned to teach any classes yet.', 'warning')
        return render_template('teacher/teacher_classes.html',
                              classes=[],
                              total_students=0,
                              total_subjects=0,
                              class_attendance={})
    
    # Build unique classes list
    assigned_class_ids = set(a.class_batch_id for a in teacher_assignments)
    classes = ClassBatch.query.filter(ClassBatch.id.in_(list(assigned_class_ids))).all()
    
    # Calculate total students across all assigned classes
    total_students = 0
    for cls in classes:
        total_students += len(cls.students)
    
    # Calculate total unique subjects
    all_subjects = set()
    for assignment in teacher_assignments:
        all_subjects.add(assignment.subject)
    total_subjects = len(all_subjects)
    
    # Calculate attendance rate per class (last 30 days)
    class_attendance = {}
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    
    for cls in classes:
        student_ids = [s.id for s in cls.students]
        
        if student_ids:
            attendance_query = Attendance.query.filter(
                Attendance.student_id.in_(student_ids),
                Attendance.date >= thirty_days_ago
            )
            
            total_records = attendance_query.count()
            total_present = attendance_query.filter_by(status='present').count()
            
            if total_records > 0:
                class_attendance[cls.id] = (total_present / total_records) * 100
            else:
                class_attendance[cls.id] = 0
        else:
            class_attendance[cls.id] = 0
    
    return render_template('teacher/teacher_classes.html',
                          classes=classes,
                          total_students=total_students,
                          total_subjects=total_subjects,
                          class_attendance=class_attendance)


# ===== TEACHER REPORTS =====
@teacher_bp.route('/reports')
@teacher_required
def teacher_reports():
    """Display teacher's attendance reports with filtering"""
    
    # Get teacher's assigned classes
    teacher_assignments = TeacherAssignment.query.filter_by(teacher_id=g.user.id).all()
    assigned_class_ids = set(a.class_batch_id for a in teacher_assignments)
    
    if not assigned_class_ids:
        flash('⚠️ You are not assigned to teach any classes yet.', 'warning')
        return render_template('teacher/teacher_reports_summary.html',
                              report_data=[],
                              classes=[],
                              selected_class_id=None,
                              start_date=None,
                              end_date=None,
                              summary={'overall_attendance_percent': 0, 'total_present': 0, 'total_absent': 0})
    
    classes = ClassBatch.query.filter(ClassBatch.id.in_(list(assigned_class_ids))).all()
    
    # Get date range
    selected_class_id = request.args.get('class_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Default date range (last 30 days)
    today = datetime.now().date()
    if not start_date_str:
        start_date = today - timedelta(days=30)
        start_date_str = start_date.strftime('%Y-%m-%d')
    else:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = today - timedelta(days=30)
            start_date_str = start_date.strftime('%Y-%m-%d')
    
    if not end_date_str:
        end_date = today
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            end_date = today
            end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Build query
    base_query = Attendance.query.join(Student).join(ClassBatch).filter(
        ClassBatch.id.in_(list(assigned_class_ids)),
        Attendance.date.between(start_date, end_date)
    )
    
    if selected_class_id and selected_class_id in assigned_class_ids:
        base_query = base_query.filter(ClassBatch.id == selected_class_id)
    
    # Get all records
    total_records = base_query.count()
    total_present = base_query.filter(Attendance.status == 'present').count()
    total_absent = total_records - total_present
    
    summary = {
        'overall_attendance_percent': (total_present / total_records * 100) if total_records > 0 else 0,
        'total_present': total_present,
        'total_absent': total_absent
    }
    
    # Get detailed report
    report_data_query = db.session.query(
        Student.name,
        ClassBatch.name.label('class_name'),
        func.count(Attendance.id).label('total_days'),
        func.sum(func.cast(Attendance.status == 'present', db.Integer)).label('present_days')
    ).select_from(Attendance).join(Student).join(ClassBatch).filter(
        ClassBatch.id.in_(list(assigned_class_ids)),
        Attendance.date.between(start_date, end_date)
    ).group_by(Student.id, Student.name, ClassBatch.id, ClassBatch.name).all()
    
    report_data = []
    for name, class_name, total_days, present_days in report_data_query:
        present = present_days or 0
        absent = total_days - present
        percentage = (present / total_days * 100) if total_days > 0 else 0
        report_data.append({
            'student': name,
            'class_name': class_name,
            'total_days': total_days,
            'present': present,
            'absent': absent,
            'attendance_percent': round(percentage, 1)
        })
    
    return render_template('teacher/teacher_reports_summary.html',
                          report_data=report_data,
                          classes=classes,
                          selected_class_id=selected_class_id,
                          start_date=start_date_str,
                          end_date=end_date_str,
                          summary=summary)


# ===== VIEW CLASS STUDENTS =====
@teacher_bp.route('/classes/<int:class_id>/students')
@teacher_required
def view_class_students(class_id):
    """View students in a class assigned to teacher"""
    
    # Verify teacher is assigned to this class
    assignment = TeacherAssignment.query.filter_by(
        teacher_id=g.user.id,
        class_batch_id=class_id
    ).first()
    
    if not assignment:
        flash('❌ You are not assigned to teach this class!', 'danger')
        return redirect(url_for('teacher.teacher_classes'))
    
    class_batch = ClassBatch.query.get_or_404(class_id)
    students = Student.query.filter_by(class_batch_id=class_id).order_by(Student.name).all()
    
    # Calculate attendance for each student (last 30 days)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    student_stats = {}
    
    for student in students:
        attendance_query = Attendance.query.filter_by(
            student_id=student.id,
            status='present'
        ).filter(Attendance.date >= thirty_days_ago)
        
        total_query = Attendance.query.filter_by(
            student_id=student.id
        ).filter(Attendance.date >= thirty_days_ago)
        
        present = attendance_query.count()
        total = total_query.count()
        
        if total > 0:
            attendance_pct = (present / total) * 100
        else:
            attendance_pct = 0
        
        student_stats[student.id] = {
            'present': present,
            'total': total,
            'percentage': round(attendance_pct, 1)
        }
    
    return render_template('teacher/view_class_students.html',
                          class_batch=class_batch,
                          students=students,
                          student_stats=student_stats)


# ===== HANDLE LEAVE REQUESTS =====
@teacher_bp.route('/leaves/<int:leave_id>/<action>', methods=['POST'])
@teacher_required
def handle_leave(leave_id, action):
    """Handle leave approval/denial (for teachers who can approve)"""
    
    leave = MedicalLeave.query.get_or_404(leave_id)
    
    # Verify teacher's institution matches
    if leave.institution_id != g.user.institution_id:
        flash('❌ Unauthorized access!', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    if action == 'approve':
        leave.status = 'approved'
        flash(f'✅ Leave for {leave.student.name} has been approved.', 'success')
    elif action == 'deny':
        leave.status = 'denied'
        flash(f'❌ Leave for {leave.student.name} has been denied.', 'warning')
    else:
        flash('❌ Invalid action!', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard.dashboard'))
