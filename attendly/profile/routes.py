# -*- coding: utf-8 -*-
"""
Handles user profile management, role switching, and account settings
using Flask templates (Jinja2).
"""
# --- Standard Library Imports ---
import os
import datetime
import secrets
from datetime import datetime as dt, timedelta


# --- Third-Party Library Imports ---
from flask import (Blueprint, render_template, request, redirect, url_for, flash, g, session, current_app)
from sqlalchemy.orm import joinedload
from sqlalchemy import func 
from werkzeug.utils import secure_filename


# --- Local Application Imports ---
from ..extensions import db
from ..models import User, Student, Attendance, ClassBatch, MedicalLeave
from ..utils import login_required, allowed_file, send_verification_email


# --- Blueprint Configuration ---
profile_bp = Blueprint('profile', __name__)


# --- Mock Data for Template Fix ---
GRADE_STYLES = {
    'default': {'color': 'text-gray-500', 'icon': '⭐'},
    'A+': {'color': 'text-green-500', 'icon': '🏆'},
    'A': {'color': 'text-green-400', 'icon': '⭐'},
    'B+': {'color': 'text-blue-500', 'icon': '✨'},
    'B': {'color': 'text-blue-400', 'icon': '💎'},
    'C+': {'color': 'text-yellow-500', 'icon': '🔸'},
    'C': {'color': 'text-yellow-400', 'icon': '📚'},
    'D': {'color': 'text-orange-500', 'icon': '📖'},
    'F': {'color': 'text-red-500', 'icon': '💪'},
}


