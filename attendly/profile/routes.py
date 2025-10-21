# -*- coding: utf-8 -*-
"""
Handles user profile management, role switching, and account settings.
"""
# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, session
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename
import os

# --- Local Application Imports ---
from ..extensions import db
from ..models import User, Student, Attendance, ClassBatch
from ..utils import login_required, allowed_file

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/profile', methods=['GET', 'POST'])
@profile_bp.route('/profile/<attendly_id>', methods=['GET'])
@login_required
def profile_view(attendly_id=None):
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        if current_password and new_password:
            if g.user.check_password(current_password):
                g.user.set_password(new_password)
                db.session.commit()
                flash('Password updated successfully!', 'success')
            else:
                flash('Incorrect current password.', 'danger')
            return redirect(url_for('profile.profile_view'))
    
    # Determine which user's profile to show
    if attendly_id is None:
        user = db.session.get(User, g.user.id)
        is_own_profile = True
    else:
        user = User.query.filter_by(attendly_id=attendly_id).first()
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('dashboard.dashboard'))
        is_own_profile = (user.id == g.user.id)
    
    data = {}
    
    try:
        if user.role == 'student':
            student_profile = user.student_profile
            if student_profile:
                total_days = Attendance.query.filter_by(student_id=student_profile.id).count()
                present_days = Attendance.query.filter_by(student_id=student_profile.id, status='present').count()
                data = {
                    'attendance_percentage': round((present_days / total_days * 100), 1) if total_days > 0 else 0,
                    'total_present': present_days,
                    'total_absent': total_days - present_days
                }
            else:
                data = {'attendance_percentage': 0, 'total_present': 0, 'total_absent': 0}

        elif user.role == 'teacher':
            taught_classes = user.taught_classes
            student_count = sum(c.students.count() for c in taught_classes)
            data = {
                'class_count': len(taught_classes),
                'student_count': student_count
            }

        elif user.role == 'admin':
            inst_id = user.institution_id
            total_students = Student.query.join(ClassBatch).filter(ClassBatch.institution_id == inst_id).count()
            total_teachers = User.query.filter_by(institution_id=inst_id, role='teacher').count()
            total_classes = ClassBatch.query.filter_by(institution_id=inst_id).count()
            data = {
                'total_students': total_students,
                'total_teachers': total_teachers,
                'total_classes': total_classes
            }
            
    except Exception as e:
        flash("An error occurred while loading profile data.", "danger")

    return render_template('profile/profile.html', data=data, user=user, is_own_profile=is_own_profile)


@profile_bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user = db.session.get(User, g.user.id)
    student_profile = user.student_profile if user.role == 'student' else None
    
    if user.role == 'student' and not student_profile:
        flash('Your student profile is not linked yet. Please join an institution first.', 'warning')
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        try:
            # Update basic info
            if user.role == 'student' and student_profile:
                student_profile.name = request.form.get('name')
                student_profile.email = request.form.get('email')
                user.phone = request.form.get('phone')
                user.location = request.form.get('location')
                user.biography = request.form.get('bio')
                user.branch = request.form.get('branch')
                
                # Update student-specific fields
                student_profile.batch = request.form.get('batch')
                if request.form.get('semester'):
                    student_profile.semester = int(request.form.get('semester'))
                if request.form.get('cgpa'):
                    student_profile.cgpa = float(request.form.get('cgpa'))
                
                # Check if alumni
                if request.form.get('is_alumni'):
                    if request.form.get('graduation_year'):
                        student_profile.graduation_year = int(request.form.get('graduation_year'))
                    student_profile.semester = None
                    student_profile.cgpa = None
                
                if student_profile.user:
                    student_profile.user.email = request.form.get('email')

                # Handle photo upload
                if 'avatar' in request.files:
                    file = request.files['avatar']
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = secure_filename(f"{student_profile.id}_{file.filename}")
                        upload_folder = os.path.join(os.getcwd(), 'static', 'uploads')
                        os.makedirs(upload_folder, exist_ok=True)
                        file.save(os.path.join(upload_folder, filename))
                        user.avatar = f'/static/uploads/{filename}'
            
            elif user.role == 'teacher':
                # Update teacher info
                user.username = request.form.get('name')
                user.email = request.form.get('email')
                user.phone = request.form.get('phone')
                user.location = request.form.get('location')
                user.biography = request.form.get('bio')
                user.designation = request.form.get('designation')
                user.department = request.form.get('department')
                user.experience = request.form.get('experience')
                
            elif user.role == 'admin':
                # Update admin info
                user.username = request.form.get('name')
                user.email = request.form.get('email')
                user.phone = request.form.get('phone')
                user.location = request.form.get('location')
                user.biography = request.form.get('bio')
                user.department = request.form.get('department')
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile.profile_view'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')

    # Create a simple dummy form object for CSRF token in template
    class DummyForm:
        def __init__(self):
            self.csrf_token = ''
    
    form = DummyForm()
    
    return render_template('profile/edit_profile.html', user=user, form=form)


@profile_bp.route('/switch_role/<new_role>')
@login_required
def switch_role(new_role):
    if g.user.role == 'admin':
        if new_role in ['teacher', 'student']:
            session['view_as'] = new_role
            flash(f"Switched to {new_role.capitalize()} view.", "success")
        elif new_role == 'admin':
            session.pop('view_as', None)
            flash("Switched back to Admin view.", "success")
        else:
            flash("Invalid role specified.", "danger")
    else:
        flash("You do not have permission to switch roles.", "danger")
        
    return redirect(url_for('dashboard.dashboard'))


@profile_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    email_confirmation = request.form.get('email_confirm')

    if email_confirmation and email_confirmation.lower() == g.user.email.lower():
        try:
            user_to_delete = g.user
            db.session.delete(user_to_delete)
            db.session.commit()
            
            session.clear()
            
            flash('Your account has been permanently deleted.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while deleting your account. Please try again.', 'danger')
            return redirect(url_for('profile.profile_view'))
    else:
        flash('The email address you entered was incorrect. Account deletion cancelled.', 'danger')
        return redirect(url_for('profile.profile_view'))