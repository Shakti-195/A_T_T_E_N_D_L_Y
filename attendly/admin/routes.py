# -*- coding: utf-8 -*-
"""
Handles all administrative tasks for an institution.
"""
# --- Standard Library Imports ---
from datetime import datetime, timedelta
import time

# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case, extract, desc

# --- Local Application Imports ---
from ..extensions import db, scheduler
from ..models import Student, ClassBatch, Subject, User, Attendance
from ..utils import admin_required

# CORRECTED: Removed template_folder and static_folder arguments
admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/setup', methods=['GET', 'POST'])
@admin_required
def setup():
    if request.method == 'POST':
        if 'class_batch_name' in request.form and request.form['class_batch_name']:
            new_class = ClassBatch(
                name=request.form['class_batch_name'], 
                institution_id=g.user.institution_id
            )
            db.session.add(new_class)
            flash('New class/batch created.', 'success')
            
        if 'subject_name' in request.form and request.form['subject_name']:
            new_subject = Subject(name=request.form['subject_name'])
            db.session.add(new_subject)
            flash('New subject created.', 'success')
            
        db.session.commit()
        return redirect(url_for('admin.setup'))
    
    unassigned = Student.query.join(ClassBatch).filter(
        Student.class_batch_id == None, 
        ClassBatch.institution_id == g.user.institution_id
    ).all()
    
    classes = ClassBatch.query.filter_by(institution_id=g.user.institution_id).options(
        joinedload(ClassBatch.teachers)
    ).all()
    
    teachers = User.query.filter_by(
        role='teacher', 
        institution_id=g.user.institution_id
    ).all()
    
    subjects = Subject.query.all()
    
    return render_template('admin/setup.html', 
                           unassigned_students=unassigned, 
                           classes_batches=classes, 
                           teachers=teachers, 
                           subjects=subjects, 
                           institution=g.user.institution)

@admin_bp.route('/assign_student_to_class/<int:student_id>', methods=['POST'])
@admin_required
def assign_student_to_class(student_id):
    student = db.session.get(Student, student_id)
    class_id = request.form.get('class_batch_id')
    if student and class_id:
        student.class_batch_id = class_id
        db.session.commit()
        flash(f'{student.name} assigned.', 'success')
    return redirect(url_for('admin.setup'))

@admin_bp.route('/assign_teacher_to_class/<int:class_id>', methods=['POST'])
@admin_required
def assign_teacher_to_class(class_id):
    class_batch = db.session.get(ClassBatch, class_id)
    teacher_id = request.form.get('teacher_id')
    teacher = db.session.get(User, teacher_id)
    
    if class_batch and teacher and class_batch.institution_id == g.user.institution_id:
        if teacher not in class_batch.teachers:
            class_batch.teachers.append(teacher)
            db.session.commit()
            flash(f'Teacher assigned to {class_batch.name}.', 'success')
        else:
            flash('Teacher is already assigned to this class.', 'info')
    return redirect(url_for('admin.setup'))

@admin_bp.route('/unassign_teacher_from_class/<int:class_id>/<int:teacher_id>', methods=['POST'])
@admin_required
def unassign_teacher_from_class(class_id, teacher_id):
    class_batch = db.session.get(ClassBatch, class_id)
    teacher = db.session.get(User, teacher_id)
    
    if class_batch and teacher and class_batch.institution_id == g.user.institution_id:
        if teacher in class_batch.teachers:
            class_batch.teachers.remove(teacher)
            db.session.commit()
            flash(f'Teacher unassigned from {class_batch.name}.', 'success')
        else:
            flash('Teacher is not assigned to this class.', 'info')
    return redirect(url_for('admin.setup'))

@admin_bp.route('/delete_class_batch/<int:class_id>', methods=['POST'])
@admin_required
def delete_class_batch(class_id):
    class_to_delete = db.session.get(ClassBatch, class_id)
    
    if class_to_delete and class_to_delete.institution_id == g.user.institution_id:
        if not class_to_delete.students.first():
            db.session.delete(class_to_delete)
            db.session.commit()
            flash('Class/Batch deleted.', 'success')
        else:
            flash('Cannot delete a class with students assigned to it.', 'danger')
    return redirect(url_for('admin.setup'))

@admin_bp.route('/delete_subject/<int:subject_id>', methods=['POST'])
@admin_required
def delete_subject(subject_id):
    subject_to_delete = db.session.get(Subject, subject_id)
    if subject_to_delete and not subject_to_delete.attendances.first():
        db.session.delete(subject_to_delete)
        db.session.commit()
        flash('Subject deleted.', 'success')
    else:
        flash('Cannot delete a subject with attendance records.', 'danger')
    return redirect(url_for('admin.setup'))

