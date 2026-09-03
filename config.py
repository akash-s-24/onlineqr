import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask Secret Key
    SECRET_KEY = os.environ.get('SECRET_KEY', 'eventmate-super-secret-key-2026')

    # PostgreSQL Database Configuration
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
