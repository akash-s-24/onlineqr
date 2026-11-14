import time
import os
import gzip
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, send_from_directory, send_file, abort, Response, make_response
)
import csv
import io
import re
import uuid
import secrets
import hmac
import base64
from urllib.parse import urlencode, urlparse
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image, UnidentifiedImageError
import qrcode
from config import Config
import database
from database import query_db, execute_db, create_registration
from certificate_generator import generate_certificate, generate_team_certificates_zip
from mailer import send_certificate_email, get_smtp_info, send_receipt_email, send_whatsapp_receipt

app = Flask(__name__)
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Configure upload folders
UPLOAD_FOLDER_BANNERS = os.path.join(app.root_path, 'static', 'images')
UPLOAD_FOLDER_PAYMENTS = os.path.join(app.root_path, 'payment_proofs')
os.makedirs(UPLOAD_FOLDER_BANNERS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_PAYMENTS, exist_ok=True)
app.config['UPLOAD_FOLDER_BANNERS'] = UPLOAD_FOLDER_BANNERS
app.config['UPLOAD_FOLDER_PAYMENTS'] = UPLOAD_FOLDER_PAYMENTS
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

# Lightweight in-process login throttling keeps repeated credential attacks from
# overwhelming the login endpoint without changing normal authentication flows.
LOGIN_THROTTLE = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_IP_MAX_ATTEMPTS = 25
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_TRACKED_KEYS = 2000


def _prune_login_throttle(now):
    if len(LOGIN_THROTTLE) <= LOGIN_MAX_TRACKED_KEYS:
        return
    expired_keys = [
        k for k, stamps in LOGIN_THROTTLE.items()
        if not stamps or (now - stamps[-1]) >= LOGIN_WINDOW_SECONDS
    ]
    for k in expired_keys:
        LOGIN_THROTTLE.pop(k, None)
    if len(LOGIN_THROTTLE) > LOGIN_MAX_TRACKED_KEYS:
        oldest_key = next(iter(LOGIN_THROTTLE))
        LOGIN_THROTTLE.pop(oldest_key, None)


def login_is_throttled(client_key, identifier=''):
    now = time.time()
    _prune_login_throttle(now)
    user_key = f"{client_key}:{(identifier or '').strip().lower()}"
    user_attempts = [stamp for stamp in LOGIN_THROTTLE.get(user_key, [])
                     if now - stamp < LOGIN_WINDOW_SECONDS]
    if user_attempts:
        LOGIN_THROTTLE[user_key] = user_attempts
    else:
        LOGIN_THROTTLE.pop(user_key, None)

    ip_key = f"ip:{client_key}"
    ip_attempts = [stamp for stamp in LOGIN_THROTTLE.get(ip_key, [])
                   if now - stamp < LOGIN_WINDOW_SECONDS]
    if ip_attempts:
        LOGIN_THROTTLE[ip_key] = ip_attempts
    else:
        LOGIN_THROTTLE.pop(ip_key, None)

    return len(user_attempts) >= LOGIN_MAX_ATTEMPTS or len(ip_attempts) >= LOGIN_IP_MAX_ATTEMPTS


def record_login_failure(client_key, identifier=''):
    now = time.time()
    _prune_login_throttle(now)
    for key in (f"{client_key}:{(identifier or '').strip().lower()}", f"ip:{client_key}"):
        attempts = [stamp for stamp in LOGIN_THROTTLE.get(key, [])
                    if now - stamp < LOGIN_WINDOW_SECONDS]
        attempts.append(now)
        LOGIN_THROTTLE[key] = attempts


def clear_login_failures(client_key, identifier=''):
    LOGIN_THROTTLE.pop(f"{client_key}:{(identifier or '').strip().lower()}", None)


def sanitize_csv_cell(value):
    """Neutralize spreadsheet formula injection payloads (=, +, -, @, tab, CR) in exported CSV cells (SEC-07)."""
    if value is None:
        return ''
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r')):
        return f"'{text}"
    return text

