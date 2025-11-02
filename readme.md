# 🎓 Attendly - Smart Attendance Management System

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3.3-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Online-success.svg)](https://a-t-t-e-n-d-l-y.onrender.com)

**Attendly** is a modern, feature-rich attendance tracking system designed for educational institutions. Built with Flask and PostgreSQL, it offers real-time attendance monitoring, AI-powered insights, multiple themes, and comprehensive reporting tools.

<div align="center">

### 🌐 [**Live Demo**](https://a-t-t-e-n-d-l-y.onrender.com) | [Documentation](#) | [Report Bug](https://github.com/yourusername/attendly/issues) | [Request Feature](https://github.com/yourusername/attendly/issues/new?template=feature_request.md)

**Try the prototype now!** → [a-t-t-e-n-d-l-y.onrender.com](https://a-t-t-e-n-d-l-y.onrender.com)

</div>

---

## ✨ Key Features

### 📊 **Dashboard & Analytics**
- **Real-time Statistics**: Live attendance counts, present/absent students, and attendance rates
- **Interactive Charts**: Attendance trends, subject-wise distribution, and performance metrics
- **AI-Powered Insights**: Predictive analytics for at-risk students and anomaly detection
- **Leaderboard System**: Student performance ranking based on attendance percentage

### 👥 **Multi-Role Support**
- **Admin**: Complete system control, user management, class assignments
- **Teacher**: Mark attendance, view class statistics, approve leave requests
- **Student**: View personal attendance, request medical leaves, track performance

### 🎨 **Premium UI/UX**
- **9 Theme Options**: Light, Dark, Sepia, Oceanic Blue, Sunset Glow, Forest Green, Cyberpunk, Lavender Dream, Midnight Blue
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices
- **Dark Mode Support**: Eye-friendly themes for extended use

### 🔐 **Authentication & Security**
- **Simplified Registration**: Direct account creation without email verification (OTP verification available in code but currently disabled for deployment)
- **Password Reset**: Secure token-based password recovery via email
- **Role-Based Access Control**: Granular permissions for different user types
- **Session Management**: Secure 8-hour session lifetime with HTTP-only cookies

### 📈 **Attendance Management**
- **Multiple Marking Methods**: Manual entry, QR code scanning (code ready, currently disabled), bulk CSV upload
- **Medical Leave Tracking**: Student leave requests with approval workflow
- **Subject-wise Attendance**: Track attendance per subject and class
- **Historical Data**: Complete attendance history with filtering options

### 📧 **Automated Notifications**
- **Email Alerts**: Scheduled reports, low attendance warnings
- **APScheduler Integration**: Automated daily/weekly report generation
- **Customizable Templates**: Professional email templates with institution branding

### 📥 **Export & Reporting**
- **PDF Reports**: Generate detailed attendance reports
- **Excel Export**: Download attendance data in CSV/XLSX format
- **Scheduled Reports**: Automatic email delivery of periodic reports
- **Advanced Analytics**: Comprehensive performance metrics and trends

---

## 🚀 Quick Start

### 🌐 Try the Live Demo

**No installation required!** Experience Attendly instantly:

<div align="center">

## 🎯 **[Launch Prototype →](https://a-t-t-e-n-d-l-y.onrender.com)**

**Live URL**: `https://a-t-t-e-n-d-l-y.onrender.com`

</div>

> **💡 Demo Note**: The live prototype is hosted on Render's free tier. Initial load may take 30-60 seconds if the service is inactive. Subsequent visits will be faster.

### Test Credentials

You can create your own account or use these demo credentials to explore different roles:

| Role | Username | Password | Access Level |
|------|----------|----------|--------------|
| Admin | `demo_admin` | `admin123` | Full system access |
| Teacher | `demo_teacher` | `teacher123` | Class management |
| Student | `demo_student` | `student123` | Personal dashboard |

---

### Prerequisites

- **Python**: 3.8 or higher
- **PostgreSQL**: 12+ (or SQLite for development)
- **pip**: Python package installer
- **Virtual Environment**: Recommended for isolation

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/attendly.git
   cd attendly
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   
   Create a `.env` file in the project root:
   ```env
   # Database
   DATABASE_URL=postgresql://username:password@localhost/attendly
   # Or use SQLite for development:
   # DATABASE_URL=sqlite:///attendance.db
   
   # Security
   SECRET_KEY=your-secret-key-here
   SESSION_COOKIE_SECURE=False
   
   # Email Configuration (Gmail example)
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your_email@gmail.com
   MAIL_PASSWORD=your_app_password
   
   # Timezone
   TZ=Asia/Kolkata
   
   # Environment
   FLASK_ENV=development
   ```

5. **Initialize Database**
   ```bash
   flask init-db
   ```

6. **Create Admin User**
   ```bash
   flask create-admin admin admin@example.com
   # You'll be prompted to enter a password
   ```

7. **Run the Application**
   ```bash
   python run.py
   ```

8. **Access the Application**
   
   Open your browser and navigate to: `http://localhost:5000`

---

## 🏗️ Project Structure

```
attendly/
├── attendly/                    # Main application package
│   ├── __init__.py             # Application factory
│   ├── models.py               # Database models
│   ├── extensions.py           # Flask extensions
│   ├── utils.py                # Utility functions
│   ├── email.py                # Email functionality
│   │
│   ├── auth/                   # Authentication blueprint
│   │   ├── routes.py
│   │   └── forms.py
│   │
│   ├── admin/                  # Admin panel blueprint
│   │   ├── routes.py
│   │   └── forms.py
│   │
│   ├── dashboard/              # Dashboard blueprint
│   │   └── routes.py
│   │
│   ├── student/                # Student management blueprint
│   │   ├── routes.py
│   │   └── forms.py
│   │
│   ├── teacher/                # Teacher management blueprint
│   │   ├── routes.py
│   │   └── forms.py
│   │
│   └── profile/                # User profile blueprint
│       └── routes.py
│
├── templates/                  # HTML templates
│   ├── shared/                 # Shared templates (base, navbar)
│   ├── auth/                   # Authentication pages
│   ├── admin/                  # Admin pages
│   ├── dashboard/              # Dashboard page
│   ├── student/                # Student pages
│   ├── teacher/                # Teacher pages
│   └── errors/                 # Error pages (404, 500)
│
├── static/                     # Static files
│   ├── css/
│   ├── js/
│   ├── images/
│   └── uploads/                # User-uploaded files
│
├── migrations/                 # Database migrations
├── run.py                      # Application entry point
├── requirements.txt            # Python dependencies
├── render.yaml                 # Deployment configuration
├── .env                        # Environment variables (create this)
└── README.md                   # This file
```

---

## 📦 Database Schema

### Core Models

**User**
- Multi-role system (admin, teacher, student)
- Profile information (avatar, location, biography)
- Email verification and password reset tokens
- Unique Attendly ID for each user

**Institution**
- School/college information
- Institution code for multi-tenancy
- Links to users and classes

**ClassBatch**
- Class/section organization
- Student enrollment
- Teacher assignments with subjects

**Student**
- Extended student profile
- Academic information (semester, CGPA, graduation year)
- Social links (LinkedIn, GitHub)
- Achievements and skills

**Attendance**
- Date-based attendance records
- Status (present, absent, on leave)
- Subject and student associations
- Marking method tracking

**Subject**
- Course/subject information
- Links to attendance records

**MedicalLeave**
- Leave request management
- Date range and reason
- Approval workflow (pending, approved, denied)

**TeacherAssignment**
- Maps teachers to classes with specific subjects
- Ensures proper authorization for attendance marking

**QRToken**
- Time-limited QR codes for attendance
- Class and subject association
- Automatic expiration

---

## 🎯 Usage Guide

### For Administrators

1. **Dashboard Access**: Login with admin credentials to view system-wide statistics
2. **User Management**: Navigate to Admin Panel → Users to add/edit users
3. **Class Setup**: Create classes and assign teachers to subjects
4. **Bulk Operations**: Upload CSV files for bulk student registration
5. **Analytics**: Access advanced analytics for insights and trends
6. **Scheduled Reports**: Configure automated email reports

### For Teachers

1. **Mark Attendance**: Select class and subject, mark students present/absent
2. **QR Code Generation**: Generate time-limited QR codes for student self-marking
3. **Leave Approval**: Review and approve/deny student leave requests
4. **Class Reports**: Export attendance data for your assigned classes
5. **View Statistics**: Monitor class attendance trends and student performance

### For Students

1. **View Attendance**: Check your attendance percentage and history
2. **Request Leave**: Submit medical leave applications with reasons
3. **QR Scanning**: Scan teacher-generated QR codes to mark attendance
4. **Track Performance**: View your position in the class leaderboard
5. **Profile Management**: Update personal information and academic details

---

## 🔧 Configuration Options

### Email Setup (Gmail)

> **⚠️ Note**: Email OTP verification is currently disabled in the deployed version to avoid email delivery issues during registration. Users can register and login directly without email verification.
> 
> The OTP verification code is available in `attendly/auth/routes.py` (commented out) and can be re-enabled by uncommenting the OTP-related sections and ensuring proper email configuration.

**To enable OTP verification (optional)**:

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password: Account → Security → App Passwords
3. Use the app password in your `.env` file
4. Uncomment the OTP verification code in `attendly/auth/routes.py`
5. Update the registration flow to include email verification

**Current authentication flow** (OTP disabled):
- User registers → Account created immediately → Auto-login → Dashboard access

### Database Configuration

**PostgreSQL (Production)**:
```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

**SQLite (Development)**:
```env
DATABASE_URL=sqlite:///attendance.db
```

### Scheduler Configuration

APScheduler is configured to run in Asia/Kolkata timezone. Adjust in `app.py`:
```python
app.config['SCHEDULER_TIMEZONE'] = 'Your/Timezone'
```

---

## 🌐 Deployment

### Live Prototype

The application is currently deployed and accessible at:

**🔗 [https://a-t-t-e-n-d-l-y.onrender.com](https://a-t-t-e-n-d-l-y.onrender.com)**

**Deployment Details**:
- **Platform**: Render.com (Free Tier)
- **Database**: PostgreSQL
- **Server**: Gunicorn WSGI
- **Environment**: Production

> **⚠️ Important**: The free tier may spin down after 15 minutes of inactivity. First request after inactivity may take 30-60 seconds to wake up the service.

---

### Render.com Deployment (Current Setup)

**Current Production URL**: [a-t-t-e-n-d-l-y.onrender.com](https://a-t-t-e-n-d-l-y.onrender.com)

**To deploy your own instance**:

1. **Create Account**: Sign up at [render.com](https://render.com)
2. **New Web Service**: Connect your GitHub repository
3. **Configure**:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn run:app`
4. **Environment Variables**: Add all variables from `.env`
5. **Deploy**: Render will automatically deploy your application

**Render Configuration** (`render.yaml` already included):
```yaml
services:
  - type: web
    name: attendly
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn run:app
    envVars:
      - key: FLASK_ENV
        value: production
```

### Heroku Deployment

```bash
# Install Heroku CLI
heroku login
heroku create attendly-app

# Set environment variables
heroku config:set DATABASE_URL=your_postgres_url
heroku config:set SECRET_KEY=your_secret_key
heroku config:set MAIL_USERNAME=your_email
heroku config:set MAIL_PASSWORD=your_app_password

# Deploy
git push heroku main
heroku run flask init-db
heroku run flask create-admin admin admin@example.com
```

---

## 📊 API Endpoints

### Dashboard Data
```
GET /api/dashboard-data
```
Returns real-time attendance statistics for the dashboard.

### Attendance Management
```
POST /teacher/mark_attendance
POST /student/mark_qr_attendance
GET /student/export_csv
GET /student/export_pdf
```

### Leave Management
```
POST /student/request_leave
POST /student/handle_leave/<leave_id>/<action>
```

---

## 🛠️ CLI Commands

```bash
# Initialize database with default subjects
flask init-db

# Create admin user
flask create-admin <username> <email>

# Test email configuration
flask test-email recipient@example.com

# Populate Attendly IDs for existing users
flask populate-attendly-ids
```

---

## 🎨 Theming

Attendly includes 9 premium themes with smooth transitions:

1. **Light Mode**: Default bright theme
2. **Dark Mode**: GitHub-inspired dark theme
3. **Sepia**: Eye-comfort reading mode
4. **Oceanic Blue**: Professional blue palette
5. **Sunset Glow**: Warm orange gradient
6. **Forest Green**: Nature-inspired green
7. **Cyberpunk**: Futuristic cyan accent
8. **Lavender Dream**: Soft purple theme
9. **Midnight Blue**: Deep indigo palette

Themes persist across sessions using localStorage.

---

## 🔒 Security Features

- **Password Hashing**: Werkzeug security with bcrypt
- **CSRF Protection**: Flask-WTF CSRF tokens
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- **Session Security**: HTTP-only cookies, SameSite policy
- **Email Verification**: OTP-based account verification (code available, currently disabled for deployment)
- **Rate Limiting**: Protection against brute force attacks
- **Secure File Uploads**: Whitelist-based file type validation

> **Note**: OTP email verification is temporarily disabled to ensure smooth registration during deployment. The feature can be re-enabled by configuring SMTP settings and uncommenting the relevant code in `attendly/auth/routes.py`.

---

## 🧪 Testing

```bash
# Run tests (if test suite is available)
python -m pytest tests/

# Check code coverage
pytest --cov=attendly tests/
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Write descriptive commit messages
- Add docstrings to all functions
- Update documentation for new features
- Test thoroughly before submitting PR

---

## 📝 Important Notes

### Authentication System

The current deployment uses **simplified authentication without OTP email verification**. This decision was made to ensure smooth user registration without dependency on email service configuration.

**Current Flow**:
```
Register → Account Created → Auto Login → Dashboard Access
```

**Original OTP Flow** (available in source code, currently commented):
```
Register → Email Sent with OTP → Verify OTP → Account Activated → Login → Dashboard
```

**Files containing OTP code**:
- `attendly/auth/routes.py` - Main authentication logic (OTP sections commented)
- `attendly/utils.py` - Email sending utilities (`send_verification_email` function)
- `templates/auth/verify_otp.html` - OTP verification page

**To enable OTP verification**:
1. Configure email settings in `.env`
2. Uncomment OTP-related code in `auth/routes.py`
3. Test email delivery thoroughly
4. Update deployment configuration

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🐛 Troubleshooting

### Database Connection Issues
```bash
# Check database URL
echo $DATABASE_URL

# Reset database
flask init-db
```

### Email Not Sending
- **Current Status**: OTP email verification is disabled for the deployed version
- For password reset emails, verify SMTP credentials in `.env`
- Check if 2FA is enabled and app password is generated
- Test email: `flask test-email your@email.com`

**To Re-enable OTP Verification**:
1. Configure proper SMTP settings in `.env`
2. Uncomment OTP-related code in `attendly/auth/routes.py`
3. Update registration templates to include verification step
4. Test thoroughly before deploying

### Static Files Not Loading
- Clear browser cache
- Restart Flask development server
- Check `static/` folder permissions

### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade

# Clear Python cache
find . -type d -name __pycache__ -exec rm -r {} +
```

---

## 📧 Support

For issues, questions, or suggestions:

- **🌐 Live Demo**: [a-t-t-e-n-d-l-y.onrender.com](https://a-t-t-e-n-d-l-y.onrender.com)
- **📧 Email**: support@attendly.com
- **🐛 GitHub Issues**: [Create an issue](https://github.com/yourusername/attendly/issues)
- **📖 Documentation**: [Wiki](https://github.com/yourusername/attendly/wiki)

---

---

## 🔮 Future Scope & Upcoming Updates

We're constantly working to enhance Attendly with cutting-edge features. Here's what's coming next:

### 🚀 In Development

<table>
<tr>
<td width="50%">

#### 📱 QR Code-Based Attendance
**Status**: 🟡 Code Ready, Feature Disabled

The QR code attendance system is fully implemented in the source code but currently disabled for the production deployment.

**Features Available in Code**:
- ✅ Dynamic QR code generation with expiration
- ✅ Student QR scanning interface
- ✅ Time-limited tokens for security
- ✅ Class and subject-specific QR codes
- ✅ Real-time attendance marking

**Files Containing QR Code**:
- `attendly/models.py` - QRToken model
- `attendly/teacher/routes.py` - QR generation logic
- `attendly/student/routes.py` - QR scanning endpoint
- `templates/teacher/` - QR display templates

**Coming Soon**: Re-enabled with enhanced security features and better user interface.

</td>
<td width="50%">

#### 🤖 AI Mentor System
**Status**: 🔴 In Planning

An intelligent AI-powered mentorship system to guide students and provide personalized recommendations.

**Planned Features**:
- 📊 Personalized attendance insights
- 🎯 Goal setting and tracking
- 💡 Study recommendations based on attendance patterns
- 🚨 Early warning system for at-risk students
- 📈 Performance prediction algorithms
- 💬 Interactive chatbot for student queries
- 📧 Automated motivational messages
- 🏆 Achievement recognition system

**Technology Stack**:
- OpenAI GPT-4 / Claude API
- Machine Learning models for predictions
- Natural Language Processing
- Real-time data analysis

</td>
</tr>
</table>

### 📋 Roadmap

#### Q1 2025
- [ ] 🔓 Re-enable QR code attendance with improved UI
- [ ] 📧 Full OTP email verification activation
- [ ] 🌐 Multi-language support (Hindi, Spanish, French)
- [ ] 📱 Progressive Web App (PWA) support

#### Q2 2025
- [ ] 🤖 AI Mentor beta release
- [ ] 📊 Advanced analytics dashboard
- [ ] 👨‍👩‍👧 Parent portal for attendance tracking
- [ ] 🔔 Push notifications system

#### Q3 2025
- [ ] 📱 Native mobile apps (Android & iOS)
- [ ] 🎭 Facial recognition attendance
- [ ] 🔗 LMS integration (Moodle, Canvas, Blackboard)
- [ ] 🌍 Offline mode support

#### Q4 2025
- [ ] 🧬 Biometric attendance integration
- [ ] 📡 IoT device support (RFID, fingerprint scanners)
- [ ] 🎨 Custom theme builder
- [ ] 🔌 REST API with full documentation (Swagger/OpenAPI)

### 💡 Feature Requests

Have ideas for new features? We'd love to hear from you!

- **GitHub Issues**: [Submit a feature request](https://github.com/yourusername/attendly/issues/new?template=feature_request.md)
- **Discussions**: [Join the conversation](https://github.com/yourusername/attendly/discussions)
- **Email**: features@attendly.com

---

## 👥 Team & Contributors

This project was developed as a collaborative effort with strategic planning and creative input from the entire team.

### 🏆 Core Team

<table>
<tr>
<td align="center" width="25%">
<img src="https://via.placeholder.com/150" width="100px;" alt="Shakti Singh"/><br />
<b>Shakti Singh</b><br />
<sub>Team Leader & Lead Developer</sub><br />
<br />
<i>Full-stack development, architecture design, deployment, and project management</i>
</td>
<td align="center" width="25%">
<img src="https://via.placeholder.com/150" width="100px;" alt="Awani"/><br />
<b>Awani</b><br />
<sub>Ideation & Feature Planning</sub><br />
<br />
<i>Feature conceptualization, user flow design, and requirement analysis</i>
</td>
<td align="center" width="25%">
<img src="https://via.placeholder.com/150" width="100px;" alt="Ankit Vishwakarma"/><br />
<b>Ankit Vishwakarma</b><br />
<sub>System Design & Strategy</sub><br />
<br />
<i>System architecture ideas, database schema planning, and technical consulting</i>
</td>
<td align="center" width="25%">
<img src="https://via.placeholder.com/150" width="100px;" alt="Sagar Kumar"/><br />
<b>Sagar Kumar</b><br />
<sub>UX/UI Consultation</sub><br />
<br />
<i>User experience insights, interface suggestions, and feature prioritization</i>
</td>
</tr>
</table>

### 🎯 Role Distribution

| Team Member | Primary Role |
|-------------|--------------|
| **Shakti Singh** | 👨‍💻 Lead Developer & Project Manager |
| **Awani** | 💡 Feature Strategist |
| **Ankit Vishwakarma** | 🏗️ System Architect (Advisory) |
| **Sagar Kumar** | 🎨 UX Consultant |

### 💪 Development Model

**Solo Development with Collaborative Planning**

While the entire codebase was developed by **Shakti Singh**, the project benefited from:
- 🧠 Brainstorming sessions with the team
- 💬 Regular feedback and suggestions
- 🎯 Strategic planning and feature prioritization
- 🔍 Review and testing assistance
- 💡 Creative problem-solving discussions

This model allowed for focused development while leveraging diverse perspectives and ideas from the team.

---

## 🤖 AI-Powered Development

This project was built with the assistance of cutting-edge AI tools that accelerated development, improved code quality, and enhanced problem-solving capabilities.

### AI Tools Used

<div align="center">

| Tool | Purpose | Link |
|------|---------|------|
| 🤖 **Claude AI** | Architecture design, code generation, debugging assistance | [claude.ai](https://claude.ai) |
| 💬 **ChatGPT** | Problem-solving, documentation, algorithm optimization | [chat.openai.com](https://chat.openai.com) |
| 🔮 **Google Gemini** | Code review, best practices, testing strategies | [gemini.google.com](https://gemini.google.com) |
| 🔍 **Perplexity AI** | Research, technical documentation, troubleshooting | [perplexity.ai](https://www.perplexity.ai) |
| 🐙 **GitHub Copilot** | Real-time code suggestions, boilerplate generation | [github.com/features/copilot](https://github.com/features/copilot) |

</div>

### How AI Accelerated Development

- **🚀 Faster Prototyping**: Rapid generation of boilerplate code and project structure
- **🐛 Smart Debugging**: AI-assisted error detection and solution recommendations
- **📚 Documentation**: Automated generation of comprehensive documentation and comments
- **💡 Best Practices**: Real-time suggestions for security, performance, and code quality
- **🎨 UI/UX Design**: Theme creation, responsive layouts, and accessibility improvements
- **🧪 Testing**: Test case generation and edge case identification
- **🔄 Refactoring**: Code optimization and pattern recognition

> **Note**: While AI tools significantly accelerated development, all code was carefully reviewed, tested, and customized to meet project requirements. AI served as an intelligent assistant, not a replacement for human expertise and decision-making.

---

## 🙏 Acknowledgments

- **Flask**: Micro web framework
- **Bootstrap**: Frontend framework
- **Chart.js**: Data visualization
- **Font Awesome**: Icon library
- **APScheduler**: Task scheduling
- **PostgreSQL**: Database system

---

## 📈 Roadmap

- [ ] Mobile app (React Native/Flutter)
- [ ] Biometric attendance integration
- [ ] Facial recognition attendance
- [ ] Parent portal for attendance tracking
- [ ] Integration with learning management systems (LMS)
- [ ] Multi-language support
- [ ] Advanced analytics with machine learning
- [ ] REST API documentation (Swagger/OpenAPI)
- [ ] QR code attendance (re-enable from source code)
- [ ] AI Mentor system for personalized student guidance

> 📝 **Note**: For detailed future plans and status updates, see the [Future Scope & Upcoming Updates](#-future-scope--upcoming-updates) section above.

---

## 💡 Tips for Best Results

1. **Regular Backups**: Schedule daily database backups
2. **Email Templates**: Customize email templates for your institution
3. **Theme Customization**: Modify CSS variables to match your brand
4. **Performance**: Use PostgreSQL in production for better performance
5. **Security**: Always use HTTPS in production
6. **Monitoring**: Set up application monitoring (e.g., Sentry)

---

<div align="center">

**Made with ❤️ by Shakti Singh & Team**

### 👥 **Team**: Shakti Singh (Lead) • Awani • Ankit Vishwakarma • Sagar Kumar

### 🌐 **[Try Live Demo](https://a-t-t-e-n-d-l-y.onrender.com)** | ⭐ **[Star on GitHub](https://github.com/yourusername/attendly)**

*Transforming attendance management with intelligent automation*

</div>