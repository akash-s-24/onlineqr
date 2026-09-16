import time
import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, send_from_directory, send_file, abort, Response
)
import csv
import io
import re
import uuid
import secrets
import hmac
from urllib.parse import quote
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image, UnidentifiedImageError
import qrcode
from config import Config
import database
from database import query_db, execute_db, create_registration
from certificate_generator import generate_certificate, generate_team_certificates_zip
from mailer import send_certificate_email, get_smtp_info, send_receipt_email

app = Flask(__name__)
app.config.from_object(Config)

# Configure upload folders
UPLOAD_FOLDER_QR = os.path.join(app.root_path, 'static', 'uploads', 'qr_codes')
UPLOAD_FOLDER_BANNERS = os.path.join(app.root_path, 'static', 'images')
os.makedirs(UPLOAD_FOLDER_QR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_BANNERS, exist_ok=True)
app.config['UPLOAD_FOLDER_QR'] = UPLOAD_FOLDER_QR
app.config['UPLOAD_FOLDER_BANNERS'] = UPLOAD_FOLDER_BANNERS
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

# Lightweight in-process login throttling keeps repeated credential attacks from
# overwhelming the login endpoint without changing normal authentication flows.
LOGIN_THROTTLE = {}
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


def login_is_throttled(client_key):
    now = time.time()
    attempts = [stamp for stamp in LOGIN_THROTTLE.get(client_key, [])
                if now - stamp < LOGIN_WINDOW_SECONDS]
    LOGIN_THROTTLE[client_key] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def record_login_failure(client_key):
    now = time.time()
    attempts = [stamp for stamp in LOGIN_THROTTLE.get(client_key, [])
                if now - stamp < LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    LOGIN_THROTTLE[client_key] = attempts


def clear_login_failures(client_key):
    LOGIN_THROTTLE.pop(client_key, None)

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

    expected_origin = request.host_url.rstrip('/')
    origin = request.headers.get('Origin', '').rstrip('/')
    referer = request.headers.get('Referer', '')
    if origin and origin != expected_origin:
        abort(400, description='Invalid request origin.')
    if not origin and referer and not referer.startswith(f'{expected_origin}/'):
        abort(400, description='Invalid request origin.')

    submitted_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
    stored_token = session.get('_csrf_token')
    if submitted_token and (not stored_token or not hmac.compare_digest(submitted_token, stored_token)):
        abort(400, description='Invalid security token.')
    if not submitted_token and not app.config.get('TESTING'):
        abort(400, description='Missing security token.')
    return None


@app.after_request
def add_security_headers(response):
    """Add browser-side defenses to every response."""
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "base-uri 'self'; object-src 'none'; form-action 'self'; "
        "img-src 'self' data: https: blob:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "connect-src 'self' https://*.tile.openstreetmap.org https://*.openstreetmap.org; "
        "frame-src 'self' https://maps.google.com https://www.google.com"
    )
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if request.path.startswith(('/admin', '/member', '/login')):
        response.headers['Cache-Control'] = 'no-store'
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
@app.route('/')
def index():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('events_list'))