def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def save_image_upload(upload, folder):
    """Validate and save an uploaded image using a collision-resistant filename."""
    if not upload or not upload.filename:
        return None

    original_name = secure_filename(upload.filename)
    extension = os.path.splitext(original_name)[1].lower().lstrip('.')
    if not original_name or extension not in app.config['ALLOWED_IMAGE_EXTENSIONS']:
        raise ValueError('Please upload a JPG, JPEG, PNG, WEBP, or GIF image.')

    os.makedirs(folder, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{os.path.splitext(original_name)[1].lower()}"
    destination = os.path.join(folder, filename)
    upload.save(destination)
    try:
        with Image.open(destination) as image:
            if image.width > 6000 or image.height > 6000:
                raise ValueError('Please upload an image no larger than 6000 × 6000 pixels.')
            image.verify()
        # Normalize high-res camera captures to prevent storage and memory bottlenecks
        with Image.open(destination) as image:
            if image.width > 1600 or image.height > 1600:
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                if image.mode in ('RGBA', 'P'):
                    image = image.convert('RGB')
                image.save(destination, 'JPEG', quality=85, optimize=True)
    except ValueError:
        if os.path.exists(destination):
            os.remove(destination)
        raise
    except (UnidentifiedImageError, OSError):
        if os.path.exists(destination):
            os.remove(destination)
        raise ValueError('The uploaded file is not a valid image.')
    return filename


# Ensure required directories exist on app startup
os.makedirs(Config.CERTIFICATE_FOLDER, exist_ok=True)
database.init_db()

# ---------------------------------------------------------
# Context Processors & Decorators
# ---------------------------------------------------------
@app.context_processor
def inject_config():
    def csrf_token():
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_urlsafe(32)
        return session['_csrf_token']

    return {'config': Config, 'csrf_token': csrf_token}


@app.before_request
def protect_state_changing_requests():
    """Validate same-origin requests and CSRF tokens on browser forms."""
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None

    expected_hostname = (request.host.split(':')[0] if request.host else '').lower()
    base_hostname = (urlparse(Config.BASE_URL).hostname or '').lower() if Config.BASE_URL else ''
    origin = request.headers.get('Origin', '').rstrip('/')
    referer = request.headers.get('Referer', '')

    def _is_safe_host(candidate_host):
        if not candidate_host:
            return True
        c_host = candidate_host.lower()
        if c_host == expected_hostname or (base_hostname and c_host == base_hostname):
            return True
        if Config.APP_ENV != 'production' and c_host in ('localhost', '127.0.0.1', '0.0.0.0') and expected_hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
            return True
        return False

    if origin:
        origin_hostname = urlparse(origin).hostname or ''
        if not _is_safe_host(origin_hostname):
            abort(400, description='Invalid request origin.')
    elif referer:
        referer_hostname = urlparse(referer).hostname or ''
        if not _is_safe_host(referer_hostname):
            abort(400, description='Invalid request origin.')

    submitted_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    stored_token = session.get('_csrf_token')
    if submitted_token and (not stored_token or not hmac.compare_digest(submitted_token, stored_token)):
        abort(400, description='Invalid security token.')
    if not submitted_token and not app.config.get('TESTING'):
        abort(400, description='Missing security token.')
    return None


def _should_compress(response, request):
    """Return True when a response should be gzip-compressed.

    We compress only text payloads that are large enough to make compression
    worthwhile. Already-encoded responses (e.g. images, gzip middleware output)
    are skipped, and we never compress if the client did not ask for gzip.
    """
    if not Config.COMPRESS_RESPONSES:
        return False
    if response.status_code < 200 or response.status_code >= 300:
        return False
    if response.direct_passthrough:
        return False
    if response.mimetype and not response.mimetype.startswith(
        ('text/', 'application/json', 'application/javascript', 'image/svg+xml')
    ):
        return False
    if response.headers.get('Content-Encoding'):
        return False
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept_encoding.lower():
        return False
    try:
        return len(response.get_data()) >= 500
    except (TypeError, AttributeError):
        return False


@app.after_request
def add_security_headers(response):
    """Add browser-side defenses to every response."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "base-uri 'self'; object-src 'none'; form-action 'self'; "
        "img-src 'self' data: https: blob:; "
        "media-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com https://cdnjs.cloudflare.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "connect-src 'self' https://*.tile.openstreetmap.org https://*.openstreetmap.org; "
        "frame-src 'self' https://maps.google.com https://www.google.com https://*.google.com https://*.google.co.in"
    )
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')

    # Static assets are cache-busted via ?v=... query strings, so we serve them
    # with a long browser/edge cache lifetime. Admin/member/login pages must
    # never be cached. Everything else falls back to the framework default.
    if request.path.startswith('/static/'):
        if request.args.get('v'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        else:
            response.headers['Cache-Control'] = 'public, max-age=120, must-revalidate'
        # Allow gzip buffering of static text assets (Flask streams these via
        # passthrough, which bypasses compression). Removing passthrough makes
        # the small text/CSS/JS files below compressible, so a mobile browser
        # downloads far fewer bytes for the same cached asset.
        if response.mimetype and response.mimetype.startswith(
            ('text/', 'application/javascript', 'application/json')
        ):
            response.direct_passthrough = False
    elif request.path.startswith(('/admin', '/member', '/login')):
        response.headers['Cache-Control'] = 'no-store'

    # gzip-compress large text responses when the client supports it.
    if _should_compress(response, request):
        payload = response.get_data()
        compressed = gzip.compress(payload, compresslevel=6)
        # Only keep compression when it actually makes the payload smaller.
        if len(compressed) < len(payload):
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            response.set_data(compressed)

    return response

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin authorization required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ('admin', 'member'):
            flash('Team member authorization required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------------------------------------------
# Authentication Routes (Admin Login & Logout)
# ---------------------------------------------------------
@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return ('', 200)
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('events_list'))


@app.route('/healthz', methods=['GET', 'HEAD'])
def healthz():
    """Lightweight deployment health check that verifies database reachability."""
    if request.method == 'HEAD':
        return ('', 200)
    try:
        query_db('SELECT 1', one=True)
    except Exception:
        return jsonify({'status': 'unhealthy'}), 503
    return jsonify({'status': 'ok', 'database': database.DB_MODE}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif session.get('role') == 'member':
        return redirect(url_for('member_dashboard'))

    if request.method == 'POST':
        client_key = request.remote_addr or 'unknown-client'
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if login_is_throttled(client_key, identifier):
            flash('Too many unsuccessful attempts. Please try again in a few minutes.', 'warning')
            return render_template('login.html'), 429

        user = query_db(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (identifier, identifier),
            one=True
        )
        if not user and identifier.isdigit():
            user = query_db("SELECT * FROM users WHERE id = %s", (int(identifier),), one=True)

        required_role_pwd = (
            Config.ADMIN_PASSWORD if (user and user.get('role') == 'admin')
            else (getattr(Config, 'MEMBER_PASSWORD', '') or Config.ADMIN_PASSWORD)
        )
        if user and user.get('role') in ('admin', 'member') and not required_role_pwd and not app.config.get('TESTING') and password:
            flash('Administrator password configuration is required before sign-in is enabled.', 'danger')
            return render_template('login.html'), 503

        is_authenticated = bool(
            user
            and password
            and check_password_hash(user['password_hash'], password)
        )

        if is_authenticated:
            clear_login_failures(client_key, identifier)
            # Rotate the signed session contents after authentication to avoid
            # carrying pre-login session state into the authenticated session.
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['full_name'] = user['full_name']
            session['role'] = user['role']

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('member_dashboard'))
        else:
            record_login_failure(client_key, identifier)
            flash('Invalid ID or credentials. Please check and try again.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been safely logged out.', 'info')
    return redirect(url_for('login'))

# ---------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------
@app.route('/admin')
def admin_redirect():
    return redirect(url_for('login'))
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # 1. Total Events
    ev_res = query_db("SELECT COUNT(*) as count FROM events", one=True)
    total_events = ev_res['count'] if ev_res else 0

    # 2. Total Participants & Total Registrations
    part_res = query_db("SELECT COUNT(*) as count FROM participants", one=True)
    total_participants = part_res['count'] if part_res else 0

    reg_res = query_db("SELECT COUNT(*) as count FROM registrations", one=True)
    total_registrations = reg_res['count'] if reg_res else 0

    # 3. Attendance Counts (tied strictly to approved active registrations)
    pres_res = query_db("""
        SELECT COUNT(DISTINCT a.registration_id) as count 
        FROM attendance a
        JOIN registrations r ON a.registration_id = r.id
        WHERE a.status = 'present' AND r.status = 'approved'
    """, one=True)
    total_present = pres_res['count'] if pres_res else 0

    abs_res = query_db("""
        SELECT COUNT(DISTINCT a.registration_id) as count 
        FROM attendance a
        JOIN registrations r ON a.registration_id = r.id
        WHERE a.status = 'absent' AND a.marked_by != 'system' AND r.status = 'approved'
    """, one=True)
    total_absent = abs_res['count'] if abs_res else 0

    # 4. Certificates Generated & Sent
    cert_res = query_db("SELECT COUNT(*) as count FROM certificates", one=True)
    total_certificates = cert_res['count'] if cert_res else 0

    sent_res = query_db("SELECT COUNT(*) as count FROM certificates WHERE email_status = 'sent'", one=True)
    total_sent = sent_res['count'] if sent_res else 0

    failed_res = query_db("SELECT COUNT(*) as count FROM certificates WHERE email_status = 'failed'", one=True)
    total_failed = failed_res['count'] if failed_res else 0

    pending_cert_emails = max(0, total_certificates - total_sent - total_failed)

    # 5. Approved and Pending Counts
    appr_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE status = 'approved'", one=True)
    total_approved = appr_res['count'] if appr_res else 0

    pend_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE status = 'pending'", one=True)
    total_pending = pend_res['count'] if pend_res else 0

    # Attendance rate calculated against approved registrations
    attendance_rate = round((total_present / total_approved * 100), 1) if total_approved > 0 else 0
    unmarked_attendance = max(0, total_approved - (total_present + total_absent))

    # Eligible attendees for certificates (present in attendance, but certificate not generated yet)
    eligible_pending_cert = query_db("""
        SELECT COUNT(r.id) as count
        FROM registrations r
        JOIN attendance a ON a.registration_id = r.id AND a.status = 'present'
        LEFT JOIN certificates c ON c.registration_id = r.id
        WHERE r.status = 'approved' AND c.id IS NULL
    """, one=True)
    pending_cert_generation = eligible_pending_cert['count'] if eligible_pending_cert else 0

    cert_generation_rate = round((total_certificates / total_present * 100), 1) if total_present > 0 else 0
    cert_delivery_rate = round((total_sent / total_certificates * 100), 1) if total_certificates > 0 else 0

    stats = {
        'total_events': total_events,
        'total_participants': total_participants,
        'total_registrations': total_registrations,
        'total_present': total_present,
        'total_absent': total_absent,
        'unmarked_attendance': unmarked_attendance,
        'attendance_rate': attendance_rate,
        'total_certificates': total_certificates,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'pending_cert_emails': pending_cert_emails,
        'pending_cert_generation': pending_cert_generation,
        'cert_generation_rate': cert_generation_rate,
        'cert_delivery_rate': cert_delivery_rate,
        'total_approved': total_approved,
        'total_pending': total_pending
    }

    # Analytics: Online vs Offline Payments
    online_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE payment_method = 'Online'", one=True)
    online_count = online_res['count'] if online_res else 0

    offline_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE payment_status = 'pay_on_site' OR payment_method = 'Cash'", one=True)
    offline_count = offline_res['count'] if offline_res else 0

    analytics = {
        'online_count': online_count,
        'offline_count': offline_count
    }

    # Analytics: Event Stats for Bar Chart & Top Event
    event_stats = query_db("""
        SELECT e.event_name, COUNT(r.id) as reg_count 
        FROM events e 
        LEFT JOIN registrations r ON e.id = r.event_id 
        GROUP BY e.id 
        ORDER BY reg_count DESC
    """)
    top_event = event_stats[0] if event_stats else {'event_name': 'None', 'reg_count': 0}

    # Event Operations Matrix (combining registration, attendance & certificates per event)
    event_attendance_stats = query_db("""
        SELECT e.id as event_id, e.event_name, e.event_date,
               COUNT(r.id) as total_approved,
               SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_count,
               SUM(CASE WHEN a.status = 'absent' THEN 1 ELSE 0 END) as absent_count,
               SUM(CASE WHEN r.id IS NOT NULL AND (a.status IS NULL OR a.status = '') THEN 1 ELSE 0 END) as unmarked_count,
               COUNT(c.id) as certs_generated,
               SUM(CASE WHEN c.email_status = 'sent' THEN 1 ELSE 0 END) as certs_sent
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id AND r.status = 'approved'
        LEFT JOIN attendance a ON a.registration_id = r.id
        LEFT JOIN certificates c ON c.registration_id = r.id
        GROUP BY e.id, e.event_name, e.event_date
        ORDER BY total_approved DESC, e.event_name ASC
    """)

    # Recent Attendance Check-ins
    recent_checkins = query_db("""
        SELECT p.full_name, e.event_name, a.status, a.marked_at, a.marked_by
        FROM attendance a
        JOIN registrations r ON a.registration_id = r.id
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE a.status = 'present'
        ORDER BY a.marked_at DESC
        LIMIT 6
    """)

    # Recent Certificates Issued
    recent_certificates = query_db("""
        SELECT p.full_name, e.event_name, c.certificate_code, c.email_status, c.sent_at, c.created_at
        FROM certificates c
        JOIN registrations r ON c.registration_id = r.id
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        ORDER BY c.created_at DESC
        LIMIT 6
    """)

    # Pending Registrations
    pending_registrations = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number, r.payment_proof,
               r.payment_verified_at, r.payment_verified_by, r.receipt_sent_at, r.receipt_delivery_status,
               p.full_name, p.email, p.phone, p.college_name, p.department, 
               e.event_name, u.username as registered_by_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN users u ON r.registered_by = u.id
        WHERE r.status = 'pending'
        ORDER BY r.id ASC
    """)

    # Approved Recent Registrations
    recent_registrations = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number, r.payment_proof,
               r.payment_verified_at, r.payment_verified_by, r.receipt_sent_at, r.receipt_delivery_status,
               p.full_name, p.email, p.phone, p.college_name, p.department, 
               e.event_name, a.status as att_status, u.username as registered_by_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        LEFT JOIN users u ON r.registered_by = u.id
        WHERE r.status = 'approved'
        ORDER BY r.id DESC
    """)

    online_approved = [reg for reg in recent_registrations if reg['payment_method'] == 'Online']
    cash_approved = [reg for reg in recent_registrations if reg['payment_method'] == 'Cash']

    # Team Member Performance
    team_performance = query_db("""
        SELECT u.username, u.full_name, 
               COUNT(r.id) as total_registered,
               SUM(CASE WHEN r.payment_status = 'paid' THEN 1 ELSE 0 END) as total_paid
        FROM users u
        LEFT JOIN registrations r ON u.id = r.registered_by
        WHERE u.role = 'member'
        GROUP BY u.id
        ORDER BY total_registered DESC, u.username ASC
    """)

    # Dedicated Payment Proofs Gallery Query
    payment_screenshots = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.payment_status, r.amount_paid,
               r.payment_method, r.utr_number, r.payment_proof, r.status as reg_status,
               r.registration_date,
               p.full_name, p.email, p.phone, p.college_name,
               e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.payment_proof IS NOT NULL AND r.payment_proof != ''
        ORDER BY r.id DESC
    """)

    events = query_db("SELECT * FROM events ORDER BY id ASC")
    showcase_section = query_db(
        "SELECT * FROM event_showcase_sections WHERE section_key = %s",
        ('main-events',), one=True
    )
    
    return render_template('admin_dashboard.html', 
                           stats=stats, 
                           pending_registrations=pending_registrations,
                           recent_registrations=recent_registrations,
                           online_approved=online_approved,
                           cash_approved=cash_approved,
                           payment_screenshots=payment_screenshots,
                           team_performance=team_performance,
                           events=events,
                           analytics=analytics,
                           event_stats=event_stats,
                           top_event=top_event,
                           event_attendance_stats=event_attendance_stats,
                           recent_checkins=recent_checkins,
                           recent_certificates=recent_certificates,
                           showcase_section=showcase_section,
                           smtp_info=get_smtp_info())

@app.route('/admin/approve/<int:reg_id>', methods=['POST'])
@admin_required
def approve_registration(reg_id):
    """Approve a pending registration."""
    execute_db("UPDATE registrations SET status = 'approved' WHERE id = %s", (reg_id,))
    flash("Registration has been approved and moved to the completed list.", "success")
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/sw.js')
def service_worker():
    """Serve the root-scoped service worker for offline pass caching."""
    sw_path = os.path.join(app.root_path, 'static', 'sw.js')
    if not os.path.exists(sw_path):
        abort(404)
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = make_response(content)
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.route('/favicon.ico')
def favicon():
    """Serve the authentic college crest favicon."""
    response = send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    """Serve the authentic college crest apple touch icon."""
    response = send_from_directory(os.path.join(app.root_path, 'static'), 'apple-touch-icon.png', mimetype='image/png')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

@app.route('/site.webmanifest')
def site_webmanifest():
    """Serve the web app manifest."""
    response = send_from_directory(os.path.join(app.root_path, 'static'), 'site.webmanifest', mimetype='application/manifest+json')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

