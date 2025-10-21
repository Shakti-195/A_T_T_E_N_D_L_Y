# -*- coding: utf-8 -*-
"""
This file defines all the database models (tables) for the application
using Flask-SQLAlchemy.
"""

# --- Third-Party Library Imports ---
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

# --- Local Application Imports ---
from .extensions import db
# NOTE: We only import get_current_ist from utils. Utils no longer imports
# from models at the top level, so this is now safe.
from .utils import get_current_ist


# --- Association Table ---
# This table links Users (teachers) to ClassBatches in a many-to-many relationship.
teacher_classes = db.Table('teacher_classes',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_batch_id', db.Integer, db.ForeignKey('class_batch.id'), primary_key=True)
)


# --- Main Models ---

class User(db.Model):
    """User model for authentication and profile management"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # Roles: student, teacher, admin
    created_at = db.Column(db.DateTime, default=get_current_ist)
    
    # Foreign Keys
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=True)

    # For email verification and password reset
    email_verified = db.Column(db.Boolean, default=False)
    otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(100), nullable=True, unique=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    # Additional profile fields
    attendly_id = db.Column(db.String(50), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    avatar = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    biography = db.Column(db.Text, nullable=True)
    branch = db.Column(db.String(100), nullable=True)  # For students
    designation = db.Column(db.String(100), nullable=True)  # For teachers
    department = db.Column(db.String(100), nullable=True)  # For teachers/admin
    experience = db.Column(db.String(50), nullable=True)  # For teachers

    # A user's username must be unique within their institution
    __table_args__ = (db.UniqueConstraint('username', 'institution_id'),)

    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """Check if provided password matches the hash"""
        return check_password_hash(self.password_hash, password)
    
    # Properties for template compatibility (MongoDB-style access)
    @property
    def personalInfo(self):
        """Provide compatibility with MongoDB-style templates"""
        # Use student profile name if available, otherwise username
        name = self.username
        if self.role == 'student' and self.student_profile:
            name = self.student_profile.name
        
        return {
            'name': name,
            'email': self.email or '',
            'phone': self.phone or '',
            'avatar': self.avatar,
            'location': self.location or ''
        }
    
    @property
    def studentInfo(self):
        """Provide student information"""
        if self.role == 'student' and self.student_profile:
            return {
                'batch': self.student_profile.batch or '',
                'semester': self.student_profile.semester,
                'graduationYear': self.student_profile.graduation_year
            }
        return {}
    
    @property
    def academics(self):
        """Provide academic information"""
        if self.role == 'student' and self.student_profile:
            subjects = []
            # Get unique subjects from attendance records
            if self.student_profile.attendances:
                subject_ids = set()
                for att in self.student_profile.attendances:
                    if att.subject_id not in subject_ids:
                        subject_ids.add(att.subject_id)
                        if att.subject:
                            subjects.append({
                                'id': att.subject.id,
                                'name': att.subject.name
                            })
            
            return {
                'semester': self.student_profile.semester,
                'cgpa': self.student_profile.cgpa,
                'subjects': subjects
            }
        return {}
    
    @property
    def attendance(self):
        """Provide attendance information"""
        if self.role == 'student' and self.student_profile:
            total_days = Attendance.query.filter_by(student_id=self.student_profile.id).count()
            present_days = Attendance.query.filter_by(student_id=self.student_profile.id, status='present').count()
            percentage = round((present_days / total_days * 100), 1) if total_days > 0 else 0
            return {
                'percentage': percentage,
                'total_present': present_days,
                'total_absent': total_days - present_days
            }
        return None
    
    @property
    def achievements(self):
        """Provide achievements list"""
        if self.role == 'student' and self.student_profile and self.student_profile.achievements:
            # Split achievements if stored as comma-separated
            achievements_text = self.student_profile.achievements.strip()
            if achievements_text:
                return [a.strip() for a in achievements_text.split(',') if a.strip()]
        return []
    
    @property
    def attendlyId(self):
        """Provide attendly_id compatibility"""
        if self.attendly_id:
            return self.attendly_id
        # Generate from ID if not set
        return f"ATD{self.id:06d}"
    
    @property
    def enrollmentNo(self):
        """Provide enrollment number"""
        if self.role == 'student' and self.student_profile:
            return self.student_profile.student_id
        return None
    
    @property
    def bio(self):
        """Provide bio"""
        if self.biography:
            return self.biography
        if self.role == 'student' and self.student_profile and self.student_profile.bio:
            return self.student_profile.bio
        return ''

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Institution(db.Model):
    """Institution model for schools/colleges"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # e.g., 'School', 'College'
    institution_code = db.Column(db.String(10), unique=True, nullable=False)

    # Relationships
    users = db.relationship('User', backref='institution', lazy='dynamic')
    class_batches = db.relationship('ClassBatch', backref='institution', lazy='dynamic')

    def __repr__(self):
        return f'<Institution {self.name}>'


