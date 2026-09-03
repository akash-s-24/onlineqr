import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, send_from_directory, abort, Response
)
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
import database
from database import query_db, execute_db
from certificate_generator import generate_certificate
from mailer import send_certificate_email, get_smtp_info, send_receipt_email

app = Flask(__name__)
app.config.from_object(Config)

def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# Ensure required directories exist on app startup
os.makedirs(Config.CERTIFICATE_FOLDER, exist_ok=True)
database.init_db()

# ---------------------------------------------------------
# Context Processors & Decorators
# ---------------------------------------------------------
@app.context_processor
def inject_config():
    return {'config': Config}

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif session.get('role') == 'member':
        return redirect(url_for('member_dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = query_db(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (identifier, identifier),
            one=True
        )

        if user and check_password_hash(user['password_hash'], password):
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

    stats = {
        'total_events': total_events,
        'total_participants': total_participants,
        'total_registrations': total_registrations,
        'total_present': total_present,
        'attendance_rate': attendance_rate,
        'total_certificates': total_certificates,
        'total_sent': total_sent
    }

    # Pending Registrations
    pending_registrations = query_db("""
        SELECT r.id as registration_id, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number,
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
        SELECT r.id as registration_id, r.is_group, r.team_name, r.team_size, r.team_members, r.payment_status, r.amount_paid, r.payment_method, r.utr_number,
               p.full_name, p.email, p.college_name, p.department, 
               e.event_name, a.status as att_status, u.username as registered_by_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        LEFT JOIN attendance a ON a.registration_id = r.id
        LEFT JOIN users u ON r.registered_by = u.id
        WHERE r.status = 'approved'
        ORDER BY r.id DESC
        LIMIT 6
    """)

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
        SELECT r.id, p.full_name, r.registration_date, r.team_name, p.college_name, p.phone, p.email, r.team_size,
               r.payment_status, r.payment_method, r.amount_paid,
               COALESCE(c.certificate_code, 'No') as certificate_id,
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
        'Participant Name', 'Registration Date', 'Team Name', 'College Name', 
        'Phone Number', 'Email ID', 'Total Participants (Team Size)', 
        'Payment Status & Method', 'Amount Paid (INR)', 
        'Signed Certificate', 'Presence on App', 'Approval Status'
    ])
    
    for row in records:
        payment_info = f"Paid - {row['payment_method']}" if row['payment_status'] == 'paid' else "Unpaid"
        cert_info = f"Yes ({row['certificate_id']})" if row['certificate_id'] != 'No' else "No"
        
        writer.writerow([
            row['full_name'],
            row['registration_date'],
            row['team_name'] or '-',
            row['college_name'],
            row['phone'],
            row['email'],
            row['team_size'],
            payment_info,
            row['amount_paid'],
            cert_info,
            row['att_status'].capitalize(),
            row['approval_status'].capitalize()
        ])
    
    response = Response(output.getvalue(), content_type='text/csv')
    response.headers["Content-Disposition"] = f"attachment; filename=participants_{status_filter}.csv"
    return response

# ---------------------------------------------------------
# Member Dashboard
# ---------------------------------------------------------
@app.route('/member/dashboard')
@member_required
def member_dashboard():
    user_id = session.get('user_id')
    registrations = query_db("""
        SELECT r.id as registration_id, r.payment_status, r.amount_paid, r.payment_method, r.team_name, r.status as approval_status, r.utr_number,
               p.full_name, p.email, p.college_name, p.department, e.event_name
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        WHERE r.registered_by = %s
        ORDER BY r.id DESC
    """, (user_id,))
    return render_template('member_dashboard.html', registrations=registrations)

@app.route('/member/payment/<int:reg_id>', methods=['POST'])
@member_required
def toggle_payment(reg_id):
    """Toggle payment status between paid and unpaid."""
    reg = query_db("SELECT registered_by, payment_status, status FROM registrations WHERE id = %s", (reg_id,), one=True)
    if not reg:
        flash("Registration not found.", "danger")
        return redirect(request.referrer or url_for('member_dashboard'))
    
    if session.get('role') != 'admin' and reg['registered_by'] != session.get('user_id'):
        flash("You are not authorized to modify this registration.", "danger")
        return redirect(request.referrer or url_for('member_dashboard'))
        
    if reg['status'] != 'approved':
        flash("Cannot process payments for unapproved registrations.", "warning")
        return redirect(request.referrer or url_for('member_dashboard'))

    new_status = 'paid' if reg['payment_status'] != 'paid' else 'unpaid'
    execute_db("UPDATE registrations SET payment_status = %s WHERE id = %s", (new_status, reg_id))
    flash(f"Payment status updated to {new_status.upper()}.", "success")
    return redirect(request.referrer or url_for('member_dashboard'))

