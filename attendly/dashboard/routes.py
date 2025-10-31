# -*- coding: utf-8 -*-
"""
Handles routes for the main dashboard and its related API endpoints.
Includes real-time data updates, error handling, and performance optimizations.
"""

# --- Standard Library Imports ---
from datetime import datetime, timedelta
import logging

# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, g, jsonify, redirect, url_for, current_app
from sqlalchemy import desc, func, and_
from ..extensions import db

# --- Local Application Imports ---
from ..models import Student, Attendance, MedicalLeave, Subject, ClassBatch, Institution
from ..utils import (
    login_required, 
    get_current_ist, 
    get_attendance_leaderboard,
    get_ai_insights, 
    get_live_chart_data, 
    get_live_student_lists,
    get_dashboard_statistics
)

# Setup logging
logger = logging.getLogger(__name__)

dashboard_bp = Blueprint('dashboard', __name__)


# ====================================================================
# INDEX ROUTE
# ====================================================================

@dashboard_bp.route('/')
def index():
    """Redirect to dashboard or login"""
    return redirect(url_for('dashboard.dashboard') if g.user else url_for('auth.login'))


# ====================================================================
# MAIN DASHBOARD ROUTE
# ====================================================================

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Main dashboard displaying attendance statistics, 
    leaderboards, insights, and pending leaves.
    """
    inst_id = g.user.institution_id
    
    # --- Initialize Default Values ---
    pending_leaves_count = 0
    approved_leaves_count = 0
    leave_balance = 12
    pending_admin_leaves = 0
    pending_leaves = []
    student_counts = {"total": 0, "present": 0}
    student_lists = {"all": [], "present": [], "absent": []}
    chart_data = {"labels": [], "values": []}
    leaderboard = []
    insights = {"at_risk_count": 0, "anomaly_message": None}
    all_classes = []
    on_leave_count = 0
    subjects_today = []
    
    # Get current date
    current_date = get_current_ist().date()
    current_date_str = current_date.strftime('%Y-%m-%d')
    
    # --- Handle Missing Institution ---
    if not inst_id:
        logger.warning(f"User {g.user.username} has no institution assigned")
        return render_template(
            'dashboard/dashboard.html',
            student_counts=student_counts,
            all_classes=all_classes,
            student_lists=student_lists,
            chart_data=chart_data,
            leaderboard=leaderboard,
            insights=insights,
            selected_class_id=None,
            selected_date=current_date_str,
            on_leave_count=on_leave_count,
            subjects_today=subjects_today,
            pending_leaves_count=pending_leaves_count,
            approved_leaves_count=approved_leaves_count,
            leave_balance=leave_balance,
            pending_admin_leaves=pending_admin_leaves,
            pending_leaves=pending_leaves
        )
    
    try:
        # --- Get Filters ---
        selected_class_id = request.args.get('class_id', default=None, type=int)
        selected_date_str = request.args.get('filter_date', default=current_date_str)
        
        # Parse selected date
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            # Ensure date is not in future
            if selected_date > current_date:
                selected_date = current_date
                selected_date_str = current_date_str
        except (ValueError, TypeError):
            selected_date = current_date
            selected_date_str = current_date_str
        
        # --- Get All Classes ---
        all_classes = ClassBatch.query.filter_by(
            institution_id=inst_id
        ).order_by(ClassBatch.name).all()
        
        # Validate selected class
        if selected_class_id:
            class_exists = ClassBatch.query.filter_by(
                id=selected_class_id, 
                institution_id=inst_id
            ).first()
            if not class_exists:
                selected_class_id = None
        
        # --- Get Students Query ---
        students_query = db.session.query(Student.id).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        )
        if selected_class_id:
            students_query = students_query.filter(Student.class_batch_id == selected_class_id)
        
        all_student_ids = [s_id for s_id, in students_query.all()]
        total_students = len(all_student_ids)
        
        # --- Calculate Attendance Statistics ---
        present_today_count = 0
        absent_today_count = 0
        leave_today_count = 0
        
        if total_students > 0:
            present_today_count = Attendance.query.filter(
                Attendance.student_id.in_(all_student_ids),
                Attendance.date == selected_date,
                Attendance.status == 'present'
            ).distinct(Attendance.student_id).count()
            
            absent_today_count = Attendance.query.filter(
                Attendance.student_id.in_(all_student_ids),
                Attendance.date == selected_date,
                Attendance.status == 'absent'
            ).distinct(Attendance.student_id).count()
            
            leave_today_count = MedicalLeave.query.filter(
                MedicalLeave.student_id.in_(all_student_ids),
                MedicalLeave.start_date <= selected_date,
                MedicalLeave.end_date >= selected_date,
                MedicalLeave.status == 'approved'
            ).distinct(MedicalLeave.student_id).count()
        
        student_counts = {
            "total": total_students, 
            "present": present_today_count,
            "absent": absent_today_count,
            "leave": leave_today_count
        }
        
        on_leave_count = leave_today_count
        
        # --- Get Subjects Today ---
        subjects_today_query = db.session.query(Subject.name).distinct().join(Attendance).filter(
            Attendance.student_id.in_(all_student_ids),
            Attendance.date == selected_date
        )
        subjects_today = [row[0] for row in subjects_today_query.all()]
        
        # --- Handle Pending Leaves (Role-Based) ---
        if g.user.role == 'student' and g.user.student_profile:
            # For Students
            pending_leaves_count = MedicalLeave.query.filter_by(
                student_id=g.user.student_profile.id, 
                status='pending'
            ).count()
            
            approved_leaves_count = MedicalLeave.query.filter_by(
                student_id=g.user.student_profile.id, 
                status='approved'
            ).count()
            
            leave_balance = max(0, 12 - approved_leaves_count)
            
            # Get recent pending leaves
            pending_leaves = MedicalLeave.query.filter_by(
                student_id=g.user.student_profile.id,
                status='pending'
            ).order_by(desc(MedicalLeave.created_at)).limit(5).all()
        
        elif g.user.role in ['admin', 'teacher']:
            # For Admin and Teachers
            pending_admin_leaves = MedicalLeave.query.filter_by(
                institution_id=inst_id,
                status='pending'
            ).count()
            
            # Get recent pending leaves
            pending_leaves = MedicalLeave.query.filter_by(
                institution_id=inst_id,
                status='pending'
            ).order_by(desc(MedicalLeave.created_at)).limit(5).all()
        
        # --- Fetch Data Using Helper Functions ---
        try:
            leaderboard = get_attendance_leaderboard(inst_id, class_id=selected_class_id) or []
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {str(e)}")
            leaderboard = []
        
        try:
            insights = get_ai_insights(inst_id, class_id=selected_class_id) or {"at_risk_count": 0}
        except Exception as e:
            logger.error(f"Error fetching insights: {str(e)}")
            insights = {"at_risk_count": 0}
        
        try:
            chart_data = get_live_chart_data(inst_id, class_id=selected_class_id) or {"labels": [], "values": []}
        except Exception as e:
            logger.error(f"Error fetching chart data: {str(e)}")
            chart_data = {"labels": [], "values": []}
        
        try:
            student_lists = get_live_student_lists(inst_id, date=selected_date, class_id=selected_class_id) or {"all": [], "present": [], "absent": []}
        except Exception as e:
            logger.error(f"Error fetching student lists: {str(e)}")
            student_lists = {"all": [], "present": [], "absent": []}
        
    except Exception as e:
        logger.error(f"Error loading dashboard for user {g.user.username}: {str(e)}")
        current_app.logger.exception("Dashboard error")
    
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
        subjects_today=subjects_today,
        pending_leaves_count=pending_leaves_count,
        approved_leaves_count=approved_leaves_count,
        leave_balance=leave_balance,
        pending_admin_leaves=pending_admin_leaves,
        pending_leaves=pending_leaves
    )


# ====================================================================
# API ENDPOINT - REAL-TIME DASHBOARD DATA
# ====================================================================

@dashboard_bp.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    """
    API endpoint for real-time dashboard data updates.
    Used for live refresh without page reload.
    """
    try:
        inst_id = g.user.institution_id
        
        # Handle missing institution
        if not inst_id:
            return jsonify({
                "success": False,
                "error": "No institution assigned",
                "student_counts": {"total": 0, "present": 0},
                "student_lists": {"all": [], "present": [], "absent": []},
                "chart_data": {"labels": [], "values": []}
            }), 400
        
        # Get parameters
        selected_class_id = request.args.get('class_id', default=None, type=int)
        selected_date_str = request.args.get('date', default=get_current_ist().strftime('%Y-%m-%d'))
        
        # Parse date
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = get_current_ist().date()
        
        # Validate class exists
        if selected_class_id:
            class_exists = ClassBatch.query.filter_by(
                id=selected_class_id,
                institution_id=inst_id
            ).first()
            if not class_exists:
                selected_class_id = None
        
        # Fetch data with error handling
        try:
            student_counts = get_dashboard_statistics(
                inst_id, 
                selected_date, 
                class_id=selected_class_id
            ) or {"total": 0, "present": 0}
        except Exception as e:
            logger.error(f"Error fetching statistics: {str(e)}")
            student_counts = {"total": 0, "present": 0}
        
        try:
            student_lists = get_live_student_lists(
                inst_id, 
                date=selected_date, 
                class_id=selected_class_id
            ) or {"all": [], "present": [], "absent": []}
        except Exception as e:
            logger.error(f"Error fetching student lists: {str(e)}")
            student_lists = {"all": [], "present": [], "absent": []}
        
        try:
            chart_data = get_live_chart_data(
                inst_id, 
                class_id=selected_class_id
            ) or {"labels": [], "values": []}
        except Exception as e:
            logger.error(f"Error fetching chart data: {str(e)}")
            chart_data = {"labels": [], "values": []}
        
        # Return success response
        return jsonify({
            "success": True,
            "student_counts": student_counts,
            "student_lists": student_lists,
            "chart_data": chart_data,
            "timestamp": get_current_ist().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"API Error in dashboard-data: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Could not retrieve dashboard data"
        }), 500


# ====================================================================
# API ENDPOINT - ATTENDANCE SUMMARY
# ====================================================================

@dashboard_bp.route('/api/attendance-summary')
@login_required
def api_attendance_summary():
    """
    Get attendance summary statistics for a date range.
    """
    try:
        inst_id = g.user.institution_id
        
        if not inst_id:
            return jsonify({"error": "No institution"}), 400
        
        # Get date range
        days = request.args.get('days', default=30, type=int)
        start_date = get_current_ist().date() - timedelta(days=days)
        end_date = get_current_ist().date()
        
        # Get statistics
        total_records = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id,
            Attendance.date.between(start_date, end_date)
        ).count()
        
        total_present = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id,
            Attendance.date.between(start_date, end_date),
            Attendance.status == 'present'
        ).count()
        
        total_absent = total_records - total_present
        attendance_rate = (total_present / total_records * 100) if total_records > 0 else 0
        
        return jsonify({
            "success": True,
            "total_records": total_records,
            "total_present": total_present,
            "total_absent": total_absent,
            "attendance_rate": round(attendance_rate, 2),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }), 200
        
    except Exception as e:
        logger.error(f"API Error in attendance-summary: {str(e)}")
        return jsonify({"error": "Could not retrieve summary"}), 500


# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def get_institution_stats(inst_id):
    """
    Get overall institution statistics.
    """
    try:
        total_students = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id
        ).count()
        
        total_classes = ClassBatch.query.filter_by(institution_id=inst_id).count()
        
        today = get_current_ist().date()
        today_attendance = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == inst_id,
            Attendance.date == today
        ).count()
        
        return {
            "total_students": total_students,
            "total_classes": total_classes,
            "today_attendance": today_attendance
        }
    except Exception as e:
        logger.error(f"Error calculating institution stats: {str(e)}")
        return {
            "total_students": 0,
            "total_classes": 0,
            "today_attendance": 0
        }