class ClassBatch(db.Model):
    """ClassBatch model for organizing students into classes"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Foreign Key
    institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=False)

    # Relationships
    students = db.relationship('Student', backref='class_batch', lazy='dynamic')
    teachers = db.relationship('User', secondary=teacher_classes, 
                              backref=db.backref('taught_classes', lazy='subquery'))

    def __repr__(self):
        return f'<ClassBatch {self.name}>'


class Subject(db.Model):
    """Subject model for courses/subjects"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Relationship
    attendances = db.relationship('Attendance', backref='subject', lazy='dynamic')

    def __repr__(self):
        return f'<Subject {self.name}>'


class Student(db.Model):
    """Student model for student profiles"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), nullable=False)  # The ID given by the institution
    email = db.Column(db.String(120), nullable=True)
    photo = db.Column(db.String(100), nullable=False, default='default.png')
    created_at = db.Column(db.DateTime, default=get_current_ist)

    # Foreign Key
    class_batch_id = db.Column(db.Integer, db.ForeignKey('class_batch.id'), nullable=True)

    # Relationships
    user = db.relationship('User', backref='student_profile', uselist=False, 
                          foreign_keys=[User.student_id])
    attendances = db.relationship('Attendance', backref='student', lazy='dynamic', 
                                 cascade="all, delete-orphan")
    medical_leaves = db.relationship('MedicalLeave', backref='student', lazy='dynamic', 
                                    cascade="all, delete-orphan")

    # Additional profile information
    bio = db.Column(db.Text, nullable=True)
    linkedin_url = db.Column(db.String(200), nullable=True)
    github_url = db.Column(db.String(200), nullable=True)
    achievements = db.Column(db.Text, nullable=True)
    skills = db.Column(db.String(300), nullable=True)
    
    # Academic fields for templates
    batch = db.Column(db.String(20), nullable=True)  # e.g., "2020-2024"
    semester = db.Column(db.Integer, nullable=True)  # Current semester
    cgpa = db.Column(db.Float, nullable=True)  # Cumulative GPA
    graduation_year = db.Column(db.Integer, nullable=True)  # Year of graduation

    def __repr__(self):
        return f'<Student {self.name} ({self.student_id})>'


class Attendance(db.Model):
    """Attendance model for tracking student attendance"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='present')  # 'present', 'absent'
    marked_by = db.Column(db.String(20), default='manual')  # 'manual', 'qr'
    created_at = db.Column(db.DateTime, default=get_current_ist)
    
    # Foreign Keys
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

    def __repr__(self):
        return f'<Attendance {self.student_id} - {self.date} - {self.status}>'


class QRToken(db.Model):
    """QRToken model for QR-based attendance"""
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False, 
                     default=lambda: str(uuid.uuid4()))
    class_batch_id = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, nullable=False)
    expiry_time = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<QRToken {self.token[:8]}... expires at {self.expiry_time}>'


class MedicalLeave(db.Model):
    """MedicalLeave model for leave requests"""
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending', 'approved', 'rejected'
    created_at = db.Column(db.DateTime, default=get_current_ist)
    expiry_time = db.Column(db.DateTime, nullable=True)  # For pending requests that expire
    
    # Foreign Key
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    def __repr__(self):
        return f'<MedicalLeave {self.student_id} - {self.start_date} to {self.end_date} - {self.status}>'