@app.route('/healthz')
def healthz():
    """Lightweight deployment health check that verifies database reachability."""
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
        if login_is_throttled(client_key):
            flash('Too many unsuccessful attempts. Please try again in a few minutes.', 'warning')
            return render_template('login.html'), 429

        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = query_db(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (identifier, identifier),
            one=True
        )

        if user and user.get('role') in ('admin', 'member') and not Config.ADMIN_PASSWORD and not app.config.get('TESTING'):
            flash('Administrator password configuration is required before sign-in is enabled.', 'danger')
            return render_template('login.html'), 503

        if user and check_password_hash(user['password_hash'], password):
            clear_login_failures(client_key)
            # Rotate the signed session contents after authentication to avoid
            # carrying pre-login session state into the authenticated session.
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['full_name'] = user['full_name']
            session['role'] = user['role']

            flash(f"Welcome back, {user['full_name']}!", 'success')
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('member_dashboard'))
        else:
            record_login_failure(client_key)
            flash('Invalid username or password. Please check your credentials and try again.', 'danger')

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

    # 3. Attendance Counts
    pres_res = query_db("SELECT COUNT(*) as count FROM attendance WHERE status = 'present'", one=True)
    total_present = pres_res['count'] if pres_res else 0

    attendance_rate = round((total_present / total_registrations * 100), 1) if total_registrations > 0 else 0

    # 4. Certificates Generated & Sent
    cert_res = query_db("SELECT COUNT(*) as count FROM certificates", one=True)
    total_certificates = cert_res['count'] if cert_res else 0

    sent_res = query_db("SELECT COUNT(*) as count FROM certificates WHERE email_status = 'sent'", one=True)
    total_sent = sent_res['count'] if sent_res else 0

    # 5. Approved and Pending Counts
    appr_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE status = 'approved'", one=True)
    total_approved = appr_res['count'] if appr_res else 0

    pend_res = query_db("SELECT COUNT(*) as count FROM registrations WHERE status = 'pending'", one=True)
    total_pending = pend_res['count'] if pend_res else 0

    stats = {
        'total_events': total_events,
        'total_participants': total_participants,
        'total_registrations': total_registrations,
        'total_present': total_present,
        'attendance_rate': attendance_rate,
        'total_certificates': total_certificates,
        'total_sent': total_sent,
        'total_approved': total_approved,
        'total_pending': total_pending
    }

    # Pending Registrations
    pending_registrations = query_db("""
        SELECT r.id as registration_id, r.registration_uid, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number,
               p.full_name, p.email, p.college_name, p.department, 
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
        SELECT r.id as registration_id, r.registration_uid, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number,
               p.full_name, p.email, p.college_name, p.department, 
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

    events = query_db("SELECT * FROM events ORDER BY id ASC")
    
    return render_template('admin_dashboard.html', 
                           stats=stats, 
                           pending_registrations=pending_registrations,
                           recent_registrations=recent_registrations,
                           online_approved=online_approved,
                           cash_approved=cash_approved,
                           team_performance=team_performance,
                           events=events)

@app.route('/admin/approve/<int:reg_id>', methods=['POST'])
@admin_required
def approve_registration(reg_id):
    """Approve a pending registration."""
    execute_db("UPDATE registrations SET status = 'approved' WHERE id = %s", (reg_id,))
    flash("Registration has been approved and moved to the completed list.", "success")
    return redirect(request.referrer or url_for('admin_dashboard'))

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
        writer.writerow([
            row['registration_uid'],
            row['full_name'], row['registration_date'], row['team_name'] or 'N/A',
            row['college_name'], row['phone'], row['email'], row['team_size'],
            pay_str, row['amount_paid'], cert_status,
            row['att_status'].upper(), row['approval_status'].upper()
        ])
    
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
               p.full_name, p.email, p.phone, p.college_name, p.department, e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.registered_by = %s
        ORDER BY r.id DESC
    """, (user_id,))
    return render_template('member_dashboard.html', registrations=registrations)

