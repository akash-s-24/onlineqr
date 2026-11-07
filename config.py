import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Environment mode
    APP_ENV = os.environ.get('APP_ENV', 'development').strip().lower()

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
    _env_secure = os.environ.get('SESSION_COOKIE_SECURE')
    SESSION_COOKIE_SECURE = (
        _env_secure.strip().lower() in ('1', 'true', 'yes')
        if _env_secure is not None
        else (APP_ENV == 'production' or bool(os.environ.get('RENDER')))
    )
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Static assets are served with a cache-busting query string (?v=...), so
    # they can be cached aggressively by the browser. In production, this is
    # fine; see app.py's after_request for the per-route Cache-Control logic.
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 year in seconds

    # Force compression for text responses even when not behind a proxy.
    # The gzip middleware in app.py reads this flag.
    COMPRESS_RESPONSES = True

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
    EVENT_TITLE = os.environ.get('EVENT_TITLE', 'Daksha Infinix').strip() or 'Daksha Infinix'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip() or 'admin123'
    # Temporary lead contacts for the demo site. Replace these values before launch.
    CONTACT_PHONE_PRIMARY = os.environ.get('CONTACT_PHONE_PRIMARY', '').strip() or '+91 90000 00001'
    CONTACT_PHONE_SECONDARY = os.environ.get('CONTACT_PHONE_SECONDARY', '').strip() or '+91 90000 00002'
    SIGNATORY_NAME = os.environ.get('SIGNATORY_NAME', 'Naveen Reddy')
    SIGNATORY_TITLE = os.environ.get('SIGNATORY_TITLE', 'Head of Department (HOD)')

    # Base URL for Verification Links
    BASE_URL = os.environ.get('BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or ('https://localhost' if APP_ENV == 'production' else 'http://127.0.0.1:5001')

    # Certificate Storage Path
    CERTIFICATE_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'certificates')

    # SMTP Email Configuration
    SMTP_MODE = os.environ.get('SMTP_MODE', 'demo').strip().lower()  # 'demo' or 'live'
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_SENDER_EMAIL = os.environ.get('SMTP_SENDER_EMAIL', os.environ.get('SMTP_USERNAME', 'info@shreedakshaacademyedu.in'))
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')
    SMTP_USE_SSL = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
    RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', '').strip()


if Config.APP_ENV == 'production':
    production_errors = []
    if not Config._configured_secret or len(Config._configured_secret) < 32 or Config._configured_secret.lower().startswith(('change-me', 'eventmate-')):
        production_errors.append('SECRET_KEY must be a stable random value of at least 32 characters')
    if not Config.DATABASE_URL:
        production_errors.append('DATABASE_URL must be configured')
    if not Config.BASE_URL or not Config.BASE_URL.startswith('https://'):
        if Config.BASE_URL and Config.BASE_URL.startswith('http://'):
            Config.BASE_URL = 'https://' + Config.BASE_URL[7:]
        else:
            Config.BASE_URL = os.environ.get('RENDER_EXTERNAL_URL') or 'https://localhost'
    if not Config.SESSION_COOKIE_SECURE:
        production_errors.append('SESSION_COOKIE_SECURE must be enabled')
    smtp_ready = (Config.SMTP_MODE == 'demo') or (Config.SMTP_MODE == 'live' and Config.SMTP_USERNAME and Config.SMTP_PASSWORD)
    resend_ready = bool(Config.RESEND_API_KEY and Config.RESEND_FROM_EMAIL)
    if not smtp_ready and not resend_ready:
        production_errors.append('live SMTP or Resend email credentials must be configured (or SMTP_MODE set to demo)')
    if Config.ADMIN_PASSWORD and len(Config.ADMIN_PASSWORD) < 8:
        production_errors.append('ADMIN_PASSWORD must be at least 8 characters')
    if production_errors:
        raise RuntimeError('Production configuration is incomplete: ' + '; '.join(production_errors))