@app.route('/static/images/<path:filename>')
def serve_event_static_image(filename):
    """Resilient static image server handling casing variations, spaces, and fallbacks."""
    static_images_dir = os.path.join(app.root_path, 'static', 'images')
    # 1. Exact match on disk
    exact_path = os.path.join(static_images_dir, filename)
    if os.path.isfile(exact_path):
        return send_from_directory(static_images_dir, filename)

    # 2. Case-insensitive and punctuation-normalized lookup
    clean_req = re.sub(r'[^a-z0-9.]+', '', filename.lower())
    try:
        available_files = os.listdir(static_images_dir)
    except OSError:
        available_files = []

    for disk_file in available_files:
        if re.sub(r'[^a-z0-9.]+', '', disk_file.lower()) == clean_req:
            return send_from_directory(static_images_dir, disk_file)

    # 3. Known event image alias map
    event_key = os.path.splitext(clean_req)[0]
    canonical_lookup = {
        'beatboxing': 'Beatboxing.jpeg',
        'contentcreator': 'Content_Creator.jpeg',
        'solodance': 'Solo_Dance.jpeg',
        'groupdance': 'groupdance.jpeg',
        'techquiz': 'Tech_Quiz.jpeg',
        'photography': 'Photography.jpeg',
        'facepainting': 'facepanting.jpeg',
        'facepanting': 'facepanting.jpeg',
        'gettheshield': 'get_the_shield.jpeg',
        'madads': 'mad_adds.jpeg',
        'madadds': 'mad_adds.jpeg',
        'monoacting': 'monoacting.jpeg',
        'pencilsketching': 'pencilesketch.jpeg',
        'pencilsketch': 'pencilesketch.jpeg',
        'freefire': 'freefire.jpeg',
        'bgmi': '89e73e3fb00545329bed5ddb69478ea6.webp',
        'fashionwalk': '47a83de9ff4c4712b65dd41197a65d40.jpeg',
        'solosinging': 'solo-singing.webp',
        'singingsolo': 'solo-singing.webp',
        'singing': 'solo-singing.webp',
    }
    if event_key in canonical_lookup:
        target = canonical_lookup[event_key]
        if os.path.isfile(os.path.join(static_images_dir, target)):
            return send_from_directory(static_images_dir, target)

    # 4. Ultimate fallback to default banner image if available
    default_asset = 'event_default.jpg' if os.path.isfile(os.path.join(static_images_dir, 'event_default.jpg')) else 'hero_bg.jpg'
    if os.path.isfile(os.path.join(static_images_dir, default_asset)):
        return send_from_directory(static_images_dir, default_asset)

    return abort(404)

@app.route('/payment-status/<registration_uid>')
def payment_status(registration_uid):
    """Show a limited, shareable payment-status record."""
    registration = query_db(
        """
        SELECT r.registration_uid, r.payment_status, r.amount_paid, r.payment_method,
               r.utr_number, r.payment_proof, r.payment_verified_at, r.receipt_delivery_status,
               p.full_name, e.event_name, e.event_fee
        FROM registrations r
        JOIN participants p ON p.id = r.participant_id
        JOIN events e ON e.id = r.event_id
        WHERE r.registration_uid = %s
        """,
        (registration_uid,), one=True
    )
    if not registration:
        abort(404)

    qr_b64 = None
    try:
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(registration_uid)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        pass

    is_staff = session.get('role') in ('admin', 'member')
    owns_pass = registration_uid in session.get('recent_registration_uids', [])
    can_view_proof = bool(is_staff or owns_pass)
    return render_template('payment_status.html', registration=registration, qr_b64=qr_b64, can_view_proof=can_view_proof)


@app.route('/payment-proofs/<path:filename>')
@app.route('/static/uploads/payment_proofs/<path:filename>')
def serve_payment_proof(filename):
    """Serve uploaded UPI payment screenshots only to authorized staff or the active registrant session (SEC-05)."""
    safe_name = secure_filename(os.path.basename(filename))
    if not safe_name or safe_name != os.path.basename(filename):
        abort(404)

    is_staff = session.get('role') in ('admin', 'member')
    owns_proof = safe_name in session.get('uploaded_payment_proofs', [])
    if not is_staff and not owns_proof:
        abort(403)

    primary_dir = app.config['UPLOAD_FOLDER_PAYMENTS']
    legacy_dir = os.path.join(app.root_path, 'static', 'uploads', 'payment_proofs')
    if os.path.exists(os.path.join(primary_dir, safe_name)):
        response = send_from_directory(primary_dir, safe_name, as_attachment=False)
    elif os.path.exists(os.path.join(legacy_dir, safe_name)):
        response = send_from_directory(legacy_dir, safe_name, as_attachment=False)
    else:
        abort(404)
    response.headers['Cache-Control'] = 'private, no-store'
    return response

