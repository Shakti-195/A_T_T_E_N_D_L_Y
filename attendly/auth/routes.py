# -*- coding: utf-8 -*-
"""
Handles authentication routes like login, registration, and password recovery.
"""
# --- Third-Party Library Imports ---
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, jsonify
from sqlalchemy import func

# --- Local Application Imports ---
from ..extensions import db
from ..models import User, Institution, Student, ClassBatch
from ..utils import (generate_unique_code, send_verification_email,
                   make_timezone_aware, get_current_ist, send_password_reset_email,
                   send_username_email, login_required)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
        
    if request.method == 'POST':
        user = User.query.filter(func.lower(User.username) == func.lower(request.form.get('username'))).first()
        if user and user.check_password(request.form.get('password')):
            if not user.email_verified:
                send_verification_email(user)
                flash('Email not verified. A new OTP has been sent.', 'warning')
                return redirect(url_for('auth.verify_email_otp', email=user.email))
            
            session.permanent = True
            session['user_id'] = user.id
            session['role'] = user.role
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        try:
            role = request.form.get('role', 'student')
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')

            if not all([username, email, password]):
                flash('Username, Email, and Password are required.', 'danger')
                return render_template('auth/register.html', **request.form)

            if User.query.filter((User.username == username) | (User.email == email)).first():
                flash('Username or email already exists.', 'danger')
                return render_template('auth/register.html', **request.form)

            target_institution = None
            if role == 'admin':
                inst_name = request.form.get('institution_name')
                inst_type = request.form.get('institution_type')
                if not all([inst_name, inst_type]):
                    flash('Institution Name and Type are required for admins.', 'danger')
                    return render_template('auth/register.html', **request.form)
                
                target_institution = Institution(name=inst_name, type=inst_type, institution_code=generate_unique_code())
                db.session.add(target_institution)
                db.session.flush()

            new_user = User(username=username, email=email, role=role)
            new_user.set_password(password)

            if role == 'admin':
                new_user.institution_id = target_institution.id
            else:
                new_user.institution_id = None
            
            db.session.add(new_user)
            db.session.commit()

            send_verification_email(new_user)
            return redirect(url_for('auth.verify_email_otp', email=new_user.email, new_user=True))

        except Exception as e:
            db.session.rollback()
            flash('An unexpected error occurred. Please try again.', 'danger')

    return render_template('auth/register.html')

@auth_bp.route('/join_institution', methods=['GET', 'POST'])
@login_required
def join_institution():
    if g.user.institution_id is not None:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        # --- Teacher Logic ---
        if g.user.role == 'teacher':
            inst_code = request.form.get('institution_code')
            if not inst_code:
                flash('Institution ID is required.', 'danger')
                return redirect(url_for('auth.join_institution'))
            
            institution = Institution.query.filter(func.upper(Institution.institution_code) == inst_code.upper()).first()
            if not institution:
                flash('Invalid Institution ID.', 'danger')
                return redirect(url_for('auth.join_institution'))
            
            g.user.institution_id = institution.id
            db.session.commit()
            flash(f'Successfully joined {institution.name}!', 'success')
            return redirect(url_for('dashboard.dashboard'))

        # --- Student Logic ---
        elif g.user.role == 'student':
            try:
                student_record_id = request.form.get('student_record_id', type=int)
                student_record = db.session.get(Student, student_record_id)

                if not student_record or student_record.user is not None:
                    flash('Invalid selection or student record already claimed.', 'danger')
                    return redirect(url_for('auth.join_institution'))

                g.user.student_profile = student_record
                g.user.institution_id = student_record.class_batch.institution_id
                db.session.commit()
                
                flash('Successfully joined institution and linked your academic record!', 'success')
                return redirect(url_for('dashboard.dashboard'))
            except Exception as e:
                db.session.rollback()
                flash('An error occurred while linking your student record. Please try again.', 'danger')
                return redirect(url_for('auth.join_institution'))
    
    return render_template('auth/join_institution.html')

@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/verification_sent')
def verification_sent():
    email = request.args.get('email')
    return redirect(url_for('auth.verify_email_otp', email=email, new_user=True))
    
@auth_bp.route('/verify_otp', methods=['GET', 'POST'])
def verify_email_otp():
    email = request.args.get('email')
    is_new_user = request.args.get('new_user') 
    
    user = User.query.filter_by(email=email).first_or_404()
    if request.method == 'POST':
        otp = request.form.get('otp')
        otp_expiry_aware = make_timezone_aware(user.otp_expiry)
        if user.otp == otp and otp_expiry_aware and otp_expiry_aware > get_current_ist():
            user.email_verified = True
            user.otp = None
            user.otp_expiry = None
            db.session.commit()
            flash('Email successfully verified! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Invalid or expired OTP. A new one has been sent.', 'danger')
            send_verification_email(user)
            return redirect(url_for('auth.verify_email_otp', email=email))
            
    return render_template('auth/verify_otp.html', email=email, is_new_user=is_new_user)

@auth_bp.route('/resend_verification_otp')
def resend_verification_otp():
    email = request.args.get('email')
    user = User.query.filter_by(email=email).first()
    if user and not user.email_verified:
        send_verification_email(user)
        flash('A new OTP has been sent.', 'success')
    return redirect(url_for('auth.verify_email_otp', email=email))

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user:
            send_password_reset_email(user)
        flash('If an account with this email exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')

@auth_bp.route('/forgot_username', methods=['GET', 'POST'])
def forgot_username():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user:
            send_username_email(user)
        flash('If an account with this email exists, your username has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_username.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(password_reset_token=token).first()
    reset_expiry_aware = make_timezone_aware(user.reset_token_expiry) if user else None
    if not user or not reset_expiry_aware or reset_expiry_aware < get_current_ist():
        flash('Password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        user.set_password(request.form.get('password'))
        user.password_reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Password reset successfully. Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', token=token)

@auth_bp.route('/api/get_batches/<institution_code>')
@login_required
def get_batches_for_institution(institution_code):
    institution = Institution.query.filter(func.upper(Institution.institution_code) == institution_code.upper()).first()
    if not institution:
        return jsonify({'error': 'Institution not found'}), 404
    
    batches = [{'id': batch.id, 'name': batch.name} for batch in institution.class_batches]
    return jsonify(batches)

@auth_bp.route('/api/get_students/<int:batch_id>')
@login_required
def get_students_in_batch(batch_id):
    students = Student.query.filter_by(class_batch_id=batch_id, user=None).all()
    student_list = [{'id': student.id, 'name': student.name, 'student_id': student.student_id} for student in students]
    return jsonify(student_list)