# --- Profile View Route (FIXED) ---
@profile_bp.route('/profile', methods=['GET', 'POST'])
@profile_bp.route('/profile/<attendly_id>', methods=['GET'])
@login_required
def profile_view(attendly_id=None):
    """
    Display user profile page using profile.html template.
    Handles password change POST request.
    Now supports viewing ANY user's profile by their Attendly ID.
    """
    # Define current user's ID safely for comparison
    current_user_attendly_id = g.user.attendly_id.upper() if g.user and g.user.attendly_id else None


    if request.method == 'POST':
        # Only allow password change for own profile
        if attendly_id and current_user_attendly_id and attendly_id.upper() != current_user_attendly_id:
            flash('You can only change your own password.', 'danger')
            return redirect(url_for('profile.profile_view', attendly_id=attendly_id))
            
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


    user_to_view = None
    is_own_profile = False
    
    # Case 1: No attendly_id provided OR viewing own profile
    if attendly_id is None or (current_user_attendly_id and attendly_id.upper() == current_user_attendly_id):
        user_to_view = User.query.options(joinedload(User.student_profile)).get(g.user.id)
        is_own_profile = True
        attendly_id = user_to_view.attendly_id if user_to_view else None
    else:
        # Case 2: Viewing someone else's profile
        user_to_view = User.query.options(joinedload(User.student_profile)).filter(
            func.upper(User.attendly_id) == attendly_id.upper()
        ).first()
        
        if not user_to_view:
            flash(f'User not found with Attendly ID: {attendly_id.upper()}', 'danger')
            return redirect(url_for('profile.search_profile'))
        is_own_profile = False


    if not user_to_view:
        flash('Could not load user profile.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    # ====== FIX: Calculate stats based on role but use UNIFIED template ======
    stats = None
    if user_to_view.role == 'admin':
        stats = get_admin_stats(user_to_view)
    elif user_to_view.role == 'teacher':
        stats = get_teacher_stats(user_to_view)  # <<<< FIXED - Use dedicated teacher stats
    else:  # student
        stats = calculate_profile_stats(user_to_view)


    # ====== CRITICAL FIX: Use profile/profile.html for ALL roles ======
    return render_template(
        'profile/profile.html',  # <<<< UNIFIED TEMPLATE FOR ALL ROLES
        user=user_to_view, 
        is_own_profile=is_own_profile,
        stats=stats,
        grade_styles=GRADE_STYLES
    )


# --- Edit Profile Route (No change) ---
@profile_bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """
    Handle profile editing form (GET shows form, POST processes it).
    Uses edit_profile.html template.
    Only allows editing own profile.
    """
    user = User.query.options(joinedload(User.student_profile)).get(g.user.id)


    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard.dashboard'))


    student_profile = user.student_profile if user.role == 'student' else None


    if user.role == 'student' and not student_profile:
        if not user.institution_id:
            flash('Please join an institution before editing your student profile.', 'warning')
            return redirect(url_for('auth.join_institution'))
        else:
            flash('Student profile data missing. Please contact an administrator.', 'danger')
            return redirect(url_for('dashboard.dashboard'))


    if request.method == 'POST':
        try:
            avatar_saved = False
            avatar_error = False
            email_changed = False
            old_email = user.email


            # --- Handle Avatar Upload ---
            if 'avatar' in request.files:
                file = request.files['avatar']
                
                if file and file.filename:
                    if not allowed_file(file.filename):
                        flash(f'Invalid file type. Allowed types are: {", ".join(current_app.config["ALLOWED_EXTENSIONS"])}', 'danger')
                        avatar_error = True
                    else:
                        file.seek(0, os.SEEK_END)
                        file_size = file.tell()
                        file.seek(0)
                        
                        if file_size > 5 * 1024 * 1024:
                            flash('Avatar file size must be less than 5MB.', 'danger')
                            avatar_error = True
                        else:
                            upload_folder = current_app.config['UPLOAD_FOLDER']
                            base, ext = os.path.splitext(file.filename)
                            filename = secure_filename(f"avatar_{user.id}_{secrets.token_hex(8)}{ext}")


                            # Delete old avatar
                            if user.avatar and not user.avatar.startswith('http') and user.avatar != 'uploads/default.png':
                                old_avatar_path = os.path.join(current_app.static_folder, user.avatar)
                                if os.path.exists(old_avatar_path):
                                    try:
                                        os.remove(old_avatar_path)
                                    except Exception as e:
                                        current_app.logger.warning(f"Could not delete old avatar: {str(e)}")


                            file.save(os.path.join(upload_folder, filename))
                            user.avatar = f'uploads/{filename}'
                            avatar_saved = True
            
            if avatar_error:
                raise ValueError("Avatar upload failed, rolling back changes.")


            # --- Update Basic Fields ---
            new_email = request.form.get('email', '').strip()
            if new_email and new_email != old_email:
                # Check if email already exists
                existing_user = User.query.filter(User.email == new_email, User.id != user.id).first()
                if existing_user:
                    flash('This email is already registered.', 'danger')
                    raise ValueError("Email already exists.")
                
                # Email changed - require verification
                user.email = new_email
                user.email_verified = False
                email_changed = True


            user.phone = request.form.get('phone', '').strip()
            user.location = request.form.get('location', '').strip()
            user.biography = request.form.get('bio', '').strip()


            # --- Role-specific updates ---
            if user.role == 'student' and student_profile:
                student_profile.name = request.form.get('name', '').strip()
                user.branch = request.form.get('branch', '').strip()
                student_profile.batch = request.form.get('batch', '').strip()
                student_profile.github_url = request.form.get('github_url', '').strip()
                student_profile.linkedin_url = request.form.get('linkedin_url', '').strip()
                student_profile.achievements = request.form.get('achievements', '').strip()
                
                is_alumni = request.form.get('is_alumni')
                if is_alumni:
                    grad_year_str = request.form.get('graduation_year', '').strip()
                    if grad_year_str and grad_year_str.isdigit():
                        year = int(grad_year_str)
                        if 1980 <= year <= (datetime.datetime.now().year + 10):
                            student_profile.graduation_year = year
                        else:
                            flash(f'Invalid Graduation Year: {grad_year_str}.', 'warning')
                    student_profile.semester = None
                    student_profile.cgpa = None
                else:
                    semester_str = request.form.get('semester', '').strip()
                    if semester_str and semester_str.isdigit():
                        sem = int(semester_str)
                        if 1 <= sem <= 12:
                            student_profile.semester = sem
                        else:
                            flash(f'Invalid Semester: {semester_str}.', 'warning')
                    
                    cgpa_str = request.form.get('cgpa', '').strip()
                    if cgpa_str:
                        try:
                            cgpa_val = float(cgpa_str)
                            if 0.0 <= cgpa_val <= 10.0:
                                student_profile.cgpa = cgpa_val
                            else:
                                flash(f'CGPA must be between 0.0 and 10.0', 'warning')
                        except (ValueError, TypeError):
                            flash(f'Invalid CGPA format: {cgpa_str}.', 'warning')
                    student_profile.graduation_year = None
            
            elif user.role == 'teacher':
                user.username = request.form.get('name', '').strip()
                user.designation = request.form.get('designation', '').strip()
                user.department = request.form.get('department', '').strip()
                user.experience = request.form.get('experience', '').strip()
            
            elif user.role == 'admin':
                user.username = request.form.get('name', '').strip()
                user.department = request.form.get('department', '').strip()


            db.session.commit()
            
            # Send verification email if email changed
            if email_changed:
                try:
                    send_verification_email(user)
                    flash('Profile updated! Please verify your new email address. Check your inbox.', 'success')
                except Exception as e:
                    current_app.logger.error(f"Failed to send verification email: {str(e)}")
                    flash('Profile updated but failed to send verification email. Please contact support.', 'warning')
            elif avatar_saved:
                flash('Profile and avatar updated successfully!', 'success')
            else:
                flash('Profile updated successfully!', 'success')
            
            return redirect(url_for('profile.profile_view'))


        except Exception as e:
            db.session.rollback()
            if "Avatar upload failed" not in str(e) and "Email already exists" not in str(e):
                current_app.logger.error(f"Error updating profile: {str(e)}")
                flash(f'An error occurred while updating your profile.', 'danger')


    # --- Render edit form ---
    class DummyForm:
        def __init__(self):
            self.csrf_token = ''
    
    form = DummyForm()
    current_year = datetime.datetime.now().year


    if request.method == 'POST':
        user = User.query.options(joinedload(User.student_profile)).get(g.user.id)


    return render_template('profile/edit_profile.html',
                           user=user,
                           form=form,
                           current_year=current_year)


# --- Profile Search Route (No change) ---
@profile_bp.route('/search', methods=['GET', 'POST'])
@login_required
def search_profile():
    """
    Search for user profiles by Attendly ID.
    Redirects directly to their FULL profile page (not public view).
    Also populates quick access list with other user IDs.
    """
    # Fetch list of other active users for Quick Access section
    # Fetch max 3 other users that are not the current user, prioritizing Students/Teachers
    quick_searches = User.query.filter(User.id != g.user.id).order_by(User.role).limit(3).all()
    
    # Format for template consumption (assuming the template expects a dictionary list)
    quick_searches_data = [
        {'id': user.attendly_id, 'role': user.role, 'label': user.username or user.role.capitalize()}
        for user in quick_searches
    ]


    if request.method == 'POST':
        search_id = request.form.get('search_id', '').strip()
        
        # Remove common prefixes
        if search_id.startswith('#'):
            search_id = search_id[1:]
        
        search_id = search_id.strip()
        
        if not search_id:
            flash('Please enter an Attendly ID to search.', 'warning')
            # Pass data even on warning/failure so the Quick Access cards still render
            return render_template('profile/search_profiles.html', quick_searches=quick_searches_data)


        # FIX: Use case-insensitive search with func.upper
        user = User.query.options(
            joinedload(User.student_profile)
        ).filter(
            func.upper(User.attendly_id) == search_id.upper()
        ).first()


        if user:
            # Check if searching for own profile (using the safe check logic from profile_view)
            current_user_id = g.user.attendly_id.upper() if g.user.attendly_id else None
            
            if current_user_id and user.attendly_id.upper() == current_user_id:
                # Redirect to own profile (without attendly_id in URL)
                return redirect(url_for('profile.profile_view'))
            else:
                # FIXED: Redirect to OTHER user's FULL profile view
                return redirect(url_for('profile.profile_view', attendly_id=user.attendly_id))
        else:
            flash(f'No profile found with Attendly ID: {search_id.upper()}', 'danger')
            # Pass data even on warning/failure so the Quick Access cards still render
            return render_template('profile/search_profiles.html', quick_searches=quick_searches_data)
    
    return render_template('profile/search_profiles.html', quick_searches=quick_searches_data)


# --- Public Profile Route (KEPT FOR FUTURE USE) ---
@profile_bp.route('/u/<attendly_id>')
@login_required
def public_profile(attendly_id):
    """
    Instagram-style public profile view for searched users.
    Shows limited information - kept for future public sharing feature.
    NOTE: Currently not used - search redirects to full profile instead.
    """
    # FIX: Use case-insensitive search
    user_to_view = User.query.options(
        joinedload(User.student_profile)
    ).filter(
        func.upper(User.attendly_id) == attendly_id.upper()
    ).first()
    
    if not user_to_view:
        flash(f'No profile found with Attendly ID: {attendly_id}', 'danger')
        return redirect(url_for('profile.search_profile'))
    
    # Check if viewing own profile
    is_own_profile = (g.user.id == user_to_view.id)
    
    # If viewing own profile, redirect to full profile
    if is_own_profile:
        return redirect(url_for('profile.profile_view'))
    
    # Calculate profile stats
    stats = calculate_profile_stats(user_to_view)
    
    # Render Instagram-style public profile
    return render_template(
        'profile/public_profile.html',
        user=user_to_view,
        viewer=g.user,
        stats=stats,
        is_own_profile=False
    )


def calculate_profile_stats(user):
    """Calculate statistics for profile display"""
    stats = {
        'cgpa': 0.0,
        'attendance_rate': 0,
        'active_subjects': 0,
        'achievements': 0,
        'total_classes': 0,
        'present': 0,
        'absent': 0
    }
    
    if user.role == 'student' and user.student_profile:
        student = user.student_profile
        
        # CGPA
        stats['cgpa'] = student.cgpa or 0.0
        
        # Achievements count
        if student.achievements:
            # Handle both comma-separated and single achievements
            achievements_list = [a.strip() for a in student.achievements.split(',') if a.strip()]
            stats['achievements'] = len(achievements_list) if achievements_list else 0
        
        # Attendance calculation
        attendance_records = Attendance.query.filter_by(student_id=student.id).all()
        if attendance_records:
            stats['total_classes'] = len(attendance_records)
            stats['present'] = sum(1 for a in attendance_records if a.status == 'present')
            stats['absent'] = stats['total_classes'] - stats['present']
            
            # Calculate percentage
            if stats['total_classes'] > 0:
                stats['attendance_rate'] = round((stats['present'] / stats['total_classes']) * 100)
            else:
                stats['attendance_rate'] = 0
        else:
            stats['attendance_rate'] = 100
        
        # Active subjects (enrolled classes)
        try:
            if hasattr(student, 'enrolled_classes') and student.enrolled_classes:
                stats['active_subjects'] = len(student.enrolled_classes)
        except Exception as e:
            current_app.logger.warning(f"Could not load enrolled classes: {str(e)}")
            stats['active_subjects'] = 0
    
    return stats


# ====== NEW FUNCTION: Teacher Stats ======
def get_teacher_stats(user):
    """Calculate statistics for teacher profile display"""
    stats = {
        'cgpa': 0.0,
        'attendance_rate': 0,
        'active_subjects': 0,
        'achievements': 0,
        'total_classes': 0,
        'present': 0,
        'absent': 0,
        # Teacher-specific stats
        'total_students': 0,
    }
    
    if not user.institution_id:
        return stats
    
    try:
        # Get all class batches in the same institution
        # Since we don't have a direct teacher_id field, we'll count all batches in institution
        batches = ClassBatch.query.filter_by(institution_id=user.institution_id).all()
        
        # Count total students in institution
        stats['total_students'] = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == user.institution_id
        ).count()
        
        # Count active classes/batches as subjects
        stats['active_subjects'] = len(batches)
        
        # Calculate average attendance rate (last 30 days)
        from datetime import date, timedelta
        thirty_days_ago = date.today() - timedelta(days=30)
        
        attendance_query = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == user.institution_id,
            Attendance.date >= thirty_days_ago
        )
        
        stats['total_classes'] = attendance_query.count()
        stats['present'] = attendance_query.filter(Attendance.status == 'present').count()
        stats['absent'] = stats['total_classes'] - stats['present']
        
        if stats['total_classes'] > 0:
            stats['attendance_rate'] = round((stats['present'] / stats['total_classes']) * 100)
        else:
            stats['attendance_rate'] = 100  # Default to 100% if no data
        
    except Exception as e:
        current_app.logger.error(f"Error calculating teacher stats: {str(e)}")
    
    return stats


