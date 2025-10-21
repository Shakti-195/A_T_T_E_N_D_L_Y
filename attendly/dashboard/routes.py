# -*- coding: utf-8 -*-
"""
Handles routes for the main dashboard and its related API endpoints.
"""
# --- Standard Library Imports ---
from datetime import datetime

# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, g, jsonify, redirect, url_for
from ..extensions import db
# --- Local Application Imports ---
from ..models import Student, Attendance, MedicalLeave, Subject, ClassBatch
from ..utils import (login_required, get_current_ist, get_attendance_leaderboard,
                     get_ai_insights, get_live_chart_data, get_live_student_lists,
                     get_dashboard_statistics)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    return redirect(url_for('dashboard.dashboard') if g.user else url_for('auth.login'))

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    inst_id = g.user.institution_id
    if not inst_id:
        # If user has no institution, show a limited dashboard
        return render_template(
            'dashboard/dashboard.html',
            student_counts={"total": 0, "present": 0},
            all_classes=[],
            student_lists={"all": [], "present": [], "absent": []},
            chart_data={"labels": [], "values": []},
            leaderboard=[],
            insights={"at_risk_count": 0, "anomaly_message": None},
            selected_class_id=None,
            selected_date=get_current_ist().strftime('%Y-%m-%d'),
            on_leave_count=0,
            subjects_today=[]
        )

    # --- Filters ---
    selected_class_id = request.args.get('class_id', default=None, type=int)
    selected_date_str = request.args.get('filter_date', default=get_current_ist().strftime('%Y-%m-%d'))
    
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        selected_date = get_current_ist().date()
        selected_date_str = selected_date.strftime('%Y-%m-%d')

    # --- Calculations for Cards ---
    students_query = db.session.query(Student.id).join(ClassBatch).filter(ClassBatch.institution_id == inst_id)
    if selected_class_id:
        students_query = students_query.filter(Student.class_batch_id == selected_class_id)
    all_student_ids = [s_id for s_id, in students_query.all()]
    total_students = len(all_student_ids)

    present_today_count = 0
    if total_students > 0:
        present_today_count = Attendance.query.filter(
            Attendance.student_id.in_(all_student_ids),
            Attendance.date == selected_date,
            Attendance.status == 'present'
        ).distinct(Attendance.student_id).count()

    student_counts = {"total": total_students, "present": present_today_count}
    
    on_leave_count = MedicalLeave.query.filter(
        MedicalLeave.student_id.in_(all_student_ids),
        MedicalLeave.start_date <= selected_date,
        MedicalLeave.end_date >= selected_date,
        MedicalLeave.status == 'approved'
    ).count()

    subjects_today_query = db.session.query(Subject.name).distinct().join(Attendance).filter(
        Attendance.student_id.in_(all_student_ids),
        Attendance.date == selected_date
    )
    subjects_today = [row[0] for row in subjects_today_query.all()]

    # --- Fetching data using helper functions ---
    leaderboard = get_attendance_leaderboard(inst_id, class_id=selected_class_id)
    insights = get_ai_insights(inst_id, class_id=selected_class_id)
    chart_data = get_live_chart_data(inst_id, class_id=selected_class_id)
    student_lists = get_live_student_lists(inst_id, date=selected_date, class_id=selected_class_id)
    all_classes = ClassBatch.query.filter_by(institution_id=inst_id).order_by(ClassBatch.name).all()

    return render_template(
        'dashboard/dashboard.html',
        student_counts=student_counts,
        student_lists=student_lists,
        chart_data=chart_data,
        leaderboard=leaderboard,
        insights=insights,
        all_classes=all_classes,
        selected_class_id=selected_class_id,
        selected_date=selected_date_str,
        on_leave_count=on_leave_count,
        subjects_today=subjects_today
    )

@dashboard_bp.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    try:
        inst_id = g.user.institution_id
        if not inst_id:
            return jsonify({
                "student_counts": {"total": 0, "present": 0},
                "student_lists": {"all": [], "present": [], "absent": []},
                "chart_data": {"labels": [], "values": []}
            })

        selected_class_id = request.args.get('class_id', default=None, type=int)
        selected_date_str = request.args.get('date', default=get_current_ist().strftime('%Y-%m-%d'))
        
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = get_current_ist().date()
            
        student_counts = get_dashboard_statistics(inst_id, selected_date, class_id=selected_class_id)
        student_lists = get_live_student_lists(inst_id, date=selected_date, class_id=selected_class_id)
        chart_data = get_live_chart_data(inst_id, class_id=selected_class_id)

        final_data = {
            "student_counts": student_counts,
            "student_lists": student_lists,
            "chart_data": chart_data,
        }
        return jsonify(final_data)

    except Exception as e:
        return jsonify({"error": "Could not retrieve dashboard data."}), 500