@admin_bp.route('/reports')
@admin_required
def reports():
    today = datetime.now().date()
    start_date_str = request.args.get('start_date', (today - timedelta(days=29)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Invalid date format.', 'danger')
        start_date = today - timedelta(days=29)
        end_date = today

    base_query = Attendance.query.join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id,
        Attendance.date.between(start_date, end_date)
    )

    total_records = base_query.count()
    total_present = base_query.filter(Attendance.status == 'present').count()
    
    summary = {
        'overall_attendance_percent': (total_present / total_records * 100) if total_records > 0 else 0,
        'total_present': total_present,
        'total_absent': total_records - total_present
    }
    
    subject_performance = db.session.query(
        Subject.name,
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
    ).select_from(Attendance).join(Subject).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id,
        Attendance.date.between(start_date, end_date)
    ).group_by(Subject.name).all()
    
    report_data_query = db.session.query(
        Student.name,
        func.count(Attendance.id).label('total_days'),
        func.sum(case((Attendance.status == 'present', 1), else_=0)).label('present_days')
    ).select_from(Attendance).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == g.user.institution_id,
        Attendance.date.between(start_date, end_date)
    ).group_by(Student.name).all()
    
    processed_report = []
    for name, total_days, present_days in report_data_query:
        present = present_days or 0
        absent = total_days - present
        percentage = (present / total_days * 100) if total_days > 0 else 0
        processed_report.append({
            'student': name,
            'total_days': total_days,
            'present': present,
            'absent': absent,
            'attendance_percent': round(percentage, 1)
        })
    
    return render_template('admin/reports.html', 
                           summary=summary, 
                           start_date=start_date.strftime('%Y-%m-%d'), 
                           end_date=end_date.strftime('%Y-%m-%d'), 
                           subject_performance=[{'subject': s, 'percentage': round(p, 1)} for s, p in subject_performance], 
                           report_data=processed_report)

@admin_bp.route('/analytics')
@admin_required
def analytics():
    inst_id = g.user.institution_id
    
    heatmap_data = db.session.query(
        extract('isodow', Attendance.date).label('day_of_week'),
        extract('hour', Attendance.created_at).label('hour_of_day'),
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('percentage')
    ).join(Student).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id
    ).group_by('day_of_week', 'hour_of_day').all()
    
    heatmap_json = [{'day_of_week': d % 7, 'hour_of_day': h, 'percentage': p} for d, h, p in heatmap_data]
    
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    
    student_engagement = db.session.query(
        Student.name,
        (func.sum(case((Attendance.status == 'present', 1), else_=0)) * 100.0 / func.count(Attendance.id)).label('engagement_score')
    ).join(Attendance).join(ClassBatch).filter(
        ClassBatch.institution_id == inst_id, 
        Attendance.date >= thirty_days_ago
    ).group_by(Student.name).order_by(desc('engagement_score')).limit(10).all()
    
    return render_template('admin/analytics.html', 
                           heatmap_data=heatmap_json, 
                           student_engagement=student_engagement)

@admin_bp.route('/schedule', methods=['GET', 'POST'])
@admin_required
def schedule():
    job_id = 'Weekly Report Job'
    job = scheduler.get_job(job_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'schedule':
            day_of_week = request.form.get('day_of_week')
            hour = request.form.get('hour')
            try:
                if job:
                    scheduler.modify_job(job_id, trigger='cron', day_of_week=day_of_week, hour=hour, minute=0)
                else:
                    # Point to the function using its full import path as a string
                    scheduler.add_job(id=job_id, func='attendly.utils:email_reports_job', trigger='cron', day_of_week=day_of_week, hour=hour, minute=0)
                flash(f'Report schedule updated: {day_of_week.capitalize()} at {hour}:00', 'success')
            except Exception as e:
                flash(f'Failed to schedule report: {e}', 'danger')
        
        elif action == 'cancel':
            if job:
                scheduler.remove_job(job_id)
                flash('Report schedule canceled.', 'warning')
            else:
                flash('No scheduled report to cancel.', 'info')

        elif action == 'run_now':
             # Point to the function using its full import path as a string
             scheduler.add_job(id=f"{job_id}_immediate_{int(time.time())}", func='attendly.utils:email_reports_job', trigger='date')
             flash('Report generation started. Admins will receive it shortly.', 'info')

        return redirect(url_for('admin.schedule'))

    return render_template('admin/schedule.html', job=job)