def get_admin_stats(user):
    """Calculate statistics for admin profile display"""
    stats = {
        'cgpa': 0.0,
        'attendance_rate': 100,
        'active_subjects': 0,
        'achievements': 0,
        'total_classes': 0,
        'present': 0,
        'absent': 0,
        # Admin-specific stats
        'total_students': 0,
        'total_teachers': 0,
        'total_batches': 0,
    }
    
    if not user.institution_id:
        return stats
    
    try:
        # Get total students in institution
        stats['total_students'] = Student.query.join(ClassBatch).filter(
            ClassBatch.institution_id == user.institution_id
        ).count()
        
        # Get total teachers in institution
        stats['total_teachers'] = User.query.filter_by(
            role='teacher',
            institution_id=user.institution_id
        ).count()
        
        # Get total classes/batches
        stats['total_batches'] = ClassBatch.query.filter_by(
            institution_id=user.institution_id
        ).count()
        
        # Calculate overall attendance rate (last 30 days)
        from datetime import date, timedelta
        thirty_days_ago = date.today() - timedelta(days=30)
        
        attendance_query = Attendance.query.join(Student).join(ClassBatch).filter(
            ClassBatch.institution_id == user.institution_id,
            Attendance.date >= thirty_days_ago
        )
        
        stats['total_classes'] = attendance_query.count()
        stats['present'] = attendance_query.filter(Attendance.status == 'present').count()
        stats['absent'] = stats['total_classes'] - stats['present']
        
        if stats['total_classes'] > 0:
            stats['attendance_rate'] = round((stats['present'] / stats['total_classes']) * 100)
        else:
            stats['attendance_rate'] = 100  # Default to 100% if no data
        
        # Get active subjects count
        from ..models import Subject
        stats['active_subjects'] = Subject.query.count()
        
    except Exception as e:
        current_app.logger.error(f"Error calculating admin stats: {str(e)}")
    
    return stats


