import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask Secret Key
    _configured_secret = os.environ.get('SECRET_KEY', '').strip()
    SECRET_KEY = (
        _configured_secret
        if len(_configured_secret) >= 32
        and not _configured_secret.lower().startswith(('change-me', 'eventmate-'))
        else secrets.token_urlsafe(48)
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # PostgreSQL Database Configuration
    APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    # Optional fallback for distinct parameters if DATABASE_URL isn't used
    PG_HOST = os.environ.get('PG_HOST', 'localhost')
    PG_USER = os.environ.get('PG_USER', 'postgres')
    PG_PASSWORD = os.environ.get('PG_PASSWORD', '')
    PG_DB = os.environ.get('PG_DB', 'eventmate_db')
    PG_PORT = int(os.environ.get('PG_PORT', 5432))

    # Academy / College Branding
    COLLEGE_NAME = os.environ.get('COLLEGE_NAME', 'Shree Daksha Academy')
    COLLEGE_SUBTITLE = os.environ.get('COLLEGE_SUBTITLE', 'Department of Computer Applications')
    EVENT_TITLE = os.environ.get('EVENT_TITLE', 'SDA 2026 2027').strip() or 'SDA 2026 2027'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip()
    # Temporary lead contacts for the demo site. Replace these values before launch.
    CONTACT_PHONE_PRIMARY = os.environ.get('CONTACT_PHONE_PRIMARY', '').strip() or '+91 90000 00001'
    CONTACT_PHONE_SECONDARY = os.environ.get('CONTACT_PHONE_SECONDARY', '').strip() or '+91 90000 00002'
    SIGNATORY_NAME = os.environ.get('SIGNATORY_NAME', 'Naveen Reddy')
    SIGNATORY_TITLE = os.environ.get('SIGNATORY_TITLE', 'Head of Department (HOD)')

    # Base URL for Verification Links
    BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

    # Certificate Storage Path
    CERTIFICATE_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'certificates')

    # SMTP Email Configuration
    SMTP_MODE = os.environ.get('SMTP_MODE', 'demo').strip().lower()  # 'demo' or 'live'
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_SENDER_EMAIL = os.environ.get('SMTP_SENDER_EMAIL', os.environ.get('SMTP_USERNAME', 'eventmate.college@gmail.com'))
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')
    SMTP_USE_SSL = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't')