@app.route('/member/payment/<int:reg_id>', methods=['POST'])
@admin_required
def toggle_payment(reg_id):
    """Allow an administrator to verify or correct a payment status."""
    reg = query_db(
        """
        SELECT r.registered_by, r.payment_status, r.status,
               r.payment_method, r.utr_number, e.event_fee
        FROM registrations r
        JOIN events e ON e.id = r.event_id
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

    new_status = 'paid' if reg['payment_status'] != 'paid' else 'unpaid'

    if new_status == 'paid' and safe_int(reg.get('event_fee'), 0) > 0:
        if reg.get('payment_method') == 'Online' and not reg.get('utr_number'):
            flash("Cannot verify an online payment without a UTR / transaction reference.", "warning")
            return redirect(request.referrer or url_for('admin_dashboard'))
    
    # If marking as paid, get the event fee to update amount_paid
    if new_status == 'paid':
        event_info = query_db("SELECT e.event_fee FROM events e JOIN registrations r ON e.id = r.event_id WHERE r.id = %s", (reg_id,), one=True)
        fee = event_info['event_fee'] if event_info else 0
        execute_db("UPDATE registrations SET payment_status = %s, amount_paid = %s WHERE id = %s", (new_status, fee, reg_id))
    else:
        execute_db("UPDATE registrations SET payment_status = %s, amount_paid = 0 WHERE id = %s", (new_status, reg_id))
        
    flash(f"Payment status updated to {new_status.upper()}.", "success")
    return redirect(request.referrer or url_for('member_dashboard'))

# ---------------------------------------------------------
# Event Management Routes
# ---------------------------------------------------------
@app.route('/events')
def events_list():
    events = query_db("SELECT * FROM events ORDER BY id ASC")
    return render_template('events.html', events=events)


@app.route('/events/<int:event_id>/upi-qr')
def event_upi_qr(event_id):
    """Serve a locally generated UPI QR without an external QR dependency."""
    event = query_db(
        "SELECT event_name, event_fee, upi_id FROM events WHERE id = %s",
        (event_id,), one=True
    )
    if not event or safe_int(event.get('event_fee'), 0) <= 0:
        abort(404)

    upi_id = (event.get('upi_id') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
        abort(404)
    payload = (
        f'upi://pay?pa={quote(upi_id)}&pn={quote(Config.EVENT_TITLE)}'
        f'&am={safe_int(event.get("event_fee"), 0)}&cu=INR'
    )
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
        upi_id = request.form.get('upi_id', 'admin@upi').strip()
        rules_text = request.form.get('rules_text', '').strip()
        faculty_name = request.form.get('faculty_name', '').strip()
        faculty_phone = request.form.get('faculty_phone', '').strip()
        student_name = request.form.get('student_name', '').strip()
        student_phone = request.form.get('student_phone', '').strip()

        if not event_name or not event_date or not venue:
            flash('Event name, date, and venue are required.', 'danger')
            return render_template('add_event.html')
        if event_fee > 0 and not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
            flash('Enter a valid UPI ID for paid events.', 'danger')
            return render_template('add_event.html')

        try:
            banner_filename = save_image_upload(
                request.files.get('banner_image'), app.config['UPLOAD_FOLDER_BANNERS']
            )
            qr_filename = save_image_upload(
                request.files.get('qr_code'), app.config['UPLOAD_FOLDER_QR']
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('add_event.html')

        qr_code_image = f"uploads/qr_codes/{qr_filename}" if qr_filename else None

        execute_db(
            """
            INSERT INTO events (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, qr_code_image, banner_image, rules_text, faculty_name, faculty_phone, student_name, student_phone)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, qr_code_image, banner_filename, rules_text, faculty_name, faculty_phone, student_name, student_phone)
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
        upi_id = request.form.get('upi_id', 'admin@upi').strip()
        rules_text = request.form.get('rules_text', '').strip()
        faculty_name = request.form.get('faculty_name', '').strip()
        faculty_phone = request.form.get('faculty_phone', '').strip()
        student_name = request.form.get('student_name', '').strip()
        student_phone = request.form.get('student_phone', '').strip()

        if not event_name or not event_date or not venue:
            flash('Event name, date, and venue are required.', 'danger')
            return render_template('edit_event.html', event=event)
        if event_fee > 0 and not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,100}', upi_id):
            flash('Enter a valid UPI ID for paid events.', 'danger')
            return render_template('edit_event.html', event=event)

        try:
            banner_filename = save_image_upload(
                request.files.get('banner_image'), app.config['UPLOAD_FOLDER_BANNERS']
            )
            qr_filename = save_image_upload(
                request.files.get('qr_code'), app.config['UPLOAD_FOLDER_QR']
            )
        except ValueError as error:
            flash(str(error), 'danger')
            return render_template('edit_event.html', event=event)

        qr_code_image = f"uploads/qr_codes/{qr_filename}" if qr_filename else event.get('qr_code_image')

        if banner_filename and qr_filename:
            execute_db(
                """
                UPDATE events 
                SET event_name = %s, event_type = %s, event_date = %s, event_time = %s, 
                    venue = %s, description = %s, max_participants = %s,
                    is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s, upi_id = %s, qr_code_image = %s, banner_image = %s
                WHERE id = %s
                """,
                (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, qr_code_image, banner_filename, event_id)
            )
        elif banner_filename:
            execute_db(
                """
                UPDATE events
                SET event_name = %s, event_type = %s, event_date = %s, event_time = %s,
                    venue = %s, description = %s, max_participants = %s,
                    is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s, upi_id = %s, banner_image = %s
                WHERE id = %s
                """,
                (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, banner_filename, event_id)
            )
        elif qr_filename:
            execute_db(
                """
                UPDATE events
                SET event_name = %s, event_type = %s, event_date = %s, event_time = %s,
                    venue = %s, description = %s, max_participants = %s,
                    is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s, upi_id = %s, qr_code_image = %s
                WHERE id = %s
                """,
                (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, qr_code_image, event_id)
            )
        else:
            execute_db(
                """
                UPDATE events 
                SET event_name = %s, event_type = %s, event_date = %s, event_time = %s, 
                    venue = %s, description = %s, max_participants = %s,
                    is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s, upi_id = %s
                WHERE id = %s
                """,
                (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, upi_id, event_id)
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
    events = query_db("SELECT * FROM events ORDER BY id ASC")
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
        semester = request.form.get('semester', 'Second PUC').strip()
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
        
        event_fee = max(0, safe_int(ev_record.get('event_fee'), 0))
        payment_status = 'paid' if event_fee == 0 else 'unpaid'
        amount_paid = 0

        if event_fee == 0:
            payment_method = 'None'
            utr_number = None
        elif payment_method == 'Online':
            if not utr_number or not re.fullmatch(r'[A-Z0-9][A-Z0-9._/-]{5,63}', utr_number):
                flash('Enter a valid UPI transaction reference (6–64 letters, numbers, or separators).', 'danger')
                return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
            payment_status = 'pending'
        elif payment_method == 'Cash':
            utr_number = None
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

        if not full_name or not email or not phone or not college_name or not event_id:
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
            registered_by=registered_by,
            is_group_event=is_group_event
        )

        if not registration['ok']:
            reason = registration['reason']
            if reason == 'duplicate_registration':
                flash('You are already registered for this event. Duplicate registration was prevented.', 'warning')
            elif reason == 'duplicate_utr':
                flash('This UPI transaction reference has already been submitted.', 'warning')
            elif reason == 'capacity_reached':
                flash('This event is full. Please choose another event.', 'warning')
            else:
                flash('The selected event is no longer available. Please refresh and try again.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)

        team_info_msg = f" (Team: {team_name} with {team_size} members)" if is_group_event and team_name else ""
        confirmation = 'Registration received and awaiting admin verification.' if payment_status == 'pending' else 'Registration successful.'
        flash(f'{confirmation} Reference: {registration["registration_uid"]}{team_info_msg}', 'success')
        
        # Always redirect to the events list on success so users can keep browsing events
        return redirect(url_for('events_list'))

    return render_template('register.html', events=events, selected_event_id=selected_event_id, user_info=user_info)

# ---------------------------------------------------------
# Participant Management (Admin)
# ---------------------------------------------------------
@app.route('/admin/participants')
@admin_required
def participants_list():
    # Aggregated query fetching participants and their registrations with group details
    participants = query_db("""
        SELECT p.*, 
               GROUP_CONCAT(e.event_name SEPARATOR ', ') as event_names,
               GROUP_CONCAT(COALESCE(r.team_name, '') SEPARATOR ', ') as team_names,
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
               COALESCE(a.status, 'absent') as att_status
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        WHERE r.status = 'approved'
        ORDER BY e.id ASC, p.full_name ASC
    """)
    events = query_db("SELECT * FROM events ORDER BY id ASC")

    present_count = sum(1 for r in attendance_records if r['att_status'] == 'present')
    absent_count = len(attendance_records) - present_count

    return render_template(
        'attendance.html', 
        attendance_records=attendance_records, 
        events=events,
        present_count=present_count,
        absent_count=absent_count
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
@app.route('/verify')
def verify_certificate():
    """Publicly verify a certificate without exposing private participant data."""
    search_id = request.args.get('id', '').strip().upper()
    certificate_info = None
    if search_id:
        certificate_info = query_db(
            """
            SELECT c.certificate_code, c.issue_date,
                   p.full_name, p.college_name, p.department,
                   e.event_name, e.event_date
            FROM certificates c
            JOIN registrations r ON c.registration_id = r.id
            JOIN participants p ON c.participant_id = p.id
            JOIN events e ON c.event_id = e.id
            WHERE c.certificate_code = %s
            """,
            (search_id,),
            one=True
        )

    sample = query_db(
        "SELECT certificate_code FROM certificates ORDER BY id ASC LIMIT 1",
        one=True
    )
    return render_template(
        'verify_certificate.html',
        search_id=search_id,
        certificate_info=certificate_info,
        sample_code=sample['certificate_code'] if sample else None
    )

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
@login_required
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
@login_required
def upload_certificate_template():
    if 'template_image' not in request.files:
        flash('No image file part', 'error')
        return redirect(url_for('certificates_manager'))
    
    file = request.files['template_image']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('certificates_manager'))
        
    if file:
        upload_dir = os.path.join(app.root_path, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        # Always save as certificate_template.png to overwrite
        file_path = os.path.join(upload_dir, 'certificate_template.png')
        
        try:
            # We convert to PNG in case it's a JPEG or other format
            from PIL import Image
            img = Image.open(file)
            img.save(file_path, 'PNG')
            flash('Certificate template uploaded successfully!', 'success')
        except Exception as e:
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
        WHERE r.id = %s AND r.status = 'approved'
    """, (reg_id,), one=True)

    if not reg:
        flash('Registration record not found or not approved.', 'danger')
        return redirect(url_for('certificates_manager'))

    if reg['att_status'] != 'present':
        flash('Cannot generate certificate: Participant attendance is not marked as PRESENT.', 'warning')
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

    flash(f"Certificate of Achievement generated successfully! Certificate ID: {cert_code}", 'success')
    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/generate-bulk', methods=['POST'])
@admin_required
def generate_bulk_certificates():
    # Find all registrations marked present
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
    Emails the payment receipt to the participant.
    """
    reg = query_db("""
        SELECT r.*, p.full_name, p.email, e.event_name
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

    success, msg = send_receipt_email(
        recipient_email=reg['email'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number']
    )
    
    if success:
        flash(msg, 'success')
    else:
        flash(f"Email dispatch error: {msg}", 'danger')
        
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
    mode_text = "Safe Demo Mode" if smtp_info['is_demo'] else "Live SMTP"
    flash(f"Successfully emailed {sent_count} certificate(s) via {mode_text}!", 'success')
    return redirect(url_for('certificates_manager'))

@app.route('/admin/certificates/toggle-mode', methods=['POST'])
@admin_required
def toggle_smtp_mode():
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
# Certificate Verification & Downloads
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

@app.route('/admin/export/csv')
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
            writer.writerow([
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
            ])
        
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": "attachment; filename=all_registrations_backup.csv"}
    )


@app.route('/admin/clear_all', methods=['POST'])
@admin_required
def clear_all_registrations():
    # Only clear tables tracking user registration
    execute_db("DELETE FROM attendance")
    execute_db("DELETE FROM certificates")
    execute_db("DELETE FROM registrations")
    execute_db("DELETE FROM participants")
    flash("All registrations, attendance, and certificates have been permanently cleared.", "success")
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    print("=" * 60)
    print("  EventMate – College Event Management System")
    print("  Server running on http://127.0.0.1:5001")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5001)