# --- Email Verification Routes (No change) ---
@profile_bp.route('/verify-email/<token>')
def verify_email(token):
    """
    Verify user email using the token sent via email.
    """
    user = User.query.filter_by(email_verification_token=token).first()
    
    if not user:
        flash('Invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.login'))
    
    # Check if token is expired (24 hours validity)
    if user.token_expiry and user.token_expiry < dt.utcnow():
        flash('Verification link has expired. Please request a new one.', 'danger')
        return redirect(url_for('profile.resend_verification'))
    
    # Verify the email
    user.email_verified = True
    user.email_verification_token = None
    user.token_expiry = None
    db.session.commit()
    
    flash('Email verified successfully! You can now access all features.', 'success')
    return redirect(url_for('dashboard.dashboard'))


@profile_bp.route('/resend-verification', methods=['GET', 'POST'])
@login_required
def resend_verification():
    """
    Resend email verification link.
    """
    if g.user.email_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('profile.profile_view'))
    
    if request.method == 'POST':
        try:
            # Generate new verification token
            g.user.email_verification_token = secrets.token_urlsafe(32)
            g.user.token_expiry = dt.utcnow() + timedelta(hours=24)
            db.session.commit()
            
            # Send verification email
            send_verification_email(g.user)
            flash('Verification email sent! Please check your inbox.', 'success')
            return redirect(url_for('profile.profile_view'))
        except Exception as e:
            current_app.logger.error(f"Failed to resend verification email: {str(e)}")
            flash('Failed to send verification email. Please try again later.', 'danger')
    
    return render_template('profile/resend_verification.html', user=g.user)