# ---------------------------------------------------------
# Event Management Routes
# ---------------------------------------------------------
@app.route('/events')
def events_list():
    events = query_db("SELECT * FROM events ORDER BY id ASC")
    return render_template('events.html', events=events)

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
        max_participants = safe_int(request.form.get('max_participants', ''), 100)
        is_group = 1 if request.form.get('is_group') in ('1', 'true', 'on') else 0
        min_team_size = safe_int(request.form.get('min_team_size', ''), 1 if is_group == 0 else 2)
        max_team_size = safe_int(request.form.get('max_team_size', ''), 1 if is_group == 0 else 4)
        event_fee = safe_int(request.form.get('event_fee', ''), 0)

        if not event_name or not event_date or not venue:
            flash('Event name, date, and venue are required.', 'danger')
            return render_template('add_event.html')

        execute_db(
            """
            INSERT INTO events (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee)
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
        max_participants = safe_int(request.form.get('max_participants', ''), 100)
        is_group = 1 if request.form.get('is_group') in ('1', 'true', 'on') else 0
        min_team_size = safe_int(request.form.get('min_team_size', ''), 1 if is_group == 0 else 2)
        max_team_size = safe_int(request.form.get('max_team_size', ''), 1 if is_group == 0 else 4)
        event_fee = safe_int(request.form.get('event_fee', ''), 0)

        execute_db(
            """
            UPDATE events 
            SET event_name = %s, event_type = %s, event_date = %s, event_time = %s, 
                venue = %s, description = %s, max_participants = %s,
                is_group = %s, min_team_size = %s, max_team_size = %s, event_fee = %s
            WHERE id = %s
            """,
            (event_name, event_type, event_date, event_time, venue, description, max_participants, is_group, min_team_size, max_team_size, event_fee, event_id)
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
        semester = request.form.get('semester', '5th Sem').strip()
        event_id = request.form.get('event_id', '').strip()

        # Group Event Fields
        team_name = request.form.get('team_name', '').strip() or None
        team_size = safe_int(request.form.get('team_size', ''), 1)
        
        # Payment Tracking
        payment_status = request.form.get('payment_status', 'unpaid').strip()
        payment_method = request.form.get('payment_method', 'None').strip()
        amount_paid = safe_int(request.form.get('amount_paid', '0'), 0)
        utr_number = request.form.get('utr_number', '').strip() or None
        
        if payment_status == 'unpaid':
            payment_method = 'None'
            amount_paid = 0

        registered_by = session.get('user_id') if session.get('role') in ('admin', 'member') else None

        # Check if event is a group event
        ev_record = query_db("SELECT event_name, is_group, min_team_size, max_team_size FROM events WHERE id = %s", (event_id,), one=True) if event_id else None
        if not ev_record:
            flash('Invalid event selected.', 'danger')
            return render_template('register.html', events=events, selected_event_id=event_id, user_info=user_info)
        event_name = ev_record['event_name']
        is_group_event = 1 if (ev_record.get('is_group') == 1) else 0

        # Collect additional team member names
        member_names = []
        if is_group_event:
            for i in range(2, team_size + 1):
                m_name = request.form.get(f'member_{i}_name', '').strip()
                if m_name:
                    member_names.append(m_name)
            # If custom team members textarea provided
            custom_members = request.form.get('team_members', '').strip()
            if custom_members:
                member_names.extend([m.strip() for m in custom_members.split(',') if m.strip()])
            
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

        # 1. Find or create participant record
        participant = query_db("SELECT id FROM participants WHERE email = %s", (email,), one=True)
        user_id = session.get('user_id') if session.get('user_id') else None

        if participant:
            participant_id = participant['id']
            # Update info if provided
            execute_db(
                """
                UPDATE participants 
                SET full_name = %s, phone = %s, college_name = %s, department = %s, semester = %s, user_id = COALESCE(%s, user_id)
                WHERE id = %s
                """,
                (full_name, phone, college_name, department, semester, user_id, participant_id)
            )
        else:
            participant_id = execute_db(
                """
                INSERT INTO participants (user_id, full_name, email, phone, college_name, department, semester)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, full_name, email, phone, college_name, department, semester)
            )

        # 2. Check for Duplicate Registration
        existing_reg = query_db(
            "SELECT id FROM registrations WHERE participant_id = %s AND event_id = %s",
            (participant_id, event_id),
            one=True
        )
        if existing_reg:
            flash(f'Notice: You are already registered for this event! Duplicate registration is prevented.', 'warning')
            return redirect(url_for('events_list'))

        # Determine approval status based on who registered
        registration_status = 'approved' if session.get('role') == 'admin' else 'pending'

        # 3. Create Registration Record with Group Information
        reg_id = execute_db(
            "INSERT INTO registrations (participant_id, event_id, registered_by, is_group, team_name, team_size, team_members, payment_status, status, amount_paid, payment_method, utr_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (participant_id, event_id, registered_by, is_group_event, team_name, team_size, team_members_str, payment_status, registration_status, amount_paid, payment_method, utr_number)
        )

        # 4. Initialize Attendance record as absent
        execute_db(
            "INSERT INTO attendance (registration_id, status, marked_by) VALUES (%s, %s, %s)",
            (reg_id, 'absent', 'system')
        )

        team_info_msg = f" (Team: {team_name} with {team_size} members)" if is_group_event and team_name else ""
        flash(f'Registration successful for {full_name}{team_info_msg}! Your participation pass is confirmed.', 'success')
        
        # Redirect behavior based on login status
        if registered_by:
            return redirect(url_for('member_dashboard') if session.get('role') == 'member' else url_for('admin_dashboard'))
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
@app.route('/admin/certificates')
@admin_required
def certificates_manager():
    cert_list = query_db("""
        SELECT r.id as registration_id, r.is_group, r.team_name, r.team_size, r.team_members,
               p.id as participant_id, p.full_name, p.email, p.college_name, p.department, p.semester,
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
    return render_template('certificates.html', cert_list=cert_list, events=events, smtp_info=smtp_info)

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
        department=reg.get('department') or 'BCA',
        semester=reg.get('semester') or '5th Sem',
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
            department=reg.get('department') or 'BCA',
            semester=reg.get('semester') or '5th Sem',
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
               e.event_name, e.event_date, r.team_name
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
            department=cert.get('department') or 'BCA',
            semester=cert.get('semester') or '5th Sem',
            team_name=cert.get('team_name')
        )
        cert['file_path'] = file_path

    success, msg = send_certificate_email(
        recipient_email=cert['email'],
        participant_name=cert['full_name'],
        event_name=cert['event_name'],
        certificate_path=cert['file_path'],
        certificate_code=cert['certificate_code']
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
                department=cert.get('department') or 'BCA',
                semester=cert.get('semester') or '5th Sem',
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
@app.route('/verify')
def verify_certificate():
    search_id = request.args.get('id', '').strip()
    certificate_info = None

    # Get sample code for quick testing
    sample_cert = query_db("SELECT certificate_code FROM certificates LIMIT 1", one=True)
    sample_code = sample_cert['certificate_code'] if sample_cert else 'EM-2026-BB-62D424'

    if search_id:
        certificate_info = query_db("""
            SELECT c.certificate_code, c.issue_date, c.file_path,
                   p.full_name, p.college_name, p.department, p.semester,
                   e.event_name, e.event_date, e.event_type,
                   r.is_group, r.team_name, r.team_size, r.team_members
            FROM certificates c
            JOIN registrations r ON c.registration_id = r.id
            JOIN participants p ON c.participant_id = p.id
            JOIN events e ON c.event_id = e.id
            WHERE UPPER(c.certificate_code) = UPPER(%s)
        """, (search_id,), one=True)

    return render_template(
        'verify_certificate.html',
        search_id=search_id,
        certificate_info=certificate_info,
        sample_code=sample_code
    )

@app.route('/certificates/<path:filename>')
def download_certificate_file(filename):
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
                department=cert.get('department') or 'BCA',
                semester=cert.get('semester') or '5th Sem',
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
if __name__ == '__main__':
    print("=" * 60)
    print("  EventMate – College Event Management System")
    print("  Server running on http://127.0.0.1:5001")
    print("=" * 60)
    app.run(debug=True, host='127.0.0.1', port=5001)