@app.route('/admin/export/csv')
@admin_required
def export_csv():
    status_filter = request.args.get('status', 'all')
    
    query = """
        SELECT r.id, r.registration_uid, p.full_name, r.registration_date, r.team_name, p.college_name, p.phone, p.email, r.team_size,
               r.payment_status, r.payment_method, r.amount_paid,
               CASE WHEN c.id IS NOT NULL THEN 'Yes' ELSE 'No' END as has_certificate,
               COALESCE(a.status, 'absent') as att_status,
               r.status as approval_status
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        LEFT JOIN certificates c ON c.registration_id = r.id
    """
    
    if status_filter == 'approved':
        query += " WHERE r.status = 'approved'"
    elif status_filter == 'pending':
        query += " WHERE r.status = 'pending'"
        
    query += " ORDER BY r.id DESC"
    
    records = query_db(query)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        'Registration UID', 'Participant Name', 'Registration Date', 'Team Name', 'College Name', 
        'Phone Number', 'Email ID', 'Total Participants (Team Size)', 
        'Payment Status & Method', 'Amount Paid (INR)', 
        'Signed Certificate', 'Presence on App', 'Approval Status'
    ])
    
    for row in records:
        cert_status = row['has_certificate']
        pay_str = f"{row['payment_status'].upper()} ({row['payment_method']})"
        writer.writerow([sanitize_csv_cell(c) for c in [
            row['registration_uid'],
            row['full_name'], row['registration_date'], row['team_name'] or 'N/A',
            row['college_name'], row['phone'], row['email'], row['team_size'],
            pay_str, row['amount_paid'], cert_status,
            row['att_status'].upper(), row['approval_status'].upper()
        ]])
    
    response = Response(output.getvalue(), content_type='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename=participants_{status_filter}.csv"
    return response

# ---------------------------------------------------------
# Member Dashboard & Members List
# ---------------------------------------------------------
@app.route('/members')
@member_required
def members_list():
    # Fetch all members (role='member' or 'admin') and aggregate their registrations
    members = query_db("""
        SELECT u.id, u.username, u.full_name, u.role,
               COUNT(r.id) as total_registrations,
               SUM(CASE WHEN r.payment_status = 'paid' THEN 1 ELSE 0 END) as paid_registrations,
               SUM(CASE WHEN r.payment_status = 'paid' THEN r.amount_paid ELSE 0 END) as total_collected
        FROM users u
        LEFT JOIN registrations r ON r.registered_by = u.id
        GROUP BY u.id
        ORDER BY total_collected DESC, total_registrations DESC
    """)
    return render_template('members_list.html', members=members)
# ---------------------------------------------------------
@app.route('/member/dashboard')
@member_required
def member_dashboard():
    user_id = session.get('user_id')
    registrations = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.payment_status, r.amount_paid, r.payment_method, r.team_name, r.status as approval_status, r.utr_number,
               r.payment_verified_at, r.receipt_sent_at, r.receipt_delivery_status,
               p.full_name, p.email, p.phone, p.college_name, p.department, e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.registered_by = %s
        ORDER BY r.id DESC
    """, (user_id,))
    return render_template('member_dashboard.html', registrations=registrations)

@app.route('/admin/verify-payment/<int:reg_id>', methods=['POST'], endpoint='verify_payment')
@app.route('/member/payment/<int:reg_id>', methods=['POST'])
@admin_required
def toggle_payment(reg_id):
    """Verify a payment once against the college bank record and issue receipt."""
    reg = query_db(
        """
        SELECT r.registered_by, r.payment_status, r.status,
               r.payment_method, r.utr_number, r.payment_verified_at,
               r.receipt_delivery_status, r.registration_uid,
               p.full_name, p.email, p.phone, e.event_name, e.event_fee
        FROM registrations r
        JOIN events e ON e.id = r.event_id
        JOIN participants p ON p.id = r.participant_id
        WHERE r.id = %s
        """,
        (reg_id,), one=True
    )
    if not reg:
        flash("Registration not found.", "danger")
        return redirect(request.referrer or url_for('member_dashboard'))
        
    if reg['status'] != 'approved':
        flash("Approve the registration before verifying its payment.", "warning")
        return redirect(request.referrer or url_for('member_dashboard'))

    if reg['payment_status'] == 'paid':
        flash("This payment is already verified. Use receipt resend if delivery failed.", "info")
        return redirect(request.referrer or url_for('admin_dashboard'))

    if safe_int(reg.get('event_fee'), 0) > 0:
        if reg.get('payment_method') == 'Online' and not reg.get('utr_number'):
            flash("Cannot verify an online payment without a UTR / transaction reference.", "warning")
            return redirect(request.referrer or url_for('admin_dashboard'))

    fee = max(0, safe_int(reg.get('event_fee'), 0))
    updated = execute_db(
        """
        UPDATE registrations
        SET payment_status = 'paid', amount_paid = %s,
            payment_verified_at = CURRENT_TIMESTAMP,
            payment_verified_by = %s,
            receipt_delivery_status = 'pending'
        WHERE id = %s AND COALESCE(payment_status, 'unpaid') <> 'paid'
        """,
        (fee, session.get('user_id'), reg_id)
    )

    if updated != 1:
        # The conditional UPDATE is the concurrency boundary. If another admin
        # won the race, do not send a second receipt or overwrite its audit data.
        flash("This payment was already verified by another administrator.", "info")
        return redirect(request.referrer or url_for('admin_dashboard'))

    receipt_ok, receipt_msg = send_receipt_email(
        recipient_email=reg['email'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=fee,
        utr_number=reg['utr_number'],
        registration_uid=reg['registration_uid']
    )
    wa_ok, wa_msg, wa_url = send_whatsapp_receipt(
        recipient_phone=reg['phone'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=fee,
        utr_number=reg['utr_number'],
        registration_uid=reg['registration_uid']
    )
    if receipt_ok or wa_ok:
        execute_db(
            "UPDATE registrations SET receipt_sent_at = CURRENT_TIMESTAMP, receipt_delivery_status = 'sent' WHERE id = %s",
            (reg_id,)
        )
        flash(f"Payment verified and receipt sent via email to {reg['email']} and WhatsApp to {reg['phone']}.", "success")
    else:
        execute_db(
            "UPDATE registrations SET receipt_delivery_status = 'failed' WHERE id = %s",
            (reg_id,)
        )
        flash(f"Payment verified, but receipt delivery failed: {receipt_msg}", "warning")
    return redirect(request.referrer or url_for('member_dashboard'))

# ---------------------------------------------------------
# Event Management Routes
# ---------------------------------------------------------
def get_public_events():
    """Return public events without duplicate legacy entries and ensure complete event metadata."""
    events = query_db("SELECT * FROM events ORDER BY id ASC")
    public_events = []
    seen = set()
    canonical_banners = {
        'bgmi': '89e73e3fb00545329bed5ddb69478ea6.webp',
        'freefire': 'freefire.jpeg',
        'pencilsketching': 'pencilesketch.jpeg',
        'pencilsketch': 'pencilesketch.jpeg',
        'gettheshield': 'get_the_shield.jpeg',
        'photography': 'Photography.jpeg',
        'contentcreator': 'Content_Creator.jpeg',
        'solodance': 'Solo_Dance.jpeg',
        'groupdance': 'groupdance.jpeg',
        'beatboxing': 'Beatboxing.jpeg',
        'facepainting': 'facepanting.jpeg',
        'techquiz': 'Tech_Quiz.jpeg',
        'madads': 'mad_adds.jpeg',
        'madadds': 'mad_adds.jpeg',
        'monoacting': 'monoacting.jpeg',
        'fashionwalk': '47a83de9ff4c4712b65dd41197a65d40.jpeg',
        'solosinging': 'solo-singing.webp',
    }
    static_images_dir = os.path.join(app.root_path, 'static', 'images')
    for event in events:
        normalized_name = re.sub(r'[^a-z0-9]+', '', (event.get('event_name') or '').lower())
        identity = 'bgmi' if normalized_name in ('bgmi', 'pubg') else normalized_name
        if identity in ('singingsolo', 'singing'):
            identity = 'solosinging'
        if identity in seen:
            continue
        seen.add(identity)

        # Ensure valid banner image that exists on disk
        banner_img = event.get('banner_image')
        file_exists = False
        if banner_img and banner_img != 'event_default.jpg':
            file_exists = os.path.isfile(os.path.join(static_images_dir, banner_img))
        if not file_exists and identity in canonical_banners:
            event['banner_image'] = canonical_banners[identity]

        # Ensure official Event Coordinators are always present
        if not event.get('faculty_phone'):
            event['faculty_phone'] = '88615 91085'
        if not event.get('faculty_name'):
            event['faculty_name'] = 'RANJITHA B K'
        if not event.get('student_phone'):
            event['student_phone'] = '88922 63116'
        if not event.get('student_name'):
            event['student_name'] = 'SINDHU M R'

        public_events.append(event)
    return public_events


def get_public_event_category(event_name):
    """Return the public lineup category for an official event name."""
    name = re.sub(r'[^a-z0-9]+', ' ', (event_name or '').lower()).strip()
    if name in ('bgmi', 'free fire'):
        return 'gaming'
    if name in ('tech quiz', 'get the shield'):
        return 'technical'
    if any(token in name for token in ('dance', 'singing', 'beat boxing', 'acting', 'fashion walk', 'mad ads')):
        return 'cultural'
    return 'arts'


@app.route('/events')
def events_list():
    events = get_public_events()
    category_labels = {
        'gaming': 'Gaming',
        'technical': 'Technical & Strategy',
        'cultural': 'Cultural & Performance',
        'arts': 'Arts & Media',
    }
    category_counts = {key: 0 for key in category_labels}
    for event in events:
        event['category_key'] = get_public_event_category(event.get('event_name'))
        category_counts[event['category_key']] += 1
    event_category_filters = [
        {'key': 'all', 'label': 'All Events', 'count': len(events)},
        *[
            {'key': key, 'label': label, 'count': category_counts[key]}
            for key, label in category_labels.items()
        ],
    ]
    showcase_section = query_db(
        "SELECT * FROM event_showcase_sections WHERE section_key = %s",
        ('main-events',), one=True
    )
    return render_template(
        'events.html',
        events=events,
        showcase_section=showcase_section,
        event_category_filters=event_category_filters,
    )


@app.route('/admin/event-showcase', methods=['POST'])
@admin_required
def update_event_showcase():
    """Update the editable public disc-cascade section settings."""
    eyebrow = request.form.get('eyebrow', '').strip() or 'THE LINEUP'
    title = request.form.get('title', '').strip() or 'Pick your frequency.'
    description = request.form.get('description', '').strip()
    background_color = request.form.get('background_color', '').strip() or '#11131b'
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', background_color):
        flash('Background color must be a six-digit hex color.', 'danger')
        return redirect(url_for('admin_dashboard'))

    try:
        banner_filename = save_image_upload(
            request.files.get('showcase_banner'), app.config['UPLOAD_FOLDER_BANNERS']
        )
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('admin_dashboard'))

    current = query_db(
        "SELECT banner_image FROM event_showcase_sections WHERE section_key = %s",
        ('main-events',), one=True
    )
    saved_banner = banner_filename or (current.get('banner_image') if current else None)
    if request.form.get('clear_showcase_banner') == 'on':
        saved_banner = None

    execute_db(
        """
        UPDATE event_showcase_sections
        SET eyebrow = %s, title = %s, description = %s, background_color = %s,
            banner_image = %s, is_enabled = %s, updated_at = CURRENT_TIMESTAMP
        WHERE section_key = %s
        """,
        (
            eyebrow,
            title,
            description,
            background_color,
            saved_banner,
            1 if request.form.get('is_enabled') == 'on' else 0,
            'main-events',
        )
    )
    flash('Disc-cascade event section updated successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/events/<int:event_id>/upi-qr')
def event_upi_qr(event_id):
    """Serve a fee-prefilled QR for the event using the shared official payee."""
    event = query_db(
        "SELECT event_name, event_fee FROM events WHERE id = %s",
        (event_id,), one=True
    )
    if not event or safe_int(event.get('event_fee'), 0) <= 0:
        abort(404)

    upi_id = Config.DEFAULT_UPI_ID.strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
        abort(503)
    fee = safe_int(event.get('event_fee'), 0)
    payload = 'upi://pay?' + urlencode({
        'pa': upi_id,
        'pn': Config.UPI_PAYEE_NAME,
        'am': str(fee),
        'cu': 'INR',
        'tn': f'{event.get("event_name", "Event")} registration',
    })
    image = qrcode.make(payload)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format='PNG')
    image_bytes.seek(0)
    return send_file(image_bytes, mimetype='image/png', max_age=3600)

@app.route('/admin/events/add', methods=['GET', 'POST'])
@admin_required
def add_event():
    if request.method == 'POST':
        event_name = request.form.get('event_name', '').strip()
        event_type = request.form.get('event_type', '').strip()
        event_date = request.form.get('event_date', '').strip()
        event_time = request.form.get('event_time', '').strip()
        venue = request.form.get('venue', '').strip()
        description = request.form.get('description', '').strip()
        max_participants = max(1, safe_int(request.form.get('max_participants', ''), 100))
        is_group = 1 if request.form.get('is_group') in ('1', 'true', 'on') else 0
        min_team_size = max(1, safe_int(request.form.get('min_team_size', ''), 1 if is_group == 0 else 2))
        max_team_size = max(min_team_size, safe_int(request.form.get('max_team_size', ''), 1 if is_group == 0 else 4))
        event_fee = max(0, safe_int(request.form.get('event_fee', ''), 0))
        upi_id = Config.DEFAULT_UPI_ID
        rules_text = request.form.get('rules_text', '').strip()
        faculty_name = request.form.get('faculty_name', '').strip()
        faculty_phone = request.form.get('faculty_phone', '').strip()
        student_name = request.form.get('student_name', '').strip()
        student_phone = request.form.get('student_phone', '').strip()

        if not event_name or not event_date or not venue:
            flash('Event name, date, and venue are required.', 'danger')
            return render_template('add_event.html')
        if event_fee > 0 and not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
            flash('The configured UPI recipient is invalid. Contact an administrator.', 'danger')
            return render_template('add_event.html')

        try:
            banner_filename = save_image_upload(
                request.files.get('banner_image'), app.config['UPLOAD_FOLDER_BANNERS']
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('add_event.html')

        execute_db(
            """
            INSERT INTO events (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, qr_code_image, banner_image, rules_text, faculty_name, faculty_phone, student_name, student_phone)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, None, banner_filename, rules_text, faculty_name, faculty_phone, student_name, student_phone)
        )
        flash(f"Event '{event_name}' created successfully!", 'success')
        return redirect(url_for('events_list'))

    return render_template('add_event.html')