# --- Security Settings (No change) ---
@profile_bp.route('/security-settings', methods=['GET', 'POST'])
@login_required
def security_settings():
    """
    Manage security settings including 2FA.
    """
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'enable_2fa':
            flash('Two-factor authentication setup coming soon!', 'info')
        
        elif action == 'disable_2fa':
            flash('Two-factor authentication disabled.', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not g.user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
            elif len(new_password) < 8:
                flash('Password must be at least 8 characters long.', 'danger')
            else:
                g.user.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully!', 'success')
        
        return redirect(url_for('profile.security_settings'))
    
    return render_template('profile/security_settings.html', user=g.user)


# --- Role Switching (No change) ---
@profile_bp.route('/switch_role/<new_role>')
@login_required
def switch_role(new_role):
    """
    Allow admin to switch between different role views.
    """
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


# --- Account Deletion (No change) ---
@profile_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    """
    Permanently delete user account with email confirmation.
    """
    email_confirmation = request.form.get('email_confirm', '').strip()
    
    if not email_confirmation:
        flash('Please enter your email to confirm account deletion.', 'danger')
        return redirect(url_for('profile.profile_view'))
    
    if email_confirmation.lower() != g.user.email.lower():
        flash('The email address you entered is incorrect. Account deletion cancelled.', 'danger')
        return redirect(url_for('profile.profile_view'))
    
    try:
        user_to_delete = g.user
        
        # Delete avatar file
        if user_to_delete.avatar and not user_to_delete.avatar.startswith('http') and user_to_delete.avatar != 'uploads/default.png':
            avatar_path = os.path.join(current_app.static_folder, user_to_delete.avatar)
            if os.path.exists(avatar_path):
                try:
                    os.remove(avatar_path)
                except Exception as e:
                    current_app.logger.warning(f"Could not delete avatar file: {str(e)}")
        
        # Delete user from database
        db.session.delete(user_to_delete)
        db.session.commit()
        
        # Clear session
        session.clear()
        
        flash('Your account has been permanently deleted. We hope to see you again!', 'success')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting account: {str(e)}")
        flash('An error occurred while deleting your account. Please try again.', 'danger')
        return redirect(url_for('profile.profile_view'))
