# -*- coding: utf-8 -*-
"""
Email service for Attendly application.
Handles all email communications and notifications.
"""

from flask_mail import Mail, Message
from flask import current_app
import logging

logger = logging.getLogger(__name__)

mail = Mail()


def send_email(subject, recipients, text_body=None, html_body=None, attachments=None):
    """
    Send email with optional attachments.
    
    Args:
        subject (str): Email subject
        recipients (list/str): Email address(es) to send to
        text_body (str): Plain text email body
        html_body (str): HTML email body
        attachments (list): List of tuples (filename, content_type, data)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not recipients:
            logger.warning("❌ No recipients provided for email")
            return False
        
        # Ensure recipients is a list
        if isinstance(recipients, str):
            recipients = [recipients]
        
        # Create message
        msg = Message(
            subject=subject,
            recipients=recipients,
            body=text_body,
            html=html_body
        )
        
        # Add attachments if provided
        if attachments:
            for filename, content_type, data in attachments:
                try:
                    msg.attach(filename, content_type, data)
                except Exception as e:
                    logger.error(f"Error attaching file {filename}: {str(e)}")
        
        # Send email
        mail.send(msg)
        logger.info(f"✅ Email sent to {recipients}: {subject}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending email: {str(e)}")
        return False


def send_leave_notification(student_name, start_date, end_date, admin_email, status='pending'):
    """Send leave request notification to admin"""
    subject = f"🔔 Leave Request - {student_name}"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #dc2626;">New Leave Request</h2>
            <p><strong>Student:</strong> {student_name}</p>
            <p><strong>Start Date:</strong> {start_date}</p>
            <p><strong>End Date:</strong> {end_date}</p>
            <p><strong>Status:</strong> <span style="color: #f59e0b; font-weight: bold;">{status.upper()}</span></p>
            <p>Please review and approve/deny the request in the admin dashboard.</p>
        </body>
    </html>
    """
    
    return send_email(subject, [admin_email], html_body=html_body)


def send_leave_approval(student_email, student_name, status):
    """Send leave approval/denial notification to student"""
    if status == 'approved':
        subject = "✅ Your Leave Request Approved"
        emoji = "✅"
        message = "has been approved"
        color = "#10b981"
    else:
        subject = "❌ Your Leave Request Denied"
        emoji = "❌"
        message = "has been denied"
        color = "#ef4444"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: {color};">{emoji} Leave Request Update</h2>
            <p>Dear {student_name},</p>
            <p>Your leave request <strong>{message}</strong>.</p>
            <p>Please check your dashboard for more details.</p>
        </body>
    </html>
    """
    
    return send_email(subject, [student_email], html_body=html_body)


def send_attendance_report(recipient_email, report_type, report_data=None):
    """Send attendance report via email"""
    subject = f"📊 {report_type.upper()} Report - Attendance"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #dc2626;">📊 Attendance Report</h2>
            <p><strong>Report Type:</strong> {report_type}</p>
            <p><strong>Generated:</strong> {report_data.get('generated_date', 'N/A') if report_data else 'N/A'}</p>
            <p>Your report is attached. Please review it.</p>
        </body>
    </html>
    """
    
    return send_email(subject, [recipient_email], html_body=html_body)


def send_test_email(recipient_email):
    """Send test email to verify configuration"""
    subject = "✅ Attendly Email Test"
    
    html_body = """
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #10b981;">✅ Test Email from Attendly</h2>
            <p>If you're reading this, your email configuration is working correctly!</p>
            <p>You can now receive notifications from Attendly.</p>
            <p style="color: #999; font-size: 12px; margin-top: 20px;">
                This is an automated message. Please do not reply.
            </p>
        </body>
    </html>
    """
    
    return send_email(subject, [recipient_email], html_body=html_body)


def send_admin_notification(admin_email, title, message):
    """Send general admin notification"""
    subject = f"🔔 Attendly Notification - {title}"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #dc2626;">🔔 {title}</h2>
            <p>{message}</p>
        </body>
    </html>
    """
    
    return send_email(subject, [admin_email], html_body=html_body)


def send_welcome_email(user_email, username, password):
    """Send welcome email to new user"""
    subject = "🎉 Welcome to Attendly"
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #dc2626;">🎉 Welcome to Attendly!</h2>
            <p>Hello <strong>{username}</strong>,</p>
            <p>Your account has been created successfully.</p>
            <p><strong>Login Credentials:</strong></p>
            <ul>
                <li>Username: {username}</li>
                <li>Temporary Password: {password}</li>
            </ul>
            <p>Please change your password after your first login for security.</p>
            <p><strong>Login URL:</strong> <a href="http://localhost:5000/login">Click here to login</a></p>
        </body>
    </html>
    """
    
    return send_email(subject, [user_email], html_body=html_body)