@app.route('/admin/events/edit/<int:event_id>', methods=['GET', 'POST'])
@admin_required
def edit_event(event_id):
    event = query_db("SELECT * FROM events WHERE id = %s", (event_id,), one=True)
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events_list'))

    if request.method == 'POST':
        event_name = request.form.get('event_name', '').strip()
        event_type = request.form.get('event_type', '').strip()
        event_date = request.form.get('event_date', '').strip()
        event_time = request.form.get('event_time', '').strip()
        venue = request.form.get('venue', '').strip()
        description = request.form.get('description', '').strip()
        max_participants = max(1, safe_int(request.form.get('max_participants', ''), 100))
        is_group = 1 if request.form.get('is_group') in ('1', 'true', 'on') else 0
        min_team_size = max(1, safe_int(request.form.get('min_team_size', ''), 1 if is_group == 0 else 2))
        max_team_size = max(min_team_size, safe_int(request.form.get('max_team_size', ''), 1 if is_group == 0 else 4))
        event_fee = max(0, safe_int(request.form.get('event_fee', ''), 0))
        upi_id = Config.DEFAULT_UPI_ID
        rules_text = request.form.get('rules_text', '').strip()
        faculty_name = request.form.get('faculty_name', '').strip()
        faculty_phone = request.form.get('faculty_phone', '').strip()
        student_name = request.form.get('student_name', '').strip()
        student_phone = request.form.get('student_phone', '').strip()

        if not event_name or not event_date or not venue:
            flash('Event name, date, and venue are required.', 'danger')
            return render_template('edit_event.html', event=event)
        if event_fee > 0 and not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
            flash('The configured UPI recipient is invalid. Contact an administrator.', 'danger')
            return render_template('edit_event.html', event=event)

        try:
            banner_filename = save_image_upload(
                request.files.get('banner_image'), app.config['UPLOAD_FOLDER_BANNERS']
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('edit_event.html', event=event)

        execute_db(
            """
            UPDATE events
            SET event_name = %s, event_type = %s, event_date = %s, event_time = %s,
                venue = %s, description = %s, max_participants = %s,
                is_group = %s, min_team_size = %s, max_team_size = %s,
                event_fee = %s, upi_id = %s, qr_code_image = NULL,
                banner_image = COALESCE(%s, banner_image)
            WHERE id = %s
            """,
            (event_name, event_type, event_date, event_time, venue, description,
             max_participants, is_group, min_team_size, max_team_size, event_fee,
             upi_id, banner_filename, event_id)
        )
        # Save contact & rules fields
        execute_db(
            """UPDATE events SET rules_text = %s, faculty_name = %s, faculty_phone = %s,
               student_name = %s, student_phone = %s WHERE id = %s""",
            (rules_text, faculty_name, faculty_phone, student_name, student_phone, event_id)
        )
        flash(f"Event '{event_name}' updated successfully!", 'success')
        return redirect(url_for('events_list'))

    return render_template('edit_event.html', event=event)

@app.route('/admin/events/delete/<int:event_id>', methods=['POST'])
@admin_required
def delete_event(event_id):
    event = query_db("SELECT event_name FROM events WHERE id = %s", (event_id,), one=True)
    if event:
        execute_db("DELETE FROM events WHERE id = %s", (event_id,))
        flash(f"Event '{event['event_name']}' deleted successfully.", 'info')
    return redirect(url_for('events_list'))

# ---------------------------------------------------------
# Participant Registration
# ---------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register_participant():
    events = get_public_events()
    selected_event_id = request.args.get('event_id', '')

    user_info = None
    if 'user_id' in session:
        user_info = {
            'full_name': session.get('full_name', ''),
            'email': session.get('email', '')
        }

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        college_name = request.form.get('college_name', '').strip()
        department = request.form.get('department', '').strip()
        semester = request.form.get('semester', '').strip()
        event_id = safe_int(request.form.get('event_id', '').strip(), 0)

        # Group Event Fields
        team_name = request.form.get('team_name', '').strip() or None
        team_size = safe_int(request.form.get('team_size', ''), 1)
        
        # Payment tracking. Online payments remain pending until an admin
        # verifies the UTR; a participant-submitted reference is not proof of
        # settlement.
        payment_method = request.form.get('payment_method', 'None').strip()
        utr_number = request.form.get('utr_number', '').strip().upper() or None

        ev_record = query_db("SELECT event_name, is_group, min_team_size, max_team_size, event_fee FROM events WHERE id = %s", (event_id,), one=True) if event_id else None
        if not ev_record:
            flash('Invalid event selected.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        if semester not in ('I PUC', 'II PUC'):
            flash('Registration is open to I and II PUC students only.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
        
        event_fee = max(0, safe_int(ev_record.get('event_fee'), 0))
        payment_status = 'paid' if event_fee == 0 else 'unpaid'
        amount_paid = 0

        payment_proof = None
        if event_fee == 0:
            payment_method = 'None'
            utr_number = None
        elif payment_method == 'Online':
            if not utr_number or not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]{5,63}', utr_number):
                flash('Enter a valid UPI transaction reference (6–64 letters, numbers, or separators).', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
            payment_status = 'pending'

            # Secure payment screenshot upload (MANDATORY for Online / UPI)
            screenshot_file = request.files.get('payment_screenshot')
            if not screenshot_file or not screenshot_file.filename:
                flash('Please upload your UPI payment screenshot to complete online registration.', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
            try:
                payment_proof = save_image_upload(screenshot_file, app.config['UPLOAD_FOLDER_PAYMENTS'])
            except ValueError as img_err:
                flash(f'Payment screenshot error: {img_err}', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
        elif payment_method == 'Cash':
            utr_number = None
            payment_status = 'pay_on_site'
        else:
            flash('Select Online (UPI) or Cash before submitting a paid registration.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        registered_by = session.get('user_id') if session.get('role') in ('admin', 'member') else None

        event_name = ev_record['event_name']
        is_group_event = 1 if (ev_record.get('is_group') == 1) else 0

        if is_group_event:
            min_team_size = safe_int(ev_record.get('min_team_size'), 1)
            max_team_size = safe_int(ev_record.get('max_team_size'), min_team_size)
            if team_size < min_team_size or team_size > max_team_size:
                flash(f'Team size must be between {min_team_size} and {max_team_size}.', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
            if not team_name:
                flash('Enter a team name for this group event.', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
        else:
            team_size = 1

        # Collect additional team member names
        member_names = []
        if is_group_event:
            for i in range(2, team_size + 1):
                m_name = request.form.get(f'member_{i}_name', '').strip()
                if not m_name:
                    flash(f'Enter the full name for participant {i}.', 'danger')
                    return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
                member_names.append(m_name)
            # If custom team members textarea provided
            custom_members = request.form.get('team_members', '').strip()
            if custom_members and len(member_names) < team_size - 1:
                member_names.extend([m.strip() for m in custom_members.split(',') if m.strip()])

            if len(member_names) != team_size - 1:
                flash('Provide the full name of every team member.', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
            
            # Combine team lead with other members
            all_members_list = [full_name] + member_names
            team_members_str = ", ".join(all_members_list)
        else:
            team_members_str = None
            team_size = 1
            team_name = None

        if not email or '@' not in email or '.' not in email.split('@')[-1] or len(email.strip()) < 5:
            flash('A valid email address is required for registration.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        if not full_name or not phone or not college_name or not event_id:
            flash('All required fields must be filled.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        registration = create_registration(
            full_name=full_name,
            email=email,
            phone=phone,
            college_name=college_name,
            department=department,
            semester=semester,
            event_id=event_id,
            team_name=team_name,
            team_size=team_size,
            team_members=team_members_str,
            payment_status=payment_status,
            amount_paid=amount_paid,
            payment_method=payment_method,
            utr_number=utr_number,
            payment_proof=payment_proof,
            registered_by=registered_by,
            is_group_event=is_group_event
        )

        if not registration['ok']:
            if payment_proof:
                proof_cleanup = os.path.join(app.config['UPLOAD_FOLDER_PAYMENTS'], payment_proof)
                if os.path.exists(proof_cleanup):
                    try:
                        os.remove(proof_cleanup)
                    except OSError:
                        pass
            reason = registration['reason']
            if reason == 'duplicate_registration':
                flash('You are already registered for this event. Duplicate registration was prevented.', 'warning')
            elif reason == 'email_identity_mismatch':
                flash('This email address is already registered with a different phone number. Please use your registered phone number or contact the help desk.', 'danger')
            elif reason == 'duplicate_utr':
                flash('This UPI transaction reference has already been submitted.', 'warning')
            elif reason == 'capacity_reached':
                flash('This event is full. Please choose another event.', 'warning')
            else:
                flash('The selected event is no longer available. Please refresh and try again.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        # Record session ownership so the registrant can view their own uploaded proof on the pass page (SEC-05)
        recent_uids = list(session.get('recent_registration_uids', []))[-9:]
        recent_uids.append(registration['registration_uid'])
        session['recent_registration_uids'] = recent_uids
        if payment_proof:
            recent_proofs = list(session.get('uploaded_payment_proofs', []))[-9:]
            recent_proofs.append(payment_proof)
            session['uploaded_payment_proofs'] = recent_proofs

        team_info_msg = f" (Team: {team_name} with {team_size} members)" if is_group_event and team_name else ""
        if payment_status == 'pay_on_site':
            confirmation = 'Registration submitted! Please pay at your college desk upon arrival.'
        elif payment_status == 'pending':
            confirmation = 'Registration received and awaiting admin verification.'
        else:
            confirmation = 'Registration successful.'
        flash(f'Successfully registered! {confirmation} Reference: {registration["registration_uid"]}{team_info_msg}', 'success')
        
        return redirect(url_for('payment_status', registration_uid=registration['registration_uid']))

    return render_template('register.html', events=events, selected_event_id=selected_event_id, user_info=user_info)

# ---------------------------------------------------------
# Participant Management (Admin)
# ---------------------------------------------------------
@app.route('/admin/participants')
@admin_required
def participants_list():
    # Aggregated query fetching participants and their registrations with group details.
    # PostgreSQL uses string_agg; SQLite uses GROUP_CONCAT.
    if database.DB_MODE == 'postgres':
        event_names_expr = "string_agg(e.event_name, ', ')"
        team_names_expr = "string_agg(COALESCE(r.team_name, ''), ', ')"
    else:
        event_names_expr = "GROUP_CONCAT(e.event_name, ', ')"
        team_names_expr = "GROUP_CONCAT(COALESCE(r.team_name, ''), ', ')"

    participants = query_db(f"""
        SELECT p.*,
               {event_names_expr} as event_names,
               {team_names_expr} as team_names,
               MAX(r.team_size) as max_team_size,
               MAX(r.is_group) as has_group_reg
        FROM participants p
        LEFT JOIN registrations r ON p.id = r.participant_id
        LEFT JOIN events e ON r.event_id = e.id
        GROUP BY p.id
        ORDER BY p.id DESC
    """)
    events = query_db("SELECT * FROM events ORDER BY id ASC")
    return render_template('participants.html', participants=participants, events=events)

@app.route('/admin/participants/edit/<int:participant_id>', methods=['GET', 'POST'])
@admin_required
def edit_participant(participant_id):
    participant = query_db("SELECT * FROM participants WHERE id = %s", (participant_id,), one=True)
    if not participant:
        flash('Participant record not found.', 'danger')
        return redirect(url_for('participants_list'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        college_name = request.form.get('college_name', '').strip()
        department = request.form.get('department', '').strip()
        semester = request.form.get('semester', '').strip()

        execute_db(
            """
            UPDATE participants 
            SET full_name = %s, email = %s, phone = %s, college_name = %s, department = %s, semester = %s
            WHERE id = %s
            """,
            (full_name, email, phone, college_name, department, semester, participant_id)
        )
        flash(f"Participant '{full_name}' updated successfully.", 'success')
        return redirect(url_for('participants_list'))

    return render_template('edit_participant.html', participant=participant)

@app.route('/admin/participants/delete/<int:participant_id>', methods=['POST'])
@admin_required
def delete_participant(participant_id):
    execute_db("DELETE FROM participants WHERE id = %s", (participant_id,))
    flash('Participant deleted successfully.', 'info')
    return redirect(url_for('participants_list'))

# ---------------------------------------------------------
# Attendance Management
# ---------------------------------------------------------
@app.route('/admin/attendance')
@admin_required
def attendance_manager():
    attendance_records = query_db("""
        SELECT r.id as registration_id, r.is_group, r.team_name, r.team_size, r.team_members,
               p.full_name, p.email, p.college_name, p.department, 
               e.event_name, e.event_date, e.is_group as event_is_group,
               COALESCE(CASE WHEN a.status = 'absent' AND a.marked_by = 'system' THEN 'pending' ELSE a.status END, 'pending') as att_status
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        WHERE r.status = 'approved'
        ORDER BY e.id ASC, p.full_name ASC
    """)
    events = query_db("SELECT * FROM events ORDER BY id ASC")

    present_count = sum(1 for r in attendance_records if r['att_status'] == 'present')
    absent_count = sum(1 for r in attendance_records if r['att_status'] == 'absent')
    pending_count = len(attendance_records) - present_count - absent_count

    return render_template(
        'attendance.html', 
        attendance_records=attendance_records, 
        events=events,
        present_count=present_count,
        absent_count=absent_count,
        pending_count=pending_count
    )

@app.route('/attendance/toggle', methods=['POST'])
@admin_required
def toggle_attendance():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Invalid request body'}), 400

    registration_id = data.get('registration_id')
    new_status = data.get('status', 'absent')

    if not registration_id or new_status not in ('present', 'absent'):
        return jsonify({'success': False, 'error': 'Invalid parameters'}), 400

    # Check if attendance record exists
    existing = query_db("SELECT id FROM attendance WHERE registration_id = %s", (registration_id,), one=True)
    if existing:
        execute_db(
            "UPDATE attendance SET status = %s, marked_by = %s WHERE registration_id = %s",
            (new_status, session.get('username', 'admin'), registration_id)
        )
    else:
        execute_db(
            "INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, %s, %s)",
            (registration_id, new_status, session.get('username', 'admin'))
        )

    return jsonify({
        'success': True, 
        'message': f"Attendance updated to {new_status.upper()}", 
        'status': new_status
    })

@app.route('/admin/attendance/delete/<int:registration_id>', methods=['POST'])
@admin_required
def delete_attendance_record(registration_id):
    """Delete a registration / attendance record and any associated certificates safely."""
    reg = query_db("SELECT id, participant_id, event_id FROM registrations WHERE id = %s", (registration_id,), one=True)
    if not reg:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Record not found'}), 404
        flash('Attendance record not found.', 'danger')
        return redirect(url_for('attendance_manager'))

    # Remove physical certificate file if it exists
    cert = query_db("SELECT file_path FROM certificates WHERE registration_id = %s", (registration_id,), one=True)
    if cert and cert.get('file_path') and os.path.exists(cert['file_path']):
        try:
            os.remove(cert['file_path'])
        except Exception as e:
            print(f"Failed to delete certificate file: {e}")

    # Clean up dependent records first to prevent foreign key issues
    execute_db("DELETE FROM certificates WHERE registration_id = %s", (registration_id,))
    execute_db("DELETE FROM attendance WHERE registration_id = %s", (registration_id,))
    execute_db("DELETE FROM registrations WHERE id = %s", (registration_id,))
    
    if request.is_json:
        return jsonify({'success': True, 'message': 'Attendance and registration record removed successfully.'})
    
    flash('Attendance and registration record removed successfully.', 'info')
    return redirect(url_for('attendance_manager'))

# ---------------------------------------------------------
# Certificate Hub & Automatic Generation
# ---------------------------------------------------------

@app.route('/admin/certificates')
@admin_required
def certificates_manager():
    # Load coordinates
    coords = {}
    coords_path = os.path.join(app.root_path, 'static', 'uploads', 'cert_coordinates.json')
    if os.path.exists(coords_path):
        try:
            import json
            with open(coords_path, 'r') as f:
                coords = json.load(f)
        except Exception:
            pass

    cert_list = query_db("""
        SELECT r.id as registration_id, r.is_group, r.team_name, r.team_size, r.team_members,
               p.id as participant_id, p.full_name, p.email, p.phone, p.college_name, p.department, p.semester,
               e.id as event_id, e.event_name, e.event_date,
               COALESCE(a.status, 'absent') as att_status,
               c.id as cert_id, c.certificate_code, c.email_status, c.sent_at
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        LEFT JOIN certificates c ON c.registration_id = r.id
        WHERE r.status = 'approved'
        ORDER BY e.id ASC, p.full_name ASC
    """)
    events = query_db("SELECT * FROM events ORDER BY id ASC")
    smtp_info = get_smtp_info()
    return render_template('certificates.html', cert_list=cert_list, events=events, smtp_info=smtp_info, coords=coords)

@app.route('/admin/settings/certificate-coords', methods=['POST'])
@admin_required
def save_certificate_coords():
    coords = {
        'name_x': request.form.get('name_x', type=int) or 1240,
        'name_y': request.form.get('name_y', type=int) or 610,
        'rank_x': request.form.get('rank_x', type=int) or 1240,
        'rank_y': request.form.get('rank_y', type=int) or 740,
        'event_x': request.form.get('event_x', type=int) or 1240,
        'event_y': request.form.get('event_y', type=int) or 870,
        'date_x': request.form.get('date_x', type=int) or 115,
        'date_y': request.form.get('date_y', type=int) or 1540
    }
    
    upload_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    coords_path = os.path.join(upload_dir, 'cert_coordinates.json')
    
    try:
        import json
        with open(coords_path, 'w') as f:
            json.dump(coords, f)
        flash('Coordinate settings saved successfully!', 'success')
    except Exception as e:
        flash(f'Failed to save coordinates: {e}', 'error')
        
    return redirect(url_for('certificates_manager'))

@app.route('/admin/settings/certificate-template', methods=['POST'])
@admin_required
def upload_certificate_template():
    if 'template_image' not in request.files:
        flash('No image file part', 'error')
        return redirect(url_for('certificates_manager'))

    file = request.files['template_image']
    if not file or file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('certificates_manager'))

    original_name = secure_filename(file.filename)
    extension = os.path.splitext(original_name)[1].lower().lstrip('.')
    if not original_name or extension not in {'png', 'jpg', 'jpeg', 'webp'}:
        flash('Please upload a valid PNG, JPG, JPEG, or WEBP certificate template.', 'danger')
        return redirect(url_for('certificates_manager'))

    upload_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, 'certificate_template.png')

    try:
        with Image.open(file.stream) as probe:
            if probe.width > 6000 or probe.height > 6000:
                flash('Template image dimensions must not exceed 6000 × 6000 pixels.', 'danger')
                return redirect(url_for('certificates_manager'))
            probe.verify()
        file.stream.seek(0)
        with Image.open(file.stream) as img:
            img.convert('RGB').save(file_path, 'PNG', optimize=True)
        flash('Certificate template uploaded successfully!', 'success')
    except (UnidentifiedImageError, OSError, ValueError) as e:
        flash(f'Failed to process template image: {e}', 'error')

    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/generate/<int:reg_id>', methods=['POST'])
@admin_required
def generate_single_certificate(reg_id):
    reg = query_db("""
        SELECT r.id as registration_id, r.participant_id, r.event_id, r.team_name, r.is_group,
               p.full_name, p.college_name, p.department, p.semester,
               e.event_name, e.event_date,
               COALESCE(a.status, 'absent') as att_status
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        WHERE r.id = %s
    """, (reg_id,), one=True)

    if not reg:
        flash('Registration record not found.', 'danger')
        return redirect(url_for('certificates_manager'))

    # Check if certificate already exists on disk
    existing = query_db("SELECT id, certificate_code, file_path FROM certificates WHERE registration_id = %s", (reg_id,), one=True)
    if existing and existing.get('file_path') and os.path.exists(existing['file_path']):
        flash(f"Certificate already generated with ID: {existing['certificate_code']}", 'info')
        return redirect(url_for('certificates_manager'))

    # Generate Certificate
    cert_code, file_path, rel_url = generate_certificate(
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        event_date=reg['event_date'],
        college_name=reg['college_name'],
        cert_code=existing['certificate_code'] if existing else None,
        department=reg.get('department') or 'PCMC',
        semester=reg.get('semester') or 'Second PUC',
        team_name=reg.get('team_name')
    )

    if existing:
        execute_db("""
            UPDATE certificates 
            SET certificate_code = %s, issue_date = %s, file_path = %s, email_status = %s
            WHERE id = %s
        """, (cert_code, reg['event_date'], file_path, 'pending', existing['id']))
    else:
        execute_db("""
            INSERT INTO certificates (certificate_code, registration_id, participant_id, event_id, issue_date, file_path, email_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (cert_code, reg_id, reg['participant_id'], reg['event_id'], reg['event_date'], file_path, 'pending'))

    flash(f"Certificate generated successfully! Certificate ID: {cert_code}", 'success')
    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/generate-bulk', methods=['POST'])
@admin_required
def generate_bulk_certificates():
    # Direct generation for all registered participants without validation barriers
    eligible = query_db("""
        SELECT r.id as registration_id, r.participant_id, r.event_id, r.team_name,
               p.full_name, p.college_name, p.department, p.semester,
               e.event_name, e.event_date,
               c.id as cert_id, c.file_path, c.certificate_code
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        JOIN attendance a ON a.registration_id = r.id AND a.status = 'present'
        LEFT JOIN certificates c ON c.registration_id = r.id
        WHERE r.status = 'approved'
    """)

    count = 0
    for reg in eligible or []:
        # Skip if certificate already exists and valid on disk
        if reg.get('cert_id') and reg.get('file_path') and os.path.exists(reg['file_path']):
            continue

        cert_code, file_path, rel_url = generate_certificate(
            participant_name=reg['full_name'],
            event_name=reg['event_name'],
            event_date=reg['event_date'],
            college_name=reg['college_name'],
            cert_code=reg.get('certificate_code'),
            department=reg.get('department') or 'PCMC',
            semester=reg.get('semester') or 'Second PUC',
            team_name=reg.get('team_name')
        )
        if reg.get('cert_id'):
            execute_db("""
                UPDATE certificates 
                SET certificate_code = %s, issue_date = %s, file_path = %s, email_status = %s
                WHERE id = %s
            """, (cert_code, reg['event_date'], file_path, 'pending', reg['cert_id']))
        else:
            execute_db("""
                INSERT INTO certificates (certificate_code, registration_id, participant_id, event_id, issue_date, file_path, email_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (cert_code, reg['registration_id'], reg['participant_id'], reg['event_id'], reg['event_date'], file_path, 'pending'))
        count += 1

    if count > 0:
        flash(f"Successfully generated {count} certificate(s) for present attendees!", 'success')
    else:
        flash("All present attendees already have valid certificates generated.", 'info')

    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/send-email/<int:cert_id>', methods=['POST'])
@admin_required
def send_certificate_email_route(cert_id):
    cert = query_db("""
        SELECT c.*, p.full_name, p.email, p.college_name, p.department, p.semester,
               e.event_name, e.event_date, r.team_name, r.is_group, r.team_members
        FROM certificates c
        LEFT JOIN registrations r ON c.registration_id = r.id
        LEFT JOIN participants p ON c.participant_id = p.id
        LEFT JOIN events e ON c.event_id = e.id
        WHERE c.id = %s
    """, (cert_id,), one=True)

    if not cert:
        flash('Certificate record not found.', 'danger')
        return redirect(url_for('certificates_manager'))

    # Regenerate file if missing from disk
    if not cert.get('file_path') or not os.path.exists(cert['file_path']):
        _, file_path, _ = generate_certificate(
            participant_name=cert['full_name'],
            event_name=cert['event_name'],
            event_date=cert['event_date'],
            college_name=cert['college_name'],
            cert_code=cert['certificate_code'],
            department=cert.get('department') or 'PCMC',
            semester=cert.get('semester') or 'Second PUC',
            team_name=cert.get('team_name')
        )
        cert['file_path'] = file_path

    attachment_bytes = None
    attachment_filename = None
    
    if cert.get('is_group') == 1 and cert.get('team_members'):
        attachment_bytes = generate_team_certificates_zip(
            team_members_str=cert['team_members'],
            event_name=cert['event_name'],
            event_date=cert['event_date'],
            college_name=cert['college_name'],
            cert_code_base=cert['certificate_code'],
            department=cert['department'],
            semester=cert['semester'],
            team_name=cert['team_name']
        )
        attachment_filename = f"Team_{cert['team_name'] or 'Certificates'}.zip"

    success, msg = send_certificate_email(
        recipient_email=cert['email'],
        participant_name=cert['full_name'],
        event_name=cert['event_name'],
        certificate_path=cert['file_path'],
        certificate_code=cert['certificate_code'],
        attachment_bytes=attachment_bytes,
        attachment_filename=attachment_filename
    )

    if success:
        execute_db(
            "UPDATE certificates SET email_status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = %s",
            (cert_id,)
        )
        flash(msg, 'success')
    else:
        execute_db(
            "UPDATE certificates SET email_status = 'failed' WHERE id = %s",
            (cert_id,)
        )
        flash(f"Email dispatch error: {msg}", 'danger')

    return redirect(url_for('certificates_manager'))

@app.route('/admin/receipts/send-email/<int:reg_id>', methods=['POST'])
@admin_required
def send_receipt_email_route(reg_id):
    """
    Sends the payment receipt to the participant via both Email and WhatsApp.
    """
    reg = query_db("""
        SELECT r.*, p.full_name, p.email, p.phone, e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.id = %s
    """, (reg_id,), one=True)
    
    if not reg:
        flash("Registration not found.", "danger")
        return redirect(request.referrer or url_for('admin_dashboard'))
    
    if reg['payment_status'] != 'paid':
        flash("Cannot send receipt for unpaid registration.", "warning")
        return redirect(request.referrer or url_for('admin_dashboard'))

    email_ok, email_msg = send_receipt_email(
        recipient_email=reg['email'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number'],
        registration_uid=reg['registration_uid']
    )
    wa_ok, wa_msg, wa_url = send_whatsapp_receipt(
        recipient_phone=reg['phone'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number'],
        registration_uid=reg['registration_uid']
    )
    
    if email_ok or wa_ok:
        execute_db(
            "UPDATE registrations SET receipt_sent_at = CURRENT_TIMESTAMP, receipt_delivery_status = 'sent' WHERE id = %s",
            (reg_id,)
        )
        flash(f"Receipt dispatched successfully via Email ({reg['email']}) and WhatsApp ({reg['phone']}).", 'success')
    else:
        execute_db(
            "UPDATE registrations SET receipt_delivery_status = 'failed' WHERE id = %s",
            (reg_id,)
        )
        flash(f"Receipt dispatch error: {email_msg}", 'danger')
        
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/registration/<registration_uid>/whatsapp-receipt')
def registration_whatsapp_receipt(registration_uid):
    """Generate and redirect to a WhatsApp receipt click-to-chat URL."""
    reg = query_db("""
        SELECT r.*, p.full_name, p.phone, p.email, e.event_name, e.event_fee
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.registration_uid = %s
    """, (registration_uid,), one=True)
    if not reg:
        abort(404)
    amount = reg.get('amount_paid') or reg.get('event_fee') or 0
    _, _, wa_url = send_whatsapp_receipt(
        recipient_phone=reg.get('phone'),
        participant_name=reg.get('full_name'),
        event_name=reg.get('event_name'),
        payment_method=reg.get('payment_method') or 'Verified',
        amount_paid=amount,
        utr_number=reg.get('utr_number'),
        registration_uid=reg.get('registration_uid')
    )
    return redirect(wa_url)
        
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/certificates/send-bulk', methods=['POST'])
@admin_required
def send_bulk_certificate_emails():
    # Find all generated certificates that have not been emailed yet
    pending = query_db("""
        SELECT c.*, p.full_name, p.email, p.college_name, p.department, p.semester,
               e.event_name, e.event_date, r.team_name
        FROM certificates c
        LEFT JOIN registrations r ON c.registration_id = r.id
        LEFT JOIN participants p ON c.participant_id = p.id
        LEFT JOIN events e ON c.event_id = e.id
        WHERE c.email_status != 'sent' OR c.email_status IS NULL
    """)

    if not pending:
        flash("All generated certificates have already been emailed!", "info")
        return redirect(url_for('certificates_manager'))

    sent_count = 0
    for cert in pending:
        # Regenerate file if missing from disk
        if not cert.get('file_path') or not os.path.exists(cert['file_path']):
            _, file_path, _ = generate_certificate(
                participant_name=cert['full_name'],
                event_name=cert['event_name'],
                event_date=cert['event_date'],
                college_name=cert['college_name'],
                cert_code=cert['certificate_code'],
                department=cert.get('department') or 'PCMC',
                semester=cert.get('semester') or 'Second PUC',
                team_name=cert.get('team_name')
            )
            cert['file_path'] = file_path

        success, _ = send_certificate_email(
            recipient_email=cert['email'],
            participant_name=cert['full_name'],
            event_name=cert['event_name'],
            certificate_path=cert['file_path'],
            certificate_code=cert['certificate_code']
        )
        if success:
            execute_db(
                "UPDATE certificates SET email_status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = %s",
                (cert['id'],)
            )
            sent_count += 1

    smtp_info = get_smtp_info()
    mode_text = "Safe Demo Mode" if smtp_info['is_demo'] else f"Live {smtp_info['mode'].upper()}"
    flash(f"Successfully emailed {sent_count} certificate(s) via {mode_text}!", 'success')
    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/toggle-mode', methods=['POST'])
@admin_required
def toggle_smtp_mode():
    if Config.APP_ENV == 'production':
        flash('Email mode is controlled by deployment secrets in production.', 'warning')
        return redirect(url_for('certificates_manager'))

    new_mode = request.form.get('mode', 'demo').strip().lower()
    if new_mode not in ('demo', 'live'):
        new_mode = 'demo'

    env_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '.env')
    content = ""
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
    import re
    if re.search(r'^SMTP_MODE=.*$', content, flags=re.MULTILINE):
        content = re.sub(r'^SMTP_MODE=.*$', f'SMTP_MODE={new_mode}', content, flags=re.MULTILINE)
    else:
        content = f"SMTP_MODE={new_mode}\n" + content
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)

    flash(f"Email Dispatch Mode updated to: {new_mode.upper()}", 'info')
    return redirect(url_for('certificates_manager'))

# ---------------------------------------------------------
# Certificate Downloads
# ---------------------------------------------------------

@app.route('/certificates/<path:filename>')
def download_certificate_file(filename):
    safe_filename = secure_filename(os.path.basename(filename))
    if safe_filename != filename or not safe_filename.lower().endswith('.png'):
        abort(404)
    filename = safe_filename
    file_path = os.path.join(Config.CERTIFICATE_FOLDER, filename)
    if not os.path.exists(file_path):
        # On-demand regeneration if file missing on disk
        code = os.path.splitext(filename)[0]
        cert = query_db("""
            SELECT c.*, p.full_name, p.college_name, p.department, p.semester,
                   e.event_name, e.event_date, r.team_name
            FROM certificates c
            JOIN registrations r ON c.registration_id = r.id
            JOIN participants p ON c.participant_id = p.id
            JOIN events e ON c.event_id = e.id
            WHERE c.certificate_code = %s
        """, (code,), one=True)
        if cert:
            generate_certificate(
                participant_name=cert['full_name'],
                event_name=cert['event_name'],
                event_date=cert['event_date'],
                college_name=cert['college_name'],
                cert_code=cert['certificate_code'],
                department=cert.get('department') or 'PCMC',
                semester=cert.get('semester') or 'Second PUC',
                team_name=cert.get('team_name')
            )
    return send_from_directory(Config.CERTIFICATE_FOLDER, filename, as_attachment=False)

# ---------------------------------------------------------
# Legacy Student Portal Redirect
# ---------------------------------------------------------
@app.route('/student/my-events')
def my_events():
    return redirect(url_for('events_list'))


# ---------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------

@app.route('/admin/export/full-backup-csv', endpoint='export_registrations_csv')
@app.route('/admin/export/registrations-csv', endpoint='export_registrations_csv_alias')
@admin_required
def export_registrations_csv():
    import csv
    import io
    from flask import Response
    
    # Query all participants/registrations
    records = query_db("""
        SELECT r.registration_uid, p.full_name, p.email, p.phone, p.college_name, p.department,
               e.event_name, r.payment_status, r.amount_paid, r.registration_date, r.utr_number
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        ORDER BY r.registration_date DESC
    """)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Registration UID', 'Full Name', 'Email', 'Phone', 'College', 'Department', 'Event', 'Payment Status', 'Amount Paid', 'Registration Date', 'UTR'])
    
    if records:
        for row in records:
            writer.writerow([sanitize_csv_cell(c) for c in [
                row.get('registration_uid', ''),
                row.get('full_name', ''),
                row.get('email', ''),
                row.get('phone', ''),
                row.get('college_name', ''),
                row.get('department', ''),
                row.get('event_name', ''),
                row.get('payment_status', ''),
                row.get('amount_paid', ''),
                row.get('registration_date', ''),
                row.get('utr_number', '')
            ]])
        
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": "attachment; filename=all_registrations_backup.csv"}
    )


def remove_registration_record(registration_id):
    """Safely delete a registration, its attendance, certificate file/record, and orphan participant."""
    reg = query_db("SELECT id, participant_id, event_id FROM registrations WHERE id = %s", (registration_id,), one=True)
    if not reg:
        return False
    
    participant_id = reg['participant_id']
    cert = query_db("SELECT file_path FROM certificates WHERE registration_id = %s", (registration_id,), one=True)
    if cert and cert.get('file_path') and os.path.exists(cert['file_path']):
        try:
            os.remove(cert['file_path'])
        except Exception as e:
            app.logger.warning(f"Failed to delete certificate file: {e}")
            
    execute_db("DELETE FROM certificates WHERE registration_id = %s", (registration_id,))
    execute_db("DELETE FROM attendance WHERE registration_id = %s", (registration_id,))
    execute_db("DELETE FROM registrations WHERE id = %s", (registration_id,))
    
    # Check if participant has remaining registrations
    remaining = query_db("SELECT id FROM registrations WHERE participant_id = %s", (participant_id,))
    if not remaining:
        execute_db("DELETE FROM participants WHERE id = %s", (participant_id,))
    return True


@app.route('/admin/export/registration/<int:reg_id>', endpoint='export_single_registration')
@admin_required
def export_single_registration(reg_id):
    """Download backup file of a single registration before deletion."""
    import json
    from flask import Response
    row = query_db("""
        SELECT r.id, r.registration_uid, r.payment_status, r.payment_method, r.amount_paid,
               r.registration_date, r.utr_number, r.payment_proof, r.team_name,
               p.full_name, p.email, p.phone, p.college_name, p.department,
               e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.id = %s
    """, (reg_id,), one=True)
    if not row:
        return jsonify({'error': 'Registration not found'}), 404
        
    data = dict(row)
    for k, v in data.items():
        if hasattr(v, 'isoformat'):
            data[k] = v.isoformat()
            
    content = json.dumps(data, indent=2)
    filename = f"backup_registration_{data.get('registration_uid', reg_id)}.json"
    
    return Response(
        content,
        mimetype='application/json',
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@app.route('/admin/registrations/delete/<int:reg_id>', methods=['POST'])
@admin_required
def delete_single_registration(reg_id):
    success = remove_registration_record(reg_id)
    if request.is_json:
        if success:
            return jsonify({'success': True, 'message': 'Registration deleted successfully.'})
        return jsonify({'success': False, 'error': 'Registration not found.'}), 404
    if success:
        flash('Registration deleted successfully.', 'info')
    else:
        flash('Registration record not found.', 'danger')
    return redirect(url_for('admin_dashboard') + '#registrations')


@app.route('/admin/registrations/delete_selected', methods=['POST'])
@admin_required
def delete_selected_registrations():
    data = request.get_json(silent=True) or {}
    reg_ids = data.get('reg_ids')
    if not reg_ids:
        reg_ids = request.form.getlist('selected_reg_ids')
        if not reg_ids and request.form.get('reg_ids'):
            reg_ids = [x.strip() for x in request.form.get('reg_ids').split(',') if x.strip()]
            
    if not reg_ids:
        if request.is_json:
            return jsonify({'success': False, 'error': 'No registrations selected.'}), 400
        flash('No registrations selected for deletion.', 'warning')
        return redirect(url_for('admin_dashboard') + '#registrations')
        
    deleted_count = 0
    for r_id in reg_ids:
        try:
            reg_int = int(r_id)
            if remove_registration_record(reg_int):
                deleted_count += 1
        except ValueError:
            continue
            
    if request.is_json:
        return jsonify({'success': True, 'deleted_count': deleted_count, 'message': f'Deleted {deleted_count} registration(s).'})
        
    flash(f'Successfully deleted {deleted_count} registration(s).', 'success')
    return redirect(url_for('admin_dashboard') + '#registrations')


@app.route('/admin/registrations/export_selected', methods=['POST', 'GET'])
@admin_required
def export_selected_registrations():
    ids_param = request.args.get('ids', '')
    if ids_param:
        reg_ids = [x.strip() for x in ids_param.split(',') if x.strip()]
    else:
        data = request.get_json(silent=True) or {}
        reg_ids = data.get('reg_ids') or request.form.getlist('selected_reg_ids')
        if not reg_ids and request.form.get('reg_ids'):
            reg_ids = [x.strip() for x in request.form.get('reg_ids').split(',') if x.strip()]

    if not reg_ids:
        flash('No registrations selected for export.', 'warning')
        return redirect(url_for('admin_dashboard') + '#registrations')

    valid_ids = []
    for x in reg_ids:
        try:
            valid_ids.append(int(x))
        except ValueError:
            pass

    if not valid_ids:
        flash('Invalid registration IDs.', 'danger')
        return redirect(url_for('admin_dashboard') + '#registrations')

    placeholders = ', '.join(['%s'] * len(valid_ids))
    records = query_db(f"""
        SELECT r.registration_uid, p.full_name, p.email, p.phone, p.college_name, p.department,
               COALESCE(e.event_name, 'Event N/A') as event_name, r.payment_status, r.amount_paid, r.registration_date, r.utr_number
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        LEFT JOIN events e ON r.event_id = e.id
        WHERE r.id IN ({placeholders})
        ORDER BY r.registration_date DESC
    """, tuple(valid_ids))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Registration UID', 'Full Name', 'Email', 'Phone', 'College', 'Department', 'Event', 'Payment Status', 'Amount Paid', 'Registration Date', 'UTR'])

    if records:
        for row in records:
            writer.writerow([sanitize_csv_cell(c) for c in [
                row.get('registration_uid', ''),
                row.get('full_name', ''),
                row.get('email', ''),
                row.get('phone', ''),
                row.get('college_name', ''),
                row.get('department', ''),
                row.get('event_name', ''),
                row.get('payment_status', ''),
                row.get('amount_paid', ''),
                row.get('registration_date', ''),
                row.get('utr_number', '')
            ]])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": "attachment; filename=selected_registrations_backup.csv"}
    )


@app.route('/admin/clear_all', methods=['POST'])
@admin_required
def clear_all_registrations():
    # Remove physical certificate files
    try:
        certs = query_db("SELECT file_path FROM certificates")
        for c in certs:
            if c.get('file_path') and os.path.exists(c['file_path']):
                try:
                    os.remove(c['file_path'])
                except Exception:
                    pass
    except Exception as e:
        app.logger.warning(f"Error cleaning certificate files: {e}")

    # Only clear tables tracking user registration
    execute_db("DELETE FROM attendance")
    execute_db("DELETE FROM certificates")
    execute_db("DELETE FROM registrations")
    execute_db("DELETE FROM participants")
    flash("All registrations, participants, attendance, and certificates have been permanently cleared.", "success")
    return redirect(url_for('admin_dashboard') + '#registrations')

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json() or {}
    message = data.get('message', '').strip().lower()
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Empty message'})
        
    # Basic Rule-Based Fallback for AI Assistant
    # In production, integrate `google.generativeai` here.
    reply = "I'm still learning! But I can tell you that you can register for events using the Registration page. If you choose 'Pay On-Site', you can pay cash at the venue."
    
    if 'when' in message or 'time' in message or 'schedule' in message:
        reply = "Events are scheduled throughout the day. Please check the specific event cards on the homepage for exact timings."
    elif 'where' in message or 'venue' in message or 'location' in message:
        reply = "All events are held at the Shree Daksha Academy main campus. Refer to your event ticket for the exact room number."
    elif 'fee' in message or 'pay' in message or 'cost' in message:
        reply = "You can pay online via UPI or choose the 'Pay On-Site' option to pay in cash when you arrive. Registration fees vary per event."
    elif 'qr' in message or 'ticket' in message:
        reply = "Once registered, you will receive a QR Code. Keep it safe! Our volunteers will scan it when you arrive to mark your attendance."
        
    return jsonify({'status': 'success', 'reply': reply})

@app.route('/scanner')
@app.route('/admin/qr_scanner')
@member_required
def qr_scanner():
    return render_template('qr_scanner.html')

@app.route('/api/scan_qr')
@member_required
def api_scan_qr():
    uid = request.args.get('uid', '').strip()
    if not uid:
        return jsonify({'status': 'error', 'message': 'No UID provided'})
        
    res = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.is_group, r.team_name, r.team_size,
               r.payment_status, r.payment_method, r.amount_paid, r.utr_number, r.payment_proof,
               p.full_name, p.college_name, p.department, p.phone, p.email,
               e.event_name, e.event_fee,
               (SELECT status FROM attendance a WHERE a.registration_id = r.id) as attendance_status
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.registration_uid = %s
    """, (uid,), one=True)
    
    if res:
        return jsonify({'status': 'success', 'data': dict(res)})
    return jsonify({'status': 'error', 'message': 'Invalid QR Code'})

@app.route('/api/mark_attended', methods=['POST'])
@member_required
def api_mark_attended():
    data = request.get_json() or {}
    reg_id = data.get('registration_id')
    collect_cash = data.get('collect_cash', False)
    
    if not reg_id:
        return jsonify({'status': 'error', 'message': 'Invalid registration ID'}), 400
        
    # Verify cash payment and record the same audit trail as online payment.
    reg = query_db(
        """
        SELECT r.id, r.payment_status, r.payment_method, r.utr_number, r.registration_uid,
               p.full_name, p.email, p.phone, e.event_name, e.event_fee
        FROM registrations r
        JOIN participants p ON p.id = r.participant_id
        JOIN events e ON e.id = r.event_id
        WHERE r.id = %s
        """,
        (reg_id,), one=True
    )
    if not reg:
        return jsonify({'status': 'error', 'message': 'Registration not found'}), 404

    receipt_warning = None
    fee = max(0, safe_int(reg.get('event_fee'), 0))
    user_id = session.get('user_id')

    # If it was pay_on_site, unpaid, or the coordinator collected cash
    if reg['payment_status'] in ('pay_on_site', 'unpaid') or collect_cash:
        claimed = execute_db(
            """
            UPDATE registrations
            SET payment_status = 'paid',
                payment_method = 'Cash',
                amount_paid = %s,
                payment_verified_at = CURRENT_TIMESTAMP,
                payment_verified_by = %s,
                status = 'approved',
                receipt_delivery_status = 'pending'
            WHERE id = %s AND payment_status <> 'paid'
            """,
            (fee, user_id, reg_id)
        )
        if claimed == 1:
            receipt_ok, receipt_msg = send_receipt_email(
                recipient_email=reg['email'],
                participant_name=reg['full_name'],
                event_name=reg['event_name'],
                payment_method='Cash',
                amount_paid=fee,
                utr_number=None,
                registration_uid=reg.get('registration_uid')
            )
            wa_ok, wa_msg, wa_url = send_whatsapp_receipt(
                recipient_phone=reg.get('phone'),
                participant_name=reg['full_name'],
                event_name=reg['event_name'],
                payment_method='Cash',
                amount_paid=fee,
                utr_number=None,
                registration_uid=reg.get('registration_uid')
            )
            if receipt_ok or wa_ok:
                execute_db(
                    "UPDATE registrations SET receipt_sent_at = CURRENT_TIMESTAMP, receipt_delivery_status = 'sent' WHERE id = %s",
                    (reg_id,)
                )
            else:
                execute_db(
                    "UPDATE registrations SET receipt_delivery_status = 'failed' WHERE id = %s",
                    (reg_id,)
                )
                receipt_warning = f'Payment recorded, but receipt delivery failed: {receipt_msg}'
    elif reg['payment_status'] == 'pending':
        # SEC-06: Only administrators may settle pending Online/UTR payments without cash collection
        if session.get('role') != 'admin':
            return jsonify({
                'status': 'error',
                'message': 'Online UTR payment is still pending administrator verification. Ask an admin to verify the UTR or collect cash on spot.'
            }), 403
        claimed = execute_db(
            """
            UPDATE registrations
            SET payment_status = 'paid',
                amount_paid = %s,
                payment_verified_at = CURRENT_TIMESTAMP,
                payment_verified_by = %s,
                status = 'approved',
                receipt_delivery_status = 'pending'
            WHERE id = %s AND COALESCE(payment_status, 'unpaid') <> 'paid'
            """,
            (fee, user_id, reg_id)
        )
        if claimed == 1:
            receipt_ok, receipt_msg = send_receipt_email(
                recipient_email=reg['email'],
                participant_name=reg['full_name'],
                event_name=reg['event_name'],
                payment_method=reg.get('payment_method') or 'Online',
                amount_paid=fee,
                utr_number=reg.get('utr_number'),
                registration_uid=reg.get('registration_uid')
            )
            wa_ok, wa_msg, wa_url = send_whatsapp_receipt(
                recipient_phone=reg.get('phone'),
                participant_name=reg['full_name'],
                event_name=reg['event_name'],
                payment_method=reg.get('payment_method') or 'Online',
                amount_paid=fee,
                utr_number=reg.get('utr_number'),
                registration_uid=reg.get('registration_uid')
            )
            if receipt_ok or wa_ok:
                execute_db(
                    "UPDATE registrations SET receipt_sent_at = CURRENT_TIMESTAMP, receipt_delivery_status = 'sent' WHERE id = %s",
                    (reg_id,)
                )
            else:
                execute_db(
                    "UPDATE registrations SET receipt_delivery_status = 'failed' WHERE id = %s",
                    (reg_id,)
                )
                receipt_warning = f'Payment recorded, but receipt delivery failed: {receipt_msg}'
        
    # Check attendance
    att = query_db("SELECT id FROM attendance WHERE registration_id = %s", (reg_id,), one=True)
    if not att:
        execute_db("INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, 'present', %s)", (reg_id, str(user_id)))
    else:
        execute_db("UPDATE attendance SET status = 'present', marked_by = %s WHERE registration_id = %s", (str(user_id), reg_id))
        
    message = 'Marked as Present and Verified'
    if collect_cash or reg['payment_status'] == 'pay_on_site':
        message = f'Cash payment of ₹{fee} collected & marked as Present'
    if receipt_warning:
        message += f'. {receipt_warning} An administrator can resend the receipt.'
    return jsonify({'status': 'success', 'message': message})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print("=" * 60)
    print("  Shree Daksha Academy – College Event Management System")
    print(f"  Server running on http://0.0.0.0:{port} (Accessible on local network)")
    print("=" * 60)
    app.run(debug=Config.APP_ENV != 'production', host='0.0.0.0', port=port)
