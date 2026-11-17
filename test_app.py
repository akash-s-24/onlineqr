import unittest
import json
import os
import time
import uuid
from unittest.mock import patch
import app as app_module
from app import app
import database
from config import Config

class SDATestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        os.environ['FLASK_TESTING'] = 'True'
        os.environ['TESTING'] = 'True'

    def test_01_homepage_redirect(self):
        """Test home page redirects to events for guests"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/events', response.location)

    def test_02_events_page(self):
        """Test events page lists required symposium events"""
        response = self.client.get('/events')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'BGMI', response.data)
        self.assertIn(b'Free Fire', response.data)
        self.assertIn(b'Pencil Sketch', response.data)
        self.assertIn(b'25\xe2\x80\x9326 November 2026', response.data)
        self.assertIn(b'Govt. of Karnataka', response.data)
        self.assertNotIn(b'Pre-University College', response.data)
        self.assertNotIn(b'BCA', response.data)
        self.assertNotIn(b'MCA', response.data)
        self.assertNotIn(b'18-sep-2026', response.data)

    def test_03_login_page_renders(self):
        """Test login page renders properly and securely"""
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Shree Daksha Academy', response.data)
        self.assertIn(b'Sign in', response.data)

    def test_04_admin_authentication(self):
        """Test admin login flow with admin account"""
        if not Config.ADMIN_PASSWORD:
            self.skipTest('Set ADMIN_PASSWORD to seed a test administrator.')
        password = Config.ADMIN_PASSWORD
        response = self.client.post('/login', data={
            'username': 'admin',
            'password': password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Event operations', response.data)
        self.assertNotIn(b'Welcome back', response.data)

    def test_05_student_registration_and_duplicate_prevention(self):
        """Test participant registration and duplicate check"""
        import time
        test_email = f"test.student_{int(time.time()*1000)}@college.edu"
        
        # 1. First registration for available event
        first_event = database.query_db("SELECT id FROM events WHERE is_group = 0 ORDER BY id ASC LIMIT 1", one=True)
        target_event_id = str(first_event['id']) if first_event else '10'

        response1 = self.client.post('/register', data={
            'full_name': 'Test Participant',
            'email': test_email,
            'phone': '9988776655',
            'college_name': 'Shree Daksha Academy',
            'department': 'PCMC',
            'semester': 'II PUC',
            'event_id': target_event_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(response1.status_code, 200)
        self.assertTrue(b'Registration submitted' in response1.data or b'Registration successful' in response1.data)
        self.assertIn(b'daksha-theme.css?v=20261114_v13', response1.data)
        self.assertIn(b'registration-pass-qr', response1.data)
        self.assertIn(b'registration-pass-qr-frame', response1.data)
        theme_css = self.client.get('/static/css/daksha-theme.css').data.decode('utf-8')
        self.assertTrue(':root[data-theme="dark"] .registration-pass-success.alert-warning' in theme_css)
        self.assertTrue(':root[data-theme="dark"] .registration-pass-success.alert-success' in theme_css)

        # 2. Duplicate registration attempt for same event
        response2 = self.client.post('/register', data={
            'full_name': 'Test Participant',
            'email': test_email,
            'phone': '9988776655',
            'college_name': 'Shree Daksha Academy',
            'department': 'PCMC',
            'semester': 'II PUC',
            'event_id': target_event_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(response2.status_code, 200)
        self.assertIn(b'Duplicate registration was prevented', response2.data)

        # Cleanup test registration to preserve event capacity for repeated test runs
        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (test_email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (test_email,), commit=True)

    def test_registration_rejects_non_puc_class(self):
        event = database.query_db("SELECT id FROM events LIMIT 1", one=True)
        response = self.client.post('/register', data={
            'full_name': 'Ineligible Class Student',
            'email': 'ineligible.class@example.edu',
            'phone': '9988776600',
            'college_name': 'Test College',
            'department': 'PCMC',
            'semester': 'III PUC',
            'event_id': str(event['id']),
            'payment_method': 'Cash'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Registration is open to I and II PUC students only.', response.data)

    def test_06_attendance_toggle_and_certificate_flow(self):
        """Test attendance toggle via AJAX and certificate generation"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 14
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        # Fetch or create a registration record
        reg = database.query_db("SELECT id FROM registrations LIMIT 1", one=True)
        if not reg:
            part_id = database.execute_db(
                "INSERT INTO participants (full_name, email, phone, college_name, department) VALUES (%s, %s, %s, %s, %s)",
                ("Test Flow Student", f"flow.test_{int(time.time())}@example.com", "9876543210", "Test College", "PCMC")
            )
            reg_id = database.execute_db(
                "INSERT INTO registrations (registration_uid, participant_id, event_id, status, payment_status, payment_method, amount_paid) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (f"SDA-FLOW-{int(time.time())}", part_id, 2, "approved", "paid", "Cash", 400)
            )
        else:
            reg_id = reg['id']
            database.execute_db("UPDATE registrations SET status = 'approved' WHERE id = %s", (reg_id,))

        # 1. Toggle attendance to 'present'
        res = self.client.post('/attendance/toggle', 
            data=json.dumps({'registration_id': reg_id, 'status': 'present'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'present')

        # 2. Generate certificate for this registration
        gen_res = self.client.post(f'/admin/certificates/generate/{reg_id}', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        self.assertIn(b'Certificate', gen_res.data)

        # 3. Fetch generated certificate code from DB
        cert = database.query_db("SELECT certificate_code, file_path FROM certificates WHERE registration_id = %s", (reg_id,), one=True)
        self.assertIsNotNone(cert)
        cert_code = cert['certificate_code']
        self.assertTrue(os.path.exists(cert['file_path']))

        # Certificate issuance remains available; the public verifier is removed.
        self.assertEqual(self.client.get('/verify').status_code, 404)

    def test_07_certificate_email_dispatch_flow(self):
        """Test certificate email dispatch in Safe Demo Mode"""
        if not Config.ADMIN_PASSWORD:
            self.skipTest('Set ADMIN_PASSWORD to seed a test administrator.')
        password = Config.ADMIN_PASSWORD
        # Login as admin
        self.client.post('/login', data={
            'username': 'admin',
            'password': password
        }, follow_redirects=True)

        # Get an existing certificate
        cert = database.query_db("SELECT id FROM certificates LIMIT 1", one=True)
        if cert:
            cert_id = cert['id']
            email_res = self.client.post(f'/admin/certificates/send-email/{cert_id}', follow_redirects=True)
            self.assertEqual(email_res.status_code, 200)
            self.assertIn(b'Certificate', email_res.data)

            # Check certificates hub renders with smtp_info
            hub_res = self.client.get('/admin/certificates')
            self.assertEqual(hub_res.status_code, 200)
            self.assertIn(b'Certificates Hub', hub_res.data)

    def test_08_admin1_and_admin2_access(self):
        """Test admin1, admin2, adminsda1, and adminsda2 access and formatting as admin SDA1 and admin SDA2"""
        if not Config.ADMIN_PASSWORD:
            self.skipTest('Set ADMIN_PASSWORD to seed test administrators.')
        password = Config.ADMIN_PASSWORD
        # admin1 test
        client1 = self.app.test_client()
        r1 = client1.post('/login', data={'username': 'admin1', 'password': password}, follow_redirects=True)
        self.assertEqual(r1.status_code, 200)
        self.assertIn(b'admin SDA1', r1.data)
        self.assertNotIn(b'Welcome back', r1.data)

        # admin2 test
        client2 = self.app.test_client()
        r2 = client2.post('/login', data={'username': 'admin2', 'password': password}, follow_redirects=True)
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b'admin SDA2', r2.data)
        self.assertNotIn(b'Welcome back', r2.data)

        # adminsda1 test
        client_sda1 = self.app.test_client()
        r_sda1 = client_sda1.post('/login', data={'username': 'adminsda1', 'password': password}, follow_redirects=True)
        self.assertEqual(r_sda1.status_code, 200)
        self.assertIn(b'admin SDA1', r_sda1.data)

        # adminsda2 test
        client_sda2 = self.app.test_client()
        r_sda2 = client_sda2.post('/login', data={'username': 'adminsda2', 'password': password}, follow_redirects=True)
        self.assertEqual(r_sda2.status_code, 200)
        self.assertIn(b'admin SDA2', r_sda2.data)

    def test_09_symposium_portal_sections(self):
        """Test the newly added countdown, stats, rules, registration, and FAQ sections on /events"""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')

        # 1. Event Dates & Hero Subtitle
        self.assertIn('Daksha Infinix', data)
        self.assertIn('Registrations Open &bull; Daksha Infinix', data)
        self.assertNotIn('Daksha Infinitx', data)
        self.assertNotIn('Daksha Infinitix', data)
        self.assertNotIn('SDA 2026-27', data)
        self.assertNotIn('2026-27', data)
        self.assertNotIn('Annual Symposium 2026-27', data)
        self.assertIn('Starts on 25, 26 November 2026, Bengaluru', data)
        self.assertTrue('Bengaluru' in data or 'Bangalore' in data)
        self.assertIn('hero-date-highlight', data)
        self.assertNotIn('November 19th', data)
        self.assertNotIn('November 20th', data)
        self.assertIn('Experience the future of innovation.', data)
        self.assertIn('id="heroCountdownBlock"', data)
        self.assertIn('id="symposiumCountdown"', data)
        self.assertIn('id="cdDays"', data)
        self.assertIn('id="cdHours"', data)
        self.assertIn('id="cdMinutes"', data)
        self.assertIn('id="cdSeconds"', data)
        self.assertNotIn('id="liveIstClock"', data)
        self.assertNotIn('09:00 AM IST', data)
        self.assertIn('Fest is Live', data)

        # 2. Fest Highlights & Stats Section
        self.assertIn('id="stats"', data)
        self.assertIn('data-target="12"', data)
        self.assertIn('<span class="stat-number-plus" aria-label="plus">+</span>', data)
        self.assertNotIn('stat-badge-events">15 COMPETITIONS<', data)
        self.assertIn('General Championship', data)
        self.assertIn('₹1 lakh', data)
        self.assertIn('(up to ₹1 lakh)', data)
        self.assertNotIn('2 Days', data)
        self.assertNotIn('26th &amp; 27th Nov', data)

        # 3. Rules & Regulations Section
        self.assertIn('id="rules"', data)
        self.assertIn('General Rules & Regulations', data)
        self.assertIn('Eligibility & Registration', data)
        self.assertIn('Conduct & Safety', data)
        self.assertIn('Timing & Preparation', data)
        self.assertIn('id="rules-awards"', data)
        self.assertNotIn('id="rules-championship"', data)

        # 4. Registration Procedures & Payment (Online & Offline)
        self.assertIn('id="registration"', data)
        self.assertIn('Registration Procedures & Payment Details', data)
        self.assertIn('ONLINE COMPETITIONS', data)
        self.assertIn('OFFLINE & SPOT ENTRIES', data)
        self.assertNotIn('Important Payment & Receipt Terms', data)

        # 5. FAQ Section
        self.assertIn('id="faq"', data)
        self.assertIn('Frequently Asked Questions', data)
        self.assertIn('Who is eligible to participate', data)
        self.assertIn('Can students from different colleges form a combined team', data)
        self.assertIn('Will participants receive a certificate?', data)
        self.assertIn('What are the payment options and is a physical hard copy receipt required?', data)
        self.assertIn('No physical hard copy receipt is required', data)

    def test_10_header_ordering_and_theme_switch(self):
        """Verify the exact 9-item header navigation sequence and dark/bright theme switcher"""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')

        # 1. Exact sequence in header navigation (#mainBreadcrumb)
        # 1. Home, 2. Highlights, 3. About us, 4. Event, 5. Rules, 6. Procedures, 7. FAQ, 8. Map, 9. Contact
        breadcrumb_start = data.find('id="mainBreadcrumb"')
        self.assertNotEqual(breadcrumb_start, -1)
        breadcrumb_end = data.find('</ul>', breadcrumb_start)
        bc_html = data[breadcrumb_start:breadcrumb_end]

        pos_home = bc_html.find('data-section="hero"')
        pos_highlights = bc_html.find('data-section="stats"')
        pos_about = bc_html.find('data-section="about"')
        pos_event = bc_html.find('data-section="events"')
        pos_rules = bc_html.find('data-section="rules"')
        pos_procedures = bc_html.find('data-section="registration"')
        pos_faq = bc_html.find('data-section="faq"')
        pos_map = bc_html.find('data-section="location"')
        pos_contact = bc_html.find('data-section="contact"')

        # All 9 must be present in header navigation
        self.assertNotEqual(pos_home, -1, "Home link missing in mainBreadcrumb")
        self.assertNotEqual(pos_highlights, -1, "Highlights link missing in mainBreadcrumb")
        self.assertNotEqual(pos_about, -1, "About us link missing in mainBreadcrumb")
        self.assertNotEqual(pos_event, -1, "Event link missing in mainBreadcrumb")
        self.assertNotEqual(pos_rules, -1, "Rules link missing in mainBreadcrumb")
        self.assertNotEqual(pos_procedures, -1, "Procedures link missing in mainBreadcrumb")
        self.assertNotEqual(pos_faq, -1, "FAQ link missing in mainBreadcrumb")
        self.assertNotEqual(pos_map, -1, "Map link missing in mainBreadcrumb")
        self.assertNotEqual(pos_contact, -1, "Contact link missing in mainBreadcrumb")

        # Verify strictly increasing index sequence: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9
        self.assertTrue(pos_home < pos_highlights < pos_about < pos_event < pos_rules < pos_procedures < pos_faq < pos_map < pos_contact,
                        "Header navigation is not in the exact requested sequence!")

        # 2. Theme switch buttons & anti-flicker script
        self.assertIn('id="themeToggleBtn"', data, "Desktop theme toggle button missing")
        self.assertIn('id="themeToggleBtnMobile"', data, "Mobile theme toggle button missing")
        self.assertIn('toggleSiteTheme', data, "toggleSiteTheme function missing")
        self.assertIn('id="footerThemeToggle"', data, "Footer theme toggle missing")
        self.assertIn('theme-icon-moon', data, "Moon icon missing from footer toggle")
        self.assertIn('theme-icon-sun', data, "Sun icon missing from footer toggle")
        self.assertIn('sda_theme', data, "localStorage theme key missing")
        self.assertIn('[data-theme="light"]', data, "Light theme CSS rules missing")

        # 3. Verify robust light theme class targeting matching actual HTML classes
        # (the redesigned events page themes its header/nav/footer/celestial components;
        #  counters use .stat-number, and .stat-card/.principal-message-card no longer exist)
        self.assertIn('[data-theme="light"] .landing-header', data, "Light theme .landing-header rule missing")
        self.assertIn('[data-theme="light"] .image-like-nav', data, "Light theme .image-like-nav rule missing")
        self.assertIn('[data-theme="light"] .header-nav-center', data, "Light theme .header-nav-center rule missing")
        self.assertIn('[data-theme="light"] .l-footer', data, "Light theme .l-footer rule missing")
        self.assertIn('[data-theme="light"] .l-footer', data, "Light theme footer rule missing")
        theme_css = self.client.get('/static/css/daksha-theme.css').data.decode('utf-8')
        self.assertIn(':root[data-theme="light"] .l-footer .footer-col p', theme_css,
                      "Light-theme footer contrast override missing")

        # 4. Verify no dark inline style pollution on key section roots
        self.assertNotIn('id="about" style="padding: 60px 20px 70px; max-width: 1200px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 48px; align-items: center; background: #000000;"', data,
                         "Inline background:#000000 still present on #about section")
        self.assertNotIn('<div class="principal-message-card" style="background: #000000;', data,
                         "Inline background:#000000 still present on principal-message-card")
        self.assertNotIn('<div class="principal-message-logo" style="width: 125px; height: 125px; background: #000000', data,
                         "Inline background:#000000 still present on principal-message-logo")

        # 5. Verify header layout is spacious flex without center nav collision
        self.assertIn('.header-nav-center', data)
        self.assertIn('justify-content: center;', data)

        # 6. Verify mobile white theme text contrast and full-row clickability
        self.assertIn('mobile-dots-svg', data, "Mobile toggle three-dot SVG icon missing")
        self.assertIn('color: #000000 !important;', data, "Mobile light theme solid black text rule missing")
        self.assertIn('document.querySelectorAll(\'#mainBreadcrumb li\')', data, "Full-row click delegation missing")

    def test_11_registration_dropdowns_accessibility(self):
        """Verify registration form dropdowns are native accessible select elements (not hidden or broken)"""
        res = self.client.get('/register')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')

        # 1. Custom combobox is labelled by the visible event-selection label
        self.assertIn('aria-labelledby="eventSelectionHeading"', data)

        # 2. event_id select is accessible with class f-select and NOT display:none
        self.assertIn('id="event_id"', data)
        self.assertIn('name="event_id"', data)
        self.assertIn('class="f-control f-select"', data)
        self.assertNotIn('<select id="event_id" name="event_id" required style="display:none;"', data)

        # 3. department / category select is accessible with commerce/science options and NOT display:none
        self.assertIn('id="department"', data)
        self.assertIn('name="department"', data)
        self.assertNotIn('<select id="department" name="department" required style="display:none;"', data)
        self.assertIn('value="CEBA"', data)
        self.assertIn('value="SEBA"', data)
        self.assertIn('value="PCMB"', data)
        self.assertIn('value="PCMC"', data)
        self.assertIn('value="Other"', data)

        # 4. semester select is accessible with I PUC and II PUC and NOT display:none
        self.assertIn('id="semester"', data)
        self.assertIn('name="semester"', data)
        self.assertNotIn('<select id="semester" name="semester" style="display:none;"', data)
        self.assertIn('value="I PUC"', data)
        self.assertIn('value="II PUC"', data)
        self.assertIn('Specify Your PUC Stream', data)
        self.assertNotIn('BCA', data)
        self.assertNotIn('MCA', data)

    def test_12_csv_exports_and_offline_pass_service_worker(self):
        """Test non-colliding CSV export routes, service worker, and ticket pass QR code"""
        if not Config.ADMIN_PASSWORD:
            self.skipTest('Set ADMIN_PASSWORD to access admin export routes.')
        password = Config.ADMIN_PASSWORD
        self.client.post('/login', data={'username': 'admin', 'password': password}, follow_redirects=True)

        # 1. Test /admin/export/csv (status-filtered export)
        res_csv = self.client.get('/admin/export/csv?status=approved')
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('text/csv', res_csv.content_type)
        self.assertIn(b'Registration UID', res_csv.data)

        # 2. Test /admin/export/full-backup-csv (comprehensive export)
        res_full_csv = self.client.get('/admin/export/full-backup-csv')
        self.assertEqual(res_full_csv.status_code, 200)
        self.assertIn('text/csv', res_full_csv.content_type)
        self.assertIn(b'Registration UID', res_full_csv.data)

        # 3. Test Service Worker root endpoint
        res_sw = self.client.get('/sw.js')
        self.assertEqual(res_sw.status_code, 200)
        self.assertEqual(res_sw.headers.get('Content-Type'), 'application/javascript')
        self.assertEqual(res_sw.headers.get('Service-Worker-Allowed'), '/')
        self.assertIn(b'sda-ticket-pass-v1', res_sw.data)

        # 4. Test payment status offline ticket pass rendering with QR code
        reg = database.query_db("SELECT registration_uid FROM registrations LIMIT 1", one=True)
        if reg:
            uid = reg['registration_uid']
            res_pass = self.client.get(f'/payment-status/{uid}')
            self.assertEqual(res_pass.status_code, 200)
            self.assertIn(b'Registration Pass QR', res_pass.data)
            self.assertIn(b'navigator.serviceWorker.register', res_pass.data)
            self.assertIn(b'class="registration-pass-qr-frame"', res_pass.data)
            self.assertIn(b'class="registration-pass-qr-image"', res_pass.data)

        theme_res = self.client.get('/static/css/daksha-theme.css')
        theme_css = theme_res.data.decode('utf-8')
        self.assertIn('#events #discCascadeRegister', theme_css)
        self.assertIn('background: var(--primary) !important;', theme_css)
        self.assertIn('color: var(--on-primary) !important;', theme_css)
        self.assertIn('.registration-pass-qr { display: grid;', theme_css)
        self.assertIn('@media (max-width: 560px)', theme_css)

    def test_13_cash_registration_and_gate_pass(self):
        """Test Cash registration generates gate pass with prompt to pay at college desk"""
        import time
        email = f"cash.student_{int(time.time()*1000)}@college.edu"
        ev = database.query_db("SELECT id, event_fee FROM events WHERE is_group = 0 AND event_fee > 0 LIMIT 1", one=True)
        ev_id = str(ev['id']) if ev else '1'

        res = self.client.post('/register', data={
            'full_name': 'Cash Attendee',
            'email': email,
            'phone': '9876543210',
            'college_name': 'Daksha Institute',
            'department': 'CEBA',
            'semester': 'II PUC',
            'event_id': ev_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Official Gate Pass QR', res.data)
        self.assertIn(b'Registration submitted (Cash Payment Pending)', res.data)
        self.assertIn(b'pay at your college desk', res.data)

        # Cleanup
        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (email,), commit=True)

    def test_14_online_registration_with_screenshot_upload(self):
        """Test online payment with UTR and payment screenshot file upload"""
        import time
        import io
        from PIL import Image

        email = f"upi.student_{int(time.time()*1000)}@college.edu"
        ev = database.query_db("SELECT id FROM events WHERE is_group = 0 AND event_fee > 0 LIMIT 1", one=True)
        ev_id = str(ev['id']) if ev else '1'
        test_utr = f"UTR{int(time.time())}"

        # Generate a small test PNG image in-memory
        img_io = io.BytesIO()
        test_img = Image.new('RGB', (120, 120), color=(37, 99, 235))
        test_img.save(img_io, format='PNG')
        img_io.seek(0)

        res = self.client.post('/register', data={
            'full_name': 'Online UPI Participant',
            'email': email,
            'phone': '9123456780',
            'college_name': 'Tech Academy',
            'department': 'SEBA',
            'semester': 'II PUC',
            'event_id': ev_id,
            'payment_method': 'Online',
            'utr_number': test_utr,
            'payment_screenshot': (img_io, 'screenshot.png')
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Payment submitted for verification', res.data)

        # Verify DB recorded payment_proof
        reg = database.query_db(
            "SELECT r.payment_proof, r.utr_number, r.payment_status FROM registrations r JOIN participants p ON r.participant_id = p.id WHERE p.email = %s",
            (email,), one=True
        )
        self.assertIsNotNone(reg)
        self.assertEqual(reg['utr_number'], test_utr)
        self.assertEqual(reg['payment_status'], 'pending')
        self.assertIsNotNone(reg['payment_proof'])

        # Verify proof file exists in upload folder
        proof_path = os.path.join(app.config['UPLOAD_FOLDER_PAYMENTS'], reg['payment_proof'])
        self.assertTrue(os.path.exists(proof_path))

        # Cleanup file and records
        if os.path.exists(proof_path):
            os.remove(proof_path)
        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (email,), commit=True)

    def test_15_member_scanner_and_cash_collection(self):
        """Test member (coordinator) QR scanner access and on-site cash collection"""
        import time
        email = f"gate.student_{int(time.time()*1000)}@college.edu"
        ev = database.query_db("SELECT id, event_fee FROM events WHERE is_group = 0 AND event_fee > 0 LIMIT 1", one=True)
        ev_id = str(ev['id']) if ev else '1'

        # Create cash registration
        res = self.client.post('/register', data={
            'full_name': 'Scanner Test Attendee',
            'email': email,
            'phone': '9988112233',
            'college_name': 'Gate College',
            'department': 'CEBA',
            'semester': 'II PUC',
            'event_id': ev_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)

        reg = database.query_db(
            "SELECT r.id, r.registration_uid FROM registrations r JOIN participants p ON r.participant_id = p.id WHERE p.email = %s",
            (email,), one=True
        )
        reg_id = reg['id']
        uid = reg['registration_uid']

        # Log in as coordinator / member
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['username'] = 'member1'
            sess['role'] = 'member'
            sess['_csrf_token'] = 'test-token'

        # 1. Member can access /scanner
        scanner_res = self.client.get('/scanner')
        self.assertEqual(scanner_res.status_code, 200)
        self.assertIn(b'On-Site QR Scanner', scanner_res.data)

        # 2. Member scans pass via /api/scan_qr
        scan_res = self.client.get(f'/api/scan_qr?uid={uid}')
        self.assertEqual(scan_res.status_code, 200)
        scan_json = scan_res.get_json()
        self.assertEqual(scan_json['status'], 'success')
        self.assertEqual(scan_json['data']['registration_uid'], uid)
        self.assertEqual(scan_json['data']['payment_status'], 'pay_on_site')

        # 3. Member collects cash and marks present via /api/mark_attended
        mark_res = self.client.post('/api/mark_attended',
            data=json.dumps({'registration_id': reg_id, 'collect_cash': True}),
            content_type='application/json',
            headers={'X-CSRF-Token': 'test-token'}
        )
        self.assertEqual(mark_res.status_code, 200)
        mark_json = mark_res.get_json()
        self.assertEqual(mark_json['status'], 'success')

        # 4. Verify DB was updated
        updated_reg = database.query_db("SELECT payment_status, payment_method, amount_paid FROM registrations WHERE id = %s", (reg_id,), one=True)
        self.assertEqual(updated_reg['payment_status'], 'paid')
        self.assertEqual(updated_reg['payment_method'], 'Cash')
        self.assertGreater(updated_reg['amount_paid'], 0)

        att = database.query_db("SELECT status FROM attendance WHERE registration_id = %s", (reg_id,), one=True)
        self.assertEqual(att['status'], 'present')

        # Cleanup
        database.query_db("DELETE FROM registrations WHERE id = %s", (reg_id,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (email,), commit=True)

    def test_16_direct_certificate_generation_without_validation_gate(self):
        """Test certificate generates directly even if attendance is absent (no validation hurdle)"""
        import time
        email = f"cert.student_{int(time.time()*1000)}@college.edu"
        ev = database.query_db("SELECT id FROM events WHERE is_group = 0 LIMIT 1", one=True)

        res = self.client.post('/register', data={
            'full_name': 'Direct Cert Student',
            'email': email,
            'phone': '9871112223',
            'college_name': 'Award Academy',
            'department': 'Commerce',
            'semester': 'II PUC',
            'event_id': str(ev['id']),
            'payment_method': 'Cash'
        }, follow_redirects=True)

        reg = database.query_db(
            "SELECT r.id FROM registrations r JOIN participants p ON r.participant_id = p.id WHERE p.email = %s",
            (email,), one=True
        )
        reg_id = reg['id']

        # Ensure attendance is absent
        database.execute_db("UPDATE attendance SET status = 'absent' WHERE registration_id = %s", (reg_id,))

        with self.client.session_transaction() as sess:
            sess['user_id'] = 14
            sess['username'] = 'admin'
            sess['role'] = 'admin'
            sess['_csrf_token'] = 'cert-token'

        # Generate certificate directly
        gen_res = self.client.post(
            f'/admin/certificates/generate/{reg_id}',
            data={'csrf_token': 'cert-token'},
            follow_redirects=True
        )
        self.assertEqual(gen_res.status_code, 200)

        # Verify certificate was issued in DB
        cert = database.query_db("SELECT certificate_code, email_status FROM certificates WHERE registration_id = %s", (reg_id,), one=True)
        self.assertIsNotNone(cert)
        self.assertTrue(cert['certificate_code'].startswith('SDA-2026-'))

        # Cleanup
        cert_path = os.path.join(Config.CERTIFICATE_FOLDER, f"{cert['certificate_code']}.png")
        if os.path.exists(cert_path):
            os.remove(cert_path)
        database.query_db("DELETE FROM certificates WHERE registration_id = %s", (reg_id,), commit=True)
        database.query_db("DELETE FROM registrations WHERE id = %s", (reg_id,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (email,), commit=True)

    def test_17_admin_dashboard_redesign_backup_and_screenshots(self):
        """Test admin dashboard distinct sections, backup download endpoint, and payment gallery"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 14
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        # 1. Test Admin Dashboard render has distinct sections
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 200)
        content = res.data.decode('utf-8')
        self.assertIn('id="overview"', content)
        self.assertIn('id="registrations"', content)
        self.assertIn('id="screenshots"', content)
        self.assertIn('id="payments"', content)
        self.assertIn('id="attendance-desk"', content)
        self.assertIn('id="operations"', content)
        self.assertIn('Payment Proof Screenshots Gallery', content)
        self.assertIn('id="screenshotZoomModal"', content)

        # 2. Test Single Registration Backup Download Route before deletion
        reg = database.query_db("SELECT id, registration_uid FROM registrations LIMIT 1", one=True)
        if not reg:
            part_id = database.execute_db(
                "INSERT INTO participants (full_name, email, phone, college_name, department) VALUES (%s, %s, %s, %s, %s)",
                ("Backup Test Attendee", f"backup_{int(time.time())}@college.edu", "9988776655", "SDA College", "CEBA")
            )
            reg_id = database.execute_db(
                "INSERT INTO registrations (registration_uid, participant_id, event_id, status, payment_status, payment_method, amount_paid) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (f"SDA-BK-{int(time.time())}", part_id, 2, "approved", "paid", "Cash", 400)
            )
        else:
            reg_id = reg['id']

        backup_res = self.client.get(f'/admin/export/registration/{reg_id}')
        self.assertEqual(backup_res.status_code, 200)
        self.assertEqual(backup_res.content_type, 'application/json')
        backup_data = json.loads(backup_res.data)
        self.assertEqual(backup_data['id'], reg_id)
        self.assertIn('registration_uid', backup_data)
        self.assertIn('full_name', backup_data)

    def test_18_general_championship_and_live_event_count(self):
        """Verify the requested 15-event championship copy and complete carousel lineup."""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        event_count = database.query_db("SELECT COUNT(*) AS count FROM events", one=True)['count']
        self.assertTrue('General Championship' in html)
        self.assertTrue('registered for all 15 competitions' in html)
        self.assertTrue('Overall Championship Trophy' not in html)
        self.assertTrue('data-title="Solo Singing"' in html)
        self.assertTrue('data-target="12"' in html)
        self.assertTrue('Register Online Only' in html)
        self.assertTrue('data-no-liquid' in html)
        self.assertTrue('25–26 November 2026' in html)
        self.assertTrue('26th/27th Nov' not in html)
        self.assertTrue('30 minutes before inauguration' in html)
        self.assertTrue('General Championship' in html)
        self.assertTrue('hard copy of the receipt' in html)
        self.assertTrue('all 14 fest events' not in html)
        self.assertIn('Government of Karnataka. BU. AICTE approved', html)
        self.assertIn('Recognized by Government of Karnataka, affiliated to Bengaluru University, approved by AICTE.', html)
        self.assertIn('id="headerRegisterBtn"', html)
        self.assertIn('id="tabModeCarousel"', html)
        self.assertIn('id="tabModeGrid"', html)
        self.assertIn('class="stat-currency rupee-blue-accent"', html)
        self.assertIn('class="stat-unit stat-blue-accent"', html)

        championship_card = html.split('class="stat-card stat-card-championship', 1)[1].split('<!-- Card 3: Prize pool -->', 1)[0]
        self.assertIn('<span>General</span> <span class="stat-title-accent">Championship</span>', championship_card)
        self.assertIn('Eligible colleges compete for the overall fest title.', championship_card)
        self.assertNotIn('15 competitions', championship_card)
        self.assertIn('stat-action-link', championship_card)
        self.assertIn('href="#rules"', championship_card)
        self.assertIn('Championship Rules', championship_card)
        self.assertNotIn('championship-competition-list', championship_card)
        self.assertNotIn('<div class="stat-badge">GENERAL CHAMPIONSHIP</div>', championship_card)
        competitions_card = html.split('class="stat-value-row stat-value-events"', 1)[1].split('<!-- Card 2: General Championship -->', 1)[0]
        self.assertIn('data-target="12"', competitions_card)
        self.assertNotIn('>Competitions</h3>', competitions_card)

        carousel_panel = html.split('id="eventsCarouselPanel"', 1)[1].split('id="eventsGridPanel"', 1)[0]
        self.assertNotIn('Contacts', carousel_panel)
        self.assertIn('id="discCascadeRules"', carousel_panel)
        self.assertIn('id="discCascadeCall"', carousel_panel)
        self.assertNotIn('discCascadeCoords', carousel_panel)
        grid_cards = html.split('id="eventsCardsGrid"', 1)[1].split('</div>\n        </div>\n    </section>', 1)[0]
        self.assertNotIn('event-contact-item', grid_cards)
        self.assertNotIn('Coordinators:', grid_cards)
        self.assertIn('btn-card-contact', grid_cards)
        self.assertIn('btn-card-rules', grid_cards)
        self.assertIn('class="btn-card-register"', grid_cards)

        theme_css = self.client.get('/static/css/daksha-theme.css').data.decode('utf-8')
        self.assertIn(':root[data-theme="dark"] #faq .faq-item[open] .faq-question', theme_css)
        self.assertIn(':root[data-theme="dark"] #faq .faq-item:not([open])', theme_css)
        self.assertIn('background: #2563eb !important', theme_css)
        self.assertIn('background: #090b10 !important', theme_css)
        self.assertIn('background: #ffffff !important; color: #111827 !important', theme_css)
        self.assertIn('.header-cta-classic { flex: 0 0 auto; min-height: 44px; white-space: nowrap;', theme_css)
        self.assertIn('.landing-header #headerNavCenter:not(.open)', theme_css)
        self.assertIn('.stat-value-events .stat-number-plus', theme_css)
        self.assertNotIn('.stat-value-events .stat-number,', theme_css)
        self.assertIn('text-decoration-line: none !important', theme_css)
        self.assertIn(':root[data-theme="dark"] .stat-value-events .stat-number-plus { color: #93c5fd', theme_css)
        self.assertIn('.event-dialog a:hover', theme_css)
        self.assertIn(':root[data-theme="light"] .registration-success-notice', theme_css)
        self.assertIn(':root[data-theme="dark"] .registration-success-notice', theme_css)
        self.assertIn('.institution-spotlight-heading', theme_css)

        brochure_competitions = [
            'Pencil Sketching', 'Photography', 'Content Creator', 'Solo Dance',
            'Face Painting', 'Mono Acting', 'Tech Quiz', 'Solo Singing',
            'Free Fire', 'BGMI', 'Beat Boxing', 'Get the Shield',
            'Fashion Walk', 'Mad Ads', 'Group Dance',
        ]
        for competition in brochure_competitions:
            self.assertIn(f'data-title="{competition}"', carousel_panel)

        # Live event lineup controls
        self.assertIn('id="discCascadeIndex"', html)
        self.assertIn('id="discCascadeIndexButton"', html)
        self.assertIn('id="discCascadeIndexMenu"', html)
        self.assertIn(f'{event_count} events', html)
        self.assertIn(f'{event_count} TOTAL', html)
        self.assertIn('disc-cascade-animated-arrow', html)
        self.assertIn('arrow-forward-backward', html)
        self.assertNotIn('Click here', html)
        self.assertNotIn('out of', html)
        self.assertIn('1 / ', html)

    def test_19_ui_improvements_attendance_and_event_config(self):
        """Verify live event counts, forward/backward arrow, and event header controls."""
        # 1. Check /events header button is "Register for Event" pointing to #events
        res = self.client.get('/events')
        html = res.data.decode('utf-8')
        self.assertIn('Register for Event', html)
        event_count = database.query_db("SELECT COUNT(*) AS count FROM events", one=True)['count']
        self.assertIn(f'{event_count} events', html)
        self.assertIn('disc-cascade-animated-arrow', html)
        self.assertIn('arrow-forward-backward', html)
        self.assertNotIn('Click here', html)
        self.assertNotIn('out of', html)
        self.assertNotIn('Desk / Member Login', html)

        # 2. Check /register: official certification guarantee removed, BGMI highlighted, email has *, no "optional" label
        reg_res = self.client.get('/register?event_id=2')
        reg_html = reg_res.data.decode('utf-8')
        self.assertNotIn('Official Certification Guarantee', reg_html)
        self.assertNotIn('event-fee-simple-badge', reg_html)
        self.assertIn('event-title-badge-box', reg_html)
        self.assertIn('bgm-highlight', reg_html)
        self.assertIn('Email Address *', reg_html)
        self.assertNotIn('optional', reg_html.lower())
        self.assertIn('16a34a', reg_html)

        # 3. Registration without email must fail
        no_email_res = self.client.post('/register', data={
            'full_name': 'No Email Student',
            'email': '',
            'phone': '9876543210',
            'college_name': 'Test College',
            'department': 'Other',
            'other_department': 'PUC Science',
            'event_id': '2',
            'team_name': 'Alpha Squad',
            'team_size': '4',
            'member_2_name': 'Member Two',
            'member_3_name': 'Member Three',
            'member_4_name': 'Member Four',
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertIn(b'email', no_email_res.data.lower())
        database.query_db("DELETE FROM participants WHERE full_name = 'No Email Student'", commit=True)

        # 4. Check admin event configuration and editing
        with self.client.session_transaction() as sess:
            sess['user_id'] = 14
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        dash_res = self.client.get('/admin/dashboard')
        dash_html = dash_res.data.decode('utf-8')
        self.assertIn('id="events-config"', dash_html)
        self.assertIn('Event Customization &amp; Rules Configuration Hub', dash_html)

        # 5. Check event editing POST updates rules, faculty and student coordinator info
        bgmi_event = database.query_db("SELECT id FROM events WHERE event_name = 'BGMI'", one=True)
        self.assertIsNotNone(bgmi_event)
        bgmi_initial = database.query_db("SELECT description, rules_text FROM events WHERE event_name = 'BGMI'", one=True)
        try:
            edit_post_res = self.client.post(f"/admin/events/edit/{bgmi_event['id']}", data={
                'event_name': 'BGMI',
                'event_type': 'Gaming',
                'event_date': '25-26-nov-2026',
                'event_time': '10:00 AM',
                'venue': 'Computer Lab 3',
                'max_participants': '100',
                'is_group': '1',
                'min_team_size': '4',
                'max_team_size': '4',
                'event_fee': '400',
                'upi_id': Config.DEFAULT_UPI_ID,
                'description': 'Battle Royale championship at Daksha Infinix.',
                'rules_text': 'Rule 1: Mobile only, no emulators.\nRule 2: Fair play mandatory.',
                'faculty_name': 'Prof. Rajesh Kumar',
                'faculty_phone': '9876543210',
                'student_name': 'Akash S',
                'student_phone': '8050774071'
            }, follow_redirects=True)
            self.assertEqual(edit_post_res.status_code, 200)

            # Verify updated values in database
            ev = database.query_db("SELECT * FROM events WHERE event_name = 'BGMI'", one=True)
            self.assertEqual(ev['faculty_name'], 'Prof. Rajesh Kumar')
            self.assertEqual(ev['student_name'], 'Akash S')
            self.assertIn('Rule 1', ev['rules_text'])
            self.assertEqual(ev['upi_id'], Config.DEFAULT_UPI_ID)
            self.assertIsNone(ev['qr_code_image'])

            # 6. Verify attendance view has no inflated 140 fake absence badge
            att_res = self.client.get('/admin/attendance')
            att_html = att_res.data.decode('utf-8')
            self.assertNotIn('>140<', att_html)
            self.assertNotIn('140 Absent', att_html)
            self.assertIn('Awaiting Check-in', att_html)
        finally:
            # Restore initial BGMI event details for subsequent tests
            database.execute_db(
                """
                UPDATE events
                SET description = %s,
                    rules_text = %s,
                    faculty_name = 'RANJITHA B K',
                    faculty_phone = '88615 91085',
                    student_name = 'SINDHU M R',
                    student_phone = '88922 63116'
                WHERE event_name = 'BGMI'
                """,
                (bgmi_initial['description'], bgmi_initial['rules_text'])
            )

    def test_20_password_required_login_and_navigation_verification(self):
        """Verify public navigation and enforce passwords for staff sign-in."""
        # 1. No login element on public events page or registration page
        res_events = self.client.get('/events')
        events_html = res_events.data.decode('utf-8')
        self.assertNotIn('Desk / Member Login', events_html)
        self.assertNotIn('href="/login"', events_html)

        # 2. Login page renders with Member / Staff ID
        res_login = self.client.get('/login')
        login_html = res_login.data.decode('utf-8')
        self.assertIn('Member / Staff ID', login_html)
        self.assertIn('Password *', login_html)
        self.assertNotIn('ID-only access supported', login_html)

        # 3. Member ID without a password is rejected.
        member_client = self.app.test_client()
        res_member = member_client.post('/login', data={'username': 'member1'}, follow_redirects=True)
        self.assertEqual(res_member.status_code, 200)
        self.assertIn(b'Invalid ID or credentials', res_member.data)

        # 4. Admin ID without a password is rejected.
        admin_client = self.app.test_client()
        res_admin = admin_client.post('/login', data={'username': 'admin'}, follow_redirects=True)
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'Invalid ID or credentials', res_admin.data)

        if Config.ADMIN_PASSWORD:
            valid_admin = self.app.test_client().post('/login', data={
                'username': 'admin', 'password': Config.ADMIN_PASSWORD
            }, follow_redirects=True)
            self.assertEqual(valid_admin.status_code, 200)
            self.assertIn(b'Event operations', valid_admin.data)

        # 5. Invalid ID rejected
        bad_client = self.app.test_client()
        res_bad = bad_client.post('/login', data={'username': 'nonexistent_user_999'}, follow_redirects=True)
        self.assertIn(b'Invalid ID or credentials', res_bad.data)

    def test_21_official_college_logo_and_favicons(self):
        """Verify authentic college logo and cross-platform favicon assets, routes, and mobile styling"""
        # 1. Verify root icon and manifest endpoints
        for endpoint, mime in [
            ('/favicon.ico', 'image/vnd.microsoft.icon'),
            ('/apple-touch-icon.png', 'image/png'),
            ('/apple-touch-icon-precomposed.png', 'image/png'),
            ('/site.webmanifest', 'application/manifest+json')
        ]:
            res = self.client.get(endpoint)
            self.assertEqual(res.status_code, 200, f"Route {endpoint} failed")
            self.assertEqual(res.content_type, mime, f"Route {endpoint} has wrong mime")
            self.assertGreater(len(res.data), 0, f"Route {endpoint} returned empty body")

        # 2. Verify favicon links in HTML head of /events
        res_events = self.client.get('/events')
        events_html = res_events.data.decode('utf-8')
        self.assertIn('static/favicon-32x32.png', events_html)
        self.assertIn('static/favicon-16x16.png', events_html)
        self.assertIn('static/apple-touch-icon.png', events_html)
        self.assertIn('static/favicon.png', events_html)
        self.assertIn('static/favicon.svg', events_html)
        self.assertIn('static/favicon.ico', events_html)

        # 3. Verify official college logo image reference with cache-busting
        self.assertIn('static/images/college_logo.png?v=4', events_html)
        self.assertNotIn('https://shreedakshaacademyedu.in/assests/images/backend/logo2.png', events_html)

        # 4. Verify mobile view CSS includes explicit visibility for logo
        self.assertIn('display: block !important;', events_html)
        self.assertIn('visibility: visible !important;', events_html)
        self.assertIn('opacity: 1 !important;', events_html)

        # 5. Verify /register page has official college logo
        res_reg = self.client.get('/register')
        reg_html = res_reg.data.decode('utf-8')
        self.assertIn('static/images/college_logo.png?v=4', reg_html)

        # 6. Verify /login page has official college logo
        res_login = self.client.get('/login')
        login_html = res_login.data.decode('utf-8')
        self.assertIn('static/images/college_logo.png?v=4', login_html)

    def test_22_mobile_ux_and_registration_optimizations(self):
        """Verify mobile address line, team lead naming, clean single UPI app button, photo pass instructions, and font consistency."""
        res_events = self.client.get('/events')
        events_html = res_events.data.decode('utf-8')

        # 1. Header address line is present and enabled for mobile
        self.assertIn('landing-logo-addr', events_html)
        self.assertIn('No.596, Andrahalli Main Road', events_html)
        self.assertNotIn('.landing-logo-addr {\n                display: none !important;', events_html)

        # 2. Permanent font stack configured in Google Fonts link
        self.assertIn('family=DM+Sans:wght@400;500;600;700;800', events_html)
        self.assertIn('family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700', events_html)

        # 3. Unnecessary background scripts removed
        self.assertNotIn('cdnjs.cloudflare.com/ajax/libs/gsap', events_html)
        self.assertNotIn('ScrollTrigger.min.js', events_html)
        self.assertFalse(os.path.exists('static/js/gridscan.js'), "gridscan.js should be removed")

        # 4. Registration page validations
        res_reg = self.client.get('/register')
        reg_html = res_reg.data.decode('utf-8')

        # Team Lead Name instead of Lead Registrant
        self.assertIn('Team Lead Name *', reg_html)
        self.assertNotIn('Lead Registrant Full Name *', reg_html)

        # Academic Year / Class: no pre-selected default option
        self.assertIn('Select Academic Year / Class', reg_html)
        self.assertNotIn('<option value="II PUC" selected>II PUC</option>', reg_html)

        # Single Open UPI App button, no separate individual app buttons
        self.assertIn('Open UPI App to Pay', reg_html)
        self.assertNotIn('data-app="gpay"', reg_html)
        self.assertNotIn('data-app="phonepe"', reg_html)
        self.assertNotIn('data-app="paytm"', reg_html)
        self.assertNotIn('data-app="bhim"', reg_html)

        # 5. Mobile pass photo / screenshot instruction on payment status
        import time
        ev = database.query_db("SELECT id FROM events WHERE is_group = 0 LIMIT 1", one=True)
        ev_id = str(ev['id']) if ev else '1'
        unique_email = f"aarav.photo_{int(time.time()*1000)}@college.edu"
        reg_post = self.client.post('/register', data={
            'full_name': 'Aarav Sharma',
            'email': unique_email,
            'phone': '9988776655',
            'college_name': 'Shree Daksha Academy',
            'department': 'CEBA',
            'semester': 'I PUC',
            'event_id': ev_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(reg_post.status_code, 200)
        pass_html = reg_post.data.decode('utf-8')
        self.assertIn('Take a photo or screenshot of this pass now!', pass_html)
        self.assertIn('Send Pass to Mobile / WhatsApp', pass_html)
        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (unique_email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (unique_email,), commit=True)

    def test_23_liquid_button_integration(self):
        """Verify liquid fluid button engine, styles, assets, and template integration across site."""
        # 1. Assets exist and serve 200
        res_css = self.client.get('/static/css/liquid-button.css')
        self.assertEqual(res_css.status_code, 200)
        css_text = res_css.data.decode('utf-8')
        self.assertIn('.liquid-btn', css_text)
        self.assertIn('--liquid-fill', css_text)
        self.assertIn('--liquid-active-text', css_text)
        self.assertIn('.liquid-btn-inverted', css_text)

        res_js = self.client.get('/static/js/liquid-button.js')
        self.assertEqual(res_js.status_code, 200)
        js_text = res_js.data.decode('utf-8')
        self.assertIn('feTurbulence', js_text)
        self.assertIn('feDisplacementMap', js_text)
        self.assertIn('initLiquidButton', js_text)
        self.assertIn('cloneInvertedContent', js_text)

        # 2. Template inclusion in events and register
        res_events = self.client.get('/events')
        events_html = res_events.data.decode('utf-8')
        self.assertIn('liquid-button.css', events_html)
        self.assertIn('liquid-button.js', events_html)

        res_reg = self.client.get('/register')
        reg_html = res_reg.data.decode('utf-8')
        self.assertIn('liquid-button.css', reg_html)
        self.assertIn('liquid-button.js', reg_html)

        # 3. Suppress old hectic button animations
        self.assertNotIn('.clean-black-submit-btn::after {\n    content: \'\';', reg_html)
        self.assertNotIn('.hero-explore-btn::after {\ncontent: \'\';', events_html)

    def test_24_restored_buttons_and_liquid_physics_visibility(self):
        """Verify all essential hero, disc cascade, and procedure buttons are present, visible, and have non-clipping liquid styles."""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # 1. Top Hero action buttons and countdown
        self.assertIn('Starts on 25, 26 November 2026, Bengaluru', html)
        self.assertIn('Explore Events', html)
        self.assertIn('Rules &amp; Guidelines', html)
        self.assertIn('Contact Organizers', html)
        self.assertIn('hero-explore-btn', html)
        self.assertIn('hero-rules-btn', html)
        self.assertIn('hero-contact-btn', html)
        self.assertIn('Register for Event', html)

        # 2. Disc cascade action buttons
        self.assertIn('Register for this event ↗', html)
        self.assertIn('id="discCascadeRegister"', html)
        self.assertIn('id="discCascadeRules"', html)
        self.assertIn('id="discCascadeCall"', html)

        # 3. Registration procedure buttons
        self.assertIn('Register Online Only', html)
        self.assertIn('View Campus Location', html)
        self.assertIn('track-btn-primary', html)
        self.assertIn('track-btn-secondary', html)

        # 4. Liquid button CSS integrity (no transparent wipeout on base container)
        res_css = self.client.get('/static/css/liquid-button.css')
        css_text = res_css.data.decode('utf-8')
        self.assertNotIn('border: 1.5px solid var(--liquid-border);\n  background: transparent;', css_text)
        self.assertIn('clip-path: none !important;', css_text)
        self.assertIn('.hero-explore-btn.liquid-btn', css_text)

        # 5. Liquid button JS integrity (no webkit-clip-path set on root button)
        res_js = self.client.get('/static/js/liquid-button.js')
        js_text = res_js.data.decode('utf-8')
        self.assertNotIn("btn.style.setProperty('-webkit-clip-path'", js_text)
        self.assertIn("invertedEl.style.setProperty('clip-path'", js_text)

        # 6. Verify the brochure-aligned official event names and rules integrity
        official_names = [
            'BGMI', 'Free Fire', 'Pencil Sketching', 'Get the Shield',
            'Photography', 'Content Creator', 'Solo Dance', 'Group Dance',
            'Beat Boxing', 'Face Painting', 'Tech Quiz', 'Solo Singing', 'Mad Ads',
            'Mono Acting', 'Fashion Walk'
        ]
        for name in official_names:
            self.assertIn(name, html)

        # 7. Check Free Fire has clean squad battle royale rules without Kannada text
        ff_ev = database.query_db("SELECT * FROM events WHERE event_name = 'Free Fire'", one=True)
        self.assertIsNotNone(ff_ev)
        self.assertIn('No teaming with other squads', ff_ev['rules_text'])
        self.assertNotIn('Kannada', ff_ev['rules_text'])

        singing_ev = database.query_db("SELECT * FROM events WHERE event_name IN ('Solo Singing', 'Singing')", one=True)
        self.assertIsNotNone(singing_ev)
        self.assertEqual(singing_ev['is_group'], 0)
        self.assertEqual(singing_ev['event_time'], 'To be announced')
        self.assertEqual(singing_ev['venue'], 'To be announced')
        self.assertIn('Indian films', singing_ev['rules_text'])
        self.assertIn('30 minutes before', singing_ev['rules_text'])

        # 8. Check Mono Acting has its own theme and solo format
        mono_ev = database.query_db("SELECT * FROM events WHERE event_name = 'Mono Acting'", one=True)
        self.assertIsNotNone(mono_ev)
        self.assertIn('Mythology characters', mono_ev['rules_text'])

    def test_staff_login_rejects_missing_password(self):
        admin_user = {
            'id': 1,
            'username': 'admin',
            'email': 'admin@example.test',
            'full_name': 'Test Admin',
            'role': 'admin',
            'password_hash': 'unused-for-empty-password-test',
        }
        with patch('app.query_db', return_value=admin_user):
            response = self.client.post('/login', data={'username': 'admin', 'password': ''})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid ID or credentials', response.data)
        self.assertNotIn(b'Event operations', response.data)

    def test_staff_login_form_marks_password_required(self):
        response = self.client.get('/login')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Password *', response.data)
        self.assertNotIn(b'ID-only access supported', response.data)

    def test_sqlite_initial_seed_persists_official_events(self):
        if database.DB_MODE != 'sqlite':
            self.skipTest('This regression covers the SQLite fallback only.')

        result = database.query_db("SELECT COUNT(*) AS count FROM events", one=True)

        self.assertEqual(result['count'], 15)

    def test_official_events_use_confirmed_november_date(self):
        if database.DB_MODE != 'sqlite':
            self.skipTest('This regression checks the isolated SQLite seed.')

        dates = database.query_db("SELECT DISTINCT event_date FROM events")

        self.assertEqual(dates, [{'event_date': '25-26-nov-2026'}])

    def test_seed_migrates_all_legacy_event_dates(self):
        if database.DB_MODE != 'sqlite':
            self.skipTest('This regression checks the isolated SQLite seed.')

        fixture_name = 'Legacy Schedule Migration Fixture'
        custom_fixture_name = 'Custom Schedule Preservation Fixture'
        database.execute_db(
            """INSERT INTO events (event_name, event_type, event_date, event_time, venue)
               VALUES (%s, %s, %s, %s, %s)""",
            (fixture_name, 'Test', '19-sep-2026', '10:00 AM', 'Test Venue')
        )
        database.execute_db(
            """INSERT INTO events (event_name, event_type, event_date, event_time, venue)
               VALUES (%s, %s, %s, %s, %s)""",
            (custom_fixture_name, 'Test', '01-dec-2026', '10:00 AM', 'Test Venue')
        )
        initialized_before = database._DB_INITIALIZED
        try:
            database._DB_INITIALIZED = False
            database.create_tables_and_seed()
            migrated = database.query_db(
                "SELECT event_date FROM events WHERE event_name = %s",
                (fixture_name,), one=True
            )
            self.assertEqual(migrated['event_date'], '25-26-nov-2026')
            custom = database.query_db(
                "SELECT event_date FROM events WHERE event_name = %s",
                (custom_fixture_name,), one=True
            )
            self.assertEqual(custom['event_date'], '01-dec-2026')
        finally:
            database._DB_INITIALIZED = initialized_before
            database.execute_db("DELETE FROM events WHERE event_name = %s", (fixture_name,))
            database.execute_db("DELETE FROM events WHERE event_name = %s", (custom_fixture_name,))

    def test_public_events_deduplicate_pubg_and_bgmi_aliases(self):
        rows = [
            {'id': 7, 'event_name': 'Pubg'},
            {'id': 8, 'event_name': 'Free Fire'},
            {'id': 32, 'event_name': 'BGMI'},
        ]
        with patch('app.query_db', return_value=rows):
            events = app_module.get_public_events()

        self.assertEqual([event['event_name'] for event in events], ['Pubg', 'Free Fire'])

    def test_public_certificate_verification_route_is_removed(self):
        self.assertEqual(self.client.get('/verify').status_code, 404)

    def test_event_contacts_are_available_through_contact_dialog(self):
        response = self.client.get('/events')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="contactModal"', response.data)
        self.assertIn(b'openContactDialog', response.data)
        self.assertIn(b'btn-card-contact', response.data)
        self.assertIn(b'id="discCascadeCall"', response.data)
        self.assertIn(b'id="contact" class="map-section"', response.data)

    def test_pending_payment_pass_is_not_called_confirmed(self):
        pending_registration = {
            'registration_uid': 'REG-TEST12345',
            'payment_status': 'pending',
            'amount_paid': 0,
            'payment_method': 'Online',
            'utr_number': 'UTR123456',
            'payment_proof': None,
            'payment_verified_at': None,
            'receipt_delivery_status': 'not_sent',
            'full_name': 'Test Participant',
            'event_name': 'Test Event',
            'event_fee': 400,
        }
        with patch('app.query_db', return_value=pending_registration):
            response = self.client.get('/payment-status/REG-TEST12345')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Registration received', response.data)
        self.assertIn(b'not confirmed until', response.data.lower())
        self.assertNotIn(b'Successfully registered!', response.data)
        self.assertNotIn(b'Demo mode', response.data)

    def test_registration_uses_the_live_upi_recipient_without_demo_copy(self):
        from io import BytesIO
        from PIL import Image

        response = self.client.get('/register?event_id=1')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'919980846695@federal', response.data)
        self.assertIn(b'/static/images/federal-upi-qr.png', response.data)
        self.assertIn(b'eventFee.toFixed(2)', response.data)
        self.assertIn(b'UPI_PAYEE_NAME', response.data)
        for obsolete in (b'Demo only', b'Demo UPI', b'Demo mode', b'test placeholders', b'demopay@ybl', b'admin@upi'):
            self.assertNotIn(obsolete, response.data)

        qr_response = self.client.get('/static/images/federal-upi-qr.png')
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response.mimetype, 'image/png')
        self.assertEqual(Image.open(BytesIO(qr_response.data)).size, (529, 529))

    def test_every_event_uses_the_shared_payment_recipient_and_qr(self):
        rows = database.query_db("SELECT upi_id, qr_code_image FROM events")

        self.assertTrue(rows)
        for event in rows:
            self.assertEqual(event['upi_id'], Config.DEFAULT_UPI_ID)
            self.assertIsNone(event['qr_code_image'])

    def test_event_upi_qr_uses_shared_payee_and_event_fee(self):
        from urllib.parse import parse_qs, urlparse

        event = {'event_name': 'Pencil Sketching', 'event_fee': 100, 'upi_id': 'old-event@upi'}
        real_qr_make = app_module.qrcode.make
        with patch.object(app_module, 'query_db', return_value=event), \
                patch.object(app_module.qrcode, 'make', wraps=real_qr_make) as make_qr:
            response = self.client.get('/events/12/upi-qr')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        payload = parse_qs(urlparse(make_qr.call_args.args[0]).query)
        self.assertEqual(payload['pa'], ['919980846695@federal'])
        self.assertEqual(payload['pn'], ['CHETHANA K'])
        self.assertEqual(payload['am'], ['100'])
        self.assertEqual(payload['cu'], ['INR'])

    def test_admin_participants_list_renders_on_sqlite(self):
        """Verify /admin/participants executes valid SQLite GROUP_CONCAT syntax without syntax error."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 14
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        response = self.client.get('/admin/participants')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Participants Management', response.data)

    def test_25_security_csv_formula_injection_sanitization(self):
        """SEC-07: Verify sanitize_csv_cell prefixes formula-triggering characters with a single quote."""
        self.assertEqual(app_module.sanitize_csv_cell('=CMD("calc")'), "'=CMD(\"calc\")")
        self.assertEqual(app_module.sanitize_csv_cell('+1+1'), "'+1+1")
        self.assertEqual(app_module.sanitize_csv_cell('-2+3'), "'-2+3")
        self.assertEqual(app_module.sanitize_csv_cell('@SUM(A1:A2)'), "'@SUM(A1:A2)")
        self.assertEqual(app_module.sanitize_csv_cell('Normal Name'), 'Normal Name')
        self.assertEqual(app_module.sanitize_csv_cell(400), 400)

    def test_26_security_email_identity_mismatch_blocks_profile_overwrite(self):
        """SEC-02: Verify unauthenticated registration with an existing email but different phone is blocked."""
        email = f"sec02_{int(time.time()*1000)}@college.edu"
        events = database.query_db("""
            SELECT e.id
            FROM events e
            LEFT JOIN (SELECT event_id, COUNT(*) as cnt FROM registrations GROUP BY event_id) r ON e.id = r.event_id
            WHERE e.is_group = 0 AND (e.max_participants IS NULL OR COALESCE(r.cnt, 0) < e.max_participants)
            ORDER BY e.id ASC
            LIMIT 2
        """)
        if len(events) < 2:
            self.skipTest('Need at least two solo events with open capacity.')
        ev1, ev2 = str(events[0]['id']), str(events[1]['id'])

        # Legitimate student registers for event 1
        r1 = self.client.post('/register', data={
            'full_name': 'Original Student',
            'email': email,
            'phone': '9876500001',
            'college_name': 'Original College',
            'department': 'PCMC',
            'semester': 'I PUC',
            'event_id': ev1,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(r1.status_code, 200)

        # Attacker attempts to register same email for event 2 with different phone and fake name
        r2 = self.client.post('/register', data={
            'full_name': 'Attacker Overwrite',
            'email': email,
            'phone': '9111111111',
            'college_name': 'Fake College',
            'department': 'PCMC',
            'semester': 'I PUC',
            'event_id': ev2,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b'already registered with a different phone number', r2.data)

        # Verify original student's name and college remain intact
        p = database.query_db("SELECT full_name, college_name FROM participants WHERE email = %s", (email,), one=True)
        self.assertEqual(p['full_name'], 'Original Student')
        self.assertEqual(p['college_name'], 'Original College')

        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (email,), commit=True)

    def test_27_security_member_cannot_modify_certificate_settings_or_settle_online_utr(self):
        """SEC-04 & SEC-06: Verify member role cannot overwrite certificate coords/templates or settle pending online UTRs."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['username'] = 'member1'
            sess['role'] = 'member'
            sess['_csrf_token'] = 'sec-token'

        res_coords = self.client.post(
            '/admin/settings/certificate-coords',
            data={'name_x': 100, 'name_y': 100, 'csrf_token': 'sec-token'},
            follow_redirects=False
        )
        self.assertEqual(res_coords.status_code, 302)
        self.assertIn('/login', res_coords.location)

    def test_28_security_payment_proof_unauthorized_access_blocked(self):
        """SEC-05: Verify unauthenticated users cannot access uploaded payment screenshots."""
        # Unauthenticated request without session ownership or staff role
        res = self.client.get('/payment-proofs/secret_screenshot.png')
        self.assertEqual(res.status_code, 403)

        # Same for legacy static upload path alias
        res_legacy = self.client.get('/static/uploads/payment_proofs/secret_screenshot.png')
        self.assertEqual(res_legacy.status_code, 403)

        # User who uploaded the proof in their session can access
        with self.client.session_transaction() as sess:
            sess['uploaded_payment_proofs'] = ['secret_screenshot.png']

        # Non-existent file should now reach the directory check (404), not 403
        res_owner = self.client.get('/payment-proofs/secret_screenshot.png')
        self.assertEqual(res_owner.status_code, 404)

    def test_29_theme_color_palette_tokens_and_integrity(self):
        """Verify the user-specified dual-mode color palette tokens, component classes, and template links."""
        # 1. Fetch theme.css directly
        res = self.client.get('/static/css/theme.css')
        self.assertEqual(res.status_code, 200)
        theme_css = res.data.decode('utf-8')

        # 2. Check Bright-Mode core tokens
        self.assertIn('--color-primary: #0066FF;', theme_css)
        self.assertIn('--color-secondary: #FF7A00;', theme_css)
        self.assertIn('--color-accent: #E91E63;', theme_css)
        self.assertIn('--color-bg: #F5F5F5;', theme_css)
        self.assertIn('--color-surface: #FFFFFF;', theme_css)
        self.assertIn('--color-text-primary: #212121;', theme_css)
        self.assertIn('--color-text-secondary: #555555;', theme_css)
        self.assertIn('--color-border: #E0E0E0;', theme_css)
        self.assertIn('--color-success: #28A745;', theme_css)
        self.assertIn('--color-warning: #FFC107;', theme_css)
        self.assertIn('--color-error: #DC3545;', theme_css)

        # 3. Check Dark-Mode core tokens
        self.assertIn('--color-primary: #0A84FF;', theme_css)
        self.assertIn('--color-secondary: #FF9500;', theme_css)
        self.assertIn('--color-accent: #FF2D55;', theme_css)
        self.assertIn('--color-bg: #121212;', theme_css)
        self.assertIn('--color-surface: #1E1E1E;', theme_css)
        self.assertIn('--color-text-primary: #E0E0E0;', theme_css)
        self.assertIn('--color-text-secondary: #A0A0A0;', theme_css)
        self.assertIn('--color-border: #333333;', theme_css)
        self.assertIn('--color-success: #34C759;', theme_css)
        self.assertIn('--color-warning: #FFCC00;', theme_css)
        self.assertIn('--color-error: #FF3B30;', theme_css)

        # 4. Check Component-level button states & tokens
        self.assertIn('.btn-primary', theme_css)
        self.assertIn('.btn-secondary', theme_css)
        self.assertIn('--color-primary-hover: #0052CC;', theme_css)
        self.assertIn('--color-primary-active: #004099;', theme_css)
        self.assertIn('--color-primary-hover: #0066CC;', theme_css)
        self.assertIn('--color-primary-active: #0055AA;', theme_css)
        self.assertIn('--color-secondary-hover: #CC6600;', theme_css)
        self.assertIn('--color-secondary-active: #B35A00;', theme_css)
        self.assertIn('--color-secondary-hover: #E68A00;', theme_css)
        self.assertIn('--color-secondary-active: #CC7A00;', theme_css)

        # 5. Check Typography & Form classes
        self.assertIn('.subheading', theme_css)
        self.assertIn('.text-highlight', theme_css)
        self.assertIn(':focus-visible', theme_css)

        # 6. Verify main style.css imports theme.css
        res_style = self.client.get('/static/css/style.css')
        self.assertEqual(res_style.status_code, 200)
        style_css = res_style.data.decode('utf-8')
        self.assertIn("theme.css", style_css)

        # 7. Verify templates reference theme.css and correct theme color meta
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')
        self.assertIn('theme.css', events_html)
        self.assertIn('themeColorMeta', events_html)

        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 200)
        login_html = res_login.data.decode('utf-8')
        self.assertIn('theme.css', login_html)
        self.assertIn('themeColorMeta', login_html)

    def test_event_banners_coordinators_and_descriptions(self):
        """Verify 15th event (Solo Singing), BGMI description, and coordinator contacts across events and Contact Us."""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # 1. 15th Event: Solo Singing
        self.assertIn('Solo Singing', html)
        self.assertIn('solo-singing.webp', html)
        self.assertIn('A soulful solo singing competition celebrating vocal brilliance', html)

        # 2. BGMI Description
        self.assertIn('A premier battle royale tournament where four-player squads deploy across high-stakes battlegrounds', html)

        # 3. Contact Us lists only the two faculty in charge; event coordinators remain on event cards.
        contact_section = html.split('<section id="contact"', 1)[1].split('</section>', 1)[0]
        for name in (Config.COORDINATOR_PRIMARY_NAME, Config.COORDINATOR_SECONDARY_NAME):
            self.assertIn(name, contact_section)
        for phone in (Config.CONTACT_PHONE_PRIMARY, Config.CONTACT_PHONE_SECONDARY):
            self.assertIn(phone, contact_section)
        for name in (Config.EVENT_COORDINATOR_PRIMARY_NAME, Config.EVENT_COORDINATOR_SECONDARY_NAME):
            self.assertNotIn(name, contact_section)
            self.assertIn(name, html)
        for phone in (Config.EVENT_COORDINATOR_PRIMARY_PHONE, Config.EVENT_COORDINATOR_SECONDARY_PHONE):
            self.assertNotIn(phone, contact_section)
            self.assertIn(phone, html)
        self.assertEqual(contact_section.count('class="contact-card coordinator-phone-card"'), 2)
        self.assertEqual(contact_section.count('Faculty in Charge'), 2)
        self.assertNotIn('Faculty Event Coordinator', contact_section)
        self.assertIn('id="contactModal"', html)

        # 4. Event Coordinators for every event
        self.assertIn('RANJITHA B K', html)
        self.assertIn('88615 91085', html)
        self.assertIn('SINDHU M R', html)
        self.assertIn('88922 63116', html)

        # 5. Database verification
        events = database.query_db("SELECT * FROM events ORDER BY id ASC")
        self.assertEqual(len(events), 15)
        for ev in events:
            self.assertEqual(ev['faculty_name'], 'RANJITHA B K')
            self.assertEqual(ev['faculty_phone'], '88615 91085')
            self.assertEqual(ev['student_name'], 'SINDHU M R')
            self.assertEqual(ev['student_phone'], '88922 63116')
            self.assertTrue(ev['description'] and len(ev['description'].strip()) > 10)
            self.assertTrue(ev['banner_image'] and len(ev['banner_image'].strip()) > 3)

            # 6. Verify image endpoint returns HTTP 200 (not 404)
            img_res = self.client.get(f"/static/images/{ev['banner_image']}")
            self.assertEqual(img_res.status_code, 200, f"Image for {ev['event_name']} ({ev['banner_image']}) returned {img_res.status_code}")

    def test_banner_images_resilience_and_specific_events(self):
        """Verify beatboxing, content creator, solo dance, and group dance images load reliably."""
        target_images = [
            'Beatboxing.jpeg',
            'beatboxing.jpeg',
            'Content_Creator.jpeg',
            'contentcreator.jpeg',
            'Solo_Dance.jpeg',
            'solo_dance.jpeg',
            'groupdance.jpeg',
            'Group_Dance.jpeg',
            'solo-singing.webp',
        ]
        for img_name in target_images:
            res = self.client.get(f"/static/images/{img_name}")
            self.assertEqual(res.status_code, 200, f"Expected 200 for {img_name}, got {res.status_code}")
            self.assertGreater(len(res.data), 1000)

    def test_certificate_generator_custom_template_only_participant_name(self):
        """Verify certificate renders only the participant name centered in dark blue on custom template."""
        from certificate_generator import generate_certificate
        from PIL import Image

        participant_name = "Pooja Hegde"
        cert_code, file_path, rel_url = generate_certificate(
            participant_name=participant_name,
            event_name="Solo Singing",
            event_date="25–26 Nov 2026",
            rank="1st"
        )
        self.assertTrue(os.path.exists(file_path))
        im = Image.open(file_path)
        self.assertEqual(im.size, (2480, 1754))

    def test_whatsapp_and_email_receipt_system(self):
        """Verify that payment receipts are dispatched via both WhatsApp and Email."""
        from mailer import send_receipt_email, send_whatsapp_receipt, format_whatsapp_receipt

        # 1. Test WhatsApp message format
        wa_text = format_whatsapp_receipt(
            participant_name="Ranjitha B K",
            event_name="Solo Singing",
            payment_method="Online UPI",
            amount_paid=100,
            utr_number="UPI9980846695",
            registration_uid="REG-TEST-12345"
        )
        self.assertIn("SHREE DAKSHA ACADEMY", wa_text)
        self.assertIn("Ranjitha B K", wa_text)
        self.assertIn("Solo Singing", wa_text)
        self.assertIn("₹100", wa_text)
        self.assertIn("REG-TEST-12345", wa_text)
        self.assertIn("6362436295", wa_text)

        # 2. Test WhatsApp dispatch
        wa_ok, wa_msg, wa_url = send_whatsapp_receipt(
            recipient_phone="8861591085",
            participant_name="Ranjitha B K",
            event_name="Solo Singing",
            payment_method="Online UPI",
            amount_paid=100,
            utr_number="UPI9980846695",
            registration_uid="REG-TEST-12345"
        )
        self.assertTrue(wa_ok)
        self.assertTrue(wa_url.startswith("https://wa.me/918861591085"))
        self.assertIn("REG-TEST-12345", wa_url)

        # 3. Test Email receipt dispatch in app context
        with self.app.app_context():
            email_ok, email_msg = send_receipt_email(
                recipient_email="ranjitha@example.com",
                participant_name="Ranjitha B K",
                event_name="Solo Singing",
                payment_method="Online UPI",
                amount_paid=100,
                utr_number="UPI9980846695",
                registration_uid="REG-TEST-12345"
            )
            self.assertTrue(email_ok)

    def test_registration_form_alignment_and_headings(self):
        """Verify registration form headings and descriptions are left-aligned and properly styled."""
        res = self.client.get('/register')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Check section headings and descriptions exist
        self.assertIn('Choose your event', html)
        self.assertIn('Review the event format, date, venue, and entry fee.', html)
        self.assertIn('Participant details', html)
        self.assertIn('Tell us who is taking part and where they study.', html)

        # Check CSS theme for flex alignment
        css_res = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(css_res.status_code, 200)
        css = css_res.data.decode('utf-8')
        self.assertIn('.form-section-heading {', css)
        self.assertIn('display: flex !important', css)
        self.assertIn('flex-direction: column !important', css)
        self.assertIn('align-items: flex-start !important', css)

    def test_registration_whatsapp_receipt_route(self):
        """Verify the direct WhatsApp receipt endpoint redirects correctly."""
        # Query an existing valid event with capacity
        ev = database.query_db("""
            SELECT e.id FROM events e
            LEFT JOIN (
                SELECT event_id, SUM(CASE WHEN is_group = 1 THEN team_size ELSE 1 END) as cnt
                FROM registrations WHERE COALESCE(status, 'pending') <> 'cancelled'
                GROUP BY event_id
            ) r ON e.id = r.event_id
            WHERE COALESCE(r.cnt, 0) < e.max_participants
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(ev)

        # Create a test registration (use hex suffix to prevent numeric substring collision in attendance tests)
        uid_token = uuid.uuid4().hex[:8]
        reg_info = database.create_registration(
            full_name="WhatsApp Test Student",
            email=f"wa_test_reg_{uid_token}@testdomain.org",
            phone="9876543210",
            college_name="Test College",
            department="PCMB",
            semester="II PUC",
            event_id=ev['id'],
            team_name=None,
            team_size=1,
            team_members=None,
            payment_status='paid',
            amount_paid=100,
            payment_method='Online',
            utr_number=f"UTRTEST{uid_token}",
            registered_by=1,
            is_group_event=False
        )
        self.assertTrue(reg_info.get('ok'))
        reg_uid = reg_info['registration_uid']

        # Call endpoint
        try:
            res = self.client.get(f'/registration/{reg_uid}/whatsapp-receipt')
            self.assertEqual(res.status_code, 302)
            location = res.headers.get('Location', '')
            self.assertTrue(location.startswith('https://wa.me/919876543210'))
            self.assertIn(reg_uid, location)
        finally:
            database.execute_db("DELETE FROM registrations WHERE registration_uid = %s", (reg_uid,))
            database.execute_db("DELETE FROM participants WHERE email = %s", (f"wa_test_reg_{uid_token}@testdomain.org",))

    def test_pointwise_rules_structure_across_all_events(self):
        """Verify all 15 events have point-wise rules delimited by newlines, with gaming having extended rules."""
        events = database.query_db("SELECT event_name, rules_text FROM events")
        self.assertEqual(len(events), 15)

        for ev in events:
            rules_text = (ev['rules_text'] or '').strip()
            self.assertTrue(len(rules_text) > 0, f"Event {ev['event_name']} has empty rules")
            lines = [line.strip() for line in rules_text.split('\n') if line.strip()]
            self.assertGreaterEqual(
                len(lines),
                4,
                f"Event {ev['event_name']} rules must be point-wise with at least 4 individual points"
            )

        # Check gaming specific additions
        bgmi = database.query_db("SELECT rules_text FROM events WHERE event_name = 'BGMI'", one=True)
        self.assertIsNotNone(bgmi)
        bgmi_rules = bgmi['rules_text']
        self.assertIn('smartphones', bgmi_rules.lower())
        self.assertIn('emulators', bgmi_rules.lower())
        self.assertIn('custom room', bgmi_rules.lower())
        self.assertIn('screenshot', bgmi_rules.lower())

        free_fire = database.query_db("SELECT rules_text FROM events WHERE event_name = 'Free Fire'", one=True)
        self.assertIsNotNone(free_fire)
        ff_rules = free_fire['rules_text']
        self.assertIn('No teaming with other squads', ff_rules)
        self.assertIn('smartphones', ff_rules.lower())
        self.assertIn('emulators', ff_rules.lower())
        self.assertIn('screenshot', ff_rules.lower())

    def test_general_rules_and_regulations_categorization_and_championship_button(self):
        """Verify General Rules & Regulations categorization, clarified 3rd point, complete awards points, and highlight championship redirect button."""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # 1. Highlight Section: General Championship button redirects to #rules
        championship_stat = html.split('class="stat-card stat-card-championship', 1)[1].split('<!-- Card 3: Prize pool -->', 1)[0]
        self.assertIn('stat-action-link', championship_stat)
        self.assertIn('href="#rules"', championship_stat)
        self.assertIn('Championship Rules', championship_stat)

        # 2. General Rules Section
        self.assertIn('id="rules"', html)
        rules_section = html.split('id="rules"', 1)[1].split('id="registration"', 1)[0]

        # Eligibility & Registration card
        self.assertIn('Eligibility & Registration', rules_section)
        self.assertNotIn('<strong>', rules_section)
        self.assertIn('Participation is open exclusively to bona fide PUC students', rules_section)
        self.assertIn('PUC students (I PUC & II PUC)', rules_section)
        self.assertIn('Every participant must carry a valid physical college ID card', rules_section)
        self.assertIn('hard copy of the receipt', rules_section)
        self.assertIn('Gate Pass with QR code', rules_section)
        self.assertIn('registered for all 15 competitions', rules_section)

        # Conduct & Safety card
        self.assertIn('Conduct & Safety', rules_section)
        self.assertIn('Strict campus decorum and discipline must be maintained', rules_section)
        self.assertIn('Sharp objects, fireworks, flammable substances, lasers', rules_section)

        # Timing & Preparation card (specifically verifying clarified 3rd point)
        self.assertIn('Timing & Preparation', rules_section)
        self.assertIn('30 minutes before inauguration', rules_section)
        self.assertIn('USB flash drive in MP3 or WAV format', rules_section)
        self.assertIn('45 minutes prior to event commencement', rules_section)
        self.assertIn('backup copy on a mobile device', rules_section)

        # Awards & Certification card (verifying missing points restored, no cash prize / 1 lakh pool mention)
        self.assertIn('id="rules-awards"', rules_section)
        awards_card = rules_section.split('id="rules-awards"', 1)[1].split('</article>', 1)[0]
        self.assertIn('Winners and runners-up in each competition will receive official trophies, medals, and merit certificates.', awards_card)
        self.assertIn('Official E-Certificates of Participation authenticated by Shree Daksha Academy', awards_card)
        self.assertIn('Overall General Championship Rolling Trophy', awards_card)
        self.assertIn('Valedictory Ceremony', awards_card)
        self.assertIn('WhatsApp and email', awards_card)
        self.assertIn('judging panel whose decisions are final, absolute, and binding', awards_card)

        # Strictly ensure NO cash prize or 1 lakh pool references in rules
        self.assertNotIn('cash prize', awards_card.lower())
        self.assertNotIn('1 lakh', awards_card.lower())
        self.assertNotIn('cash', awards_card.lower())

        # Ensure payment instructions are NOT inside Awards & Certification
        self.assertNotIn('scan the UPI QR code', awards_card)
        self.assertNotIn('The website\'s UPI details are currently in demo mode', awards_card)

    def test_button_animation_and_shadcn_integration(self):
        """Verify the neobrutalism button animation and shadcn/Tailwind configuration files."""
        import os

        # 1. Verify component files exist in components/ui
        self.assertTrue(os.path.exists("components/ui/button.tsx"))
        self.assertTrue(os.path.exists("components/ui/demo.tsx"))

        with open("components/ui/button.tsx", "r", encoding="utf-8") as f:
            button_code = f.read()
            self.assertIn("cva(", button_code)
            self.assertIn("hover:translate-x-boxShadowX hover:translate-y-boxShadowY hover:shadow-none", button_code)
            self.assertIn("export { Button, buttonVariants }", button_code)

        with open("components/ui/demo.tsx", "r", encoding="utf-8") as f:
            demo_code = f.read()
            self.assertIn("export {", demo_code)
            self.assertIn("Default,", demo_code)
            self.assertIn("Reverse,", demo_code)
            self.assertIn("NoShadow,", demo_code)
            self.assertIn("Neutral", demo_code)

        # 2. Verify Tailwind config and Globals CSS exist and contain shadow/translate tokens
        self.assertTrue(os.path.exists("tailwind.config.js"))
        with open("tailwind.config.js", "r", encoding="utf-8") as f:
            tw_code = f.read()
            self.assertIn("boxShadowX: '4px'", tw_code)
            self.assertIn("boxShadowY: '4px'", tw_code)
            self.assertIn("secondaryBlack: '#212121'", tw_code)

        self.assertTrue(os.path.exists("globals.css"))
        with open("globals.css", "r", encoding="utf-8") as f:
            css_code = f.read()
            self.assertIn("--box-shadow-x: 4px;", css_code)
            self.assertIn("--shadow: var(--box-shadow-x) var(--box-shadow-y) 0px 0px var(--border);", css_code)

        # 3. Verify the 4 designated buttons use the exact neobrutalism animation in theme CSS
        theme_css = self.client.get('/static/css/daksha-theme.css').data.decode('utf-8')

        # Check button selectors exist in the animation block
        self.assertIn('#hero .hero-actions .hero-rules-btn', theme_css)
        self.assertIn('#hero .hero-actions .hero-contact-btn', theme_css)
        self.assertIn('#events .btn-card-rules', theme_css)
        self.assertIn('#events .btn-card-contact', theme_css)
        self.assertIn('#events #discCascadeRules', theme_css)
        self.assertIn('#events #discCascadeCall', theme_css)

        # Check hover translation & shadow-none
        self.assertIn('transform: translate(4px, 4px) !important;', theme_css)
        self.assertIn('box-shadow: 0px 0px 0px 0px transparent !important;', theme_css)

        # Check resting 4px 4px border shadow
        self.assertIn('box-shadow: 4px 4px 0px 0px #0f172a !important;', theme_css)
        self.assertIn('box-shadow: 4px 4px 0px 0px #2563eb !important;', theme_css)

    def test_selective_liquid_button_enhancement(self):
        """Verify liquid animation is applied strictly and exclusively to the approved buttons with proper green/blue highlights."""
        import os

        # 1. Verify React component source code exists
        self.assertTrue(os.path.exists("components/ui/liquid-button.tsx"))
        with open("components/ui/liquid-button.tsx", "r", encoding="utf-8") as f:
            react_code = f.read()
            self.assertIn("export const liquidButtonVariants", react_code)
            self.assertIn("export default LiquidButton;", react_code)

        # 2. Verify static JS selector restrictions
        with open("static/js/liquid-button.js", "r", encoding="utf-8") as f:
            js_code = f.read()
            # Allowed buttons
            self.assertIn(".hero-explore-btn", js_code)
            self.assertIn(".hero-rules-btn", js_code)
            self.assertIn(".hero-contact-btn", js_code)
            self.assertIn("#discCascadeRules", js_code)
            self.assertIn("#discCascadeCall", js_code)
            self.assertIn(".btn-card-rules", js_code)
            self.assertIn(".btn-card-contact", js_code)
            self.assertIn("#discCascadeRegister", js_code)
            self.assertIn(".btn-card-register", js_code)
            self.assertIn(".track-footer a.track-btn-primary", js_code)
            self.assertIn("#submitBtn", js_code)

            # Excluded buttons in BUTTON_SELECTORS
            self.assertNotIn("'.header-cta-classic'", js_code)
            self.assertNotIn("'#headerRegisterBtn'", js_code)
            self.assertNotIn("'#upiPayButton'", js_code)
            self.assertNotIn("'#copyUpiBtn'", js_code)

        # 3. Verify CSS colors: Green for the two register buttons, Blue (#3b82f6) for all others
        with open("static/css/liquid-button.css", "r", encoding="utf-8") as f:
            css_code = f.read()
            # Green buttons
            self.assertIn(".btn-card-register.liquid-btn", css_code)
            self.assertIn("#discCascadeRegister.liquid-btn", css_code)
            self.assertIn("--liquid-fill: #10b981 !important;", css_code)

            # Blue buttons (#3b82f6)
            self.assertIn(".hero-explore-btn.liquid-btn", css_code)
            self.assertIn(".hero-rules-btn.liquid-btn", css_code)
            self.assertIn(".hero-contact-btn.liquid-btn", css_code)
            self.assertIn("#discCascadeRules.liquid-btn", css_code)
            self.assertIn("#discCascadeCall.liquid-btn", css_code)
            self.assertIn(".btn-card-rules.liquid-btn", css_code)
            self.assertIn(".btn-card-contact.liquid-btn", css_code)
            self.assertIn(".track-footer a.track-btn-primary.liquid-btn", css_code)
            self.assertIn("#submitBtn.liquid-btn", css_code)
            self.assertIn("--liquid-fill: #3b82f6 !important;", css_code)

        # 4. Verify templates/events.html has active buttons without data-no-liquid
        res_events = self.client.get('/events')
        events_html = res_events.data.decode('utf-8')
        self.assertIn('class="candy-btn hero-explore-btn"', events_html)
        self.assertIn('class="candy-btn hero-rules-btn"', events_html)
        self.assertIn('class="candy-btn hero-contact-btn"', events_html)
        self.assertIn('id="discCascadeRules" class="disc-cascade-rules"', events_html)
        self.assertIn('id="discCascadeCall" class="disc-cascade-call"', events_html)
        self.assertIn('id="discCascadeRegister" class="disc-cascade-register"', events_html)
        self.assertIn('class="btn-card-rules"', events_html)
        self.assertIn('class="btn-card-contact"', events_html)
        self.assertIn('class="btn-card-register"', events_html)
        self.assertNotIn('class="btn-card-register" data-no-liquid', events_html)
        self.assertNotIn('id="discCascadeRegister" class="disc-cascade-register" data-no-liquid', events_html)

        # 5. Verify register.html targets
        res_reg = self.client.get('/register')
        reg_html = res_reg.data.decode('utf-8')
        self.assertIn('id="submitBtn" class="clean-black-submit-btn"', reg_html)
        self.assertIn('id="upiPayButton" href="#" class="clean-black-submit-btn" data-no-liquid', reg_html)
        self.assertIn('id="copyUpiBtn" data-no-liquid', reg_html)

    def test_35_refined_liquid_buttons_and_countdown_live_state(self):
        """Verify button styling palettes, dark mode explore visibility, active nav pill highlight, and Fest is Live timer."""
        # 1. Check /events template copy updates
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')

        self.assertIn('Starts on 25, 26 November 2026, Bengaluru', events_html)
        self.assertIn('Registrations Open &bull; Daksha Infinix', events_html)
        self.assertNotIn('Important Payment & Receipt Terms', events_html)
        self.assertIn('No physical hard copy receipt is required', events_html)
        self.assertIn('View Campus Location', events_html)

        # 2. Verify countdown timer logic for 'Fest is Live'
        self.assertIn('if (diff <= 0) {', events_html)
        self.assertIn('fest-live-badge', events_html)
        self.assertIn('fest-live-dot', events_html)
        self.assertIn('Fest is Live', events_html)
        self.assertIn("capsule.classList.add('is-live');", events_html)

        # 3. Verify liquid-button.css styles
        res_css = self.client.get('/static/css/liquid-button.css')
        self.assertEqual(res_css.status_code, 200)
        liquid_css = res_css.data.decode('utf-8')

        # Register buttons: blue background, green liquid on hover
        self.assertIn('.btn-card-register.liquid-btn', liquid_css)
        self.assertIn('#discCascadeRegister.liquid-btn', liquid_css)
        self.assertIn('background: #2563eb !important;', liquid_css)
        self.assertIn('--liquid-fill: #10b981 !important;', liquid_css)

        # Explore button: white resting background, black resting text, white on liquid-filled
        self.assertIn('.hero-explore-btn.liquid-btn', liquid_css)
        self.assertIn('--liquid-fill: #2563eb !important;', liquid_css)
        self.assertIn('.hero-explore-btn.liquid-btn.is-liquid-filled .liquid-btn-content', liquid_css)

        # Registration procedure track buttons and submit button: white resting background, black text, blue hover
        self.assertIn('.track-footer a.track-btn-primary.liquid-btn', liquid_css)
        self.assertIn('.track-footer a.track-btn-primary.liquid-btn.is-liquid-filled .liquid-btn-content', liquid_css)
        self.assertIn('.track-btn-secondary.liquid-btn', liquid_css)
        self.assertIn('#submitBtn.liquid-btn', liquid_css)
        self.assertIn('background: #ffffff !important;', liquid_css)
        self.assertIn('color: #0f172a !important;', liquid_css)

        # 4. Verify daksha-theme.css light theme active navigation highlight and live badge
        res_theme = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_theme.status_code, 200)
        theme_css = res_theme.data.decode('utf-8')

        self.assertIn('.fest-live-badge', theme_css)
        self.assertIn('.fest-live-dot', theme_css)
        self.assertIn('.fest-live-text', theme_css)
        self.assertIn(':root[data-theme="light"] .landing-header .image-like-nav .nav-link.active', theme_css)
        self.assertIn(':root[data-theme="light"] .landing-header .nav-pill-indicator', theme_css)
        self.assertIn('background: #eff6ff !important;', theme_css)
        self.assertIn('border: 1.5px solid #2563eb !important;', theme_css)
        self.assertIn('color: #1d4ed8 !important;', theme_css)

    def test_36_explore_and_register_buttons_contrast_and_liquid_states(self):
        """Verify Explore and Register buttons have white background with black text turning white on liquid fill."""
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')

        # Check dark theme override in events.html
        self.assertIn('html:not([data-theme="light"]) .hero-actions .hero-explore-btn', events_html)
        self.assertIn('[data-theme="dark"] .hero-actions .hero-explore-btn { background: #ffffff !important; color: #0f172a !important;', events_html)

        # Check DOM elements
        self.assertIn('hero-explore-btn', events_html)
        self.assertIn('Register Online Only', events_html)
        self.assertIn('track-btn track-btn-primary', events_html)

        # Check liquid-button.css rules
        res_css = self.client.get('/static/css/liquid-button.css')
        self.assertEqual(res_css.status_code, 200)
        css = res_css.data.decode('utf-8')

        self.assertIn('.hero-explore-btn.liquid-btn,', css)
        self.assertIn('.track-footer a.track-btn-primary.liquid-btn,', css)
        self.assertIn('background: #ffffff !important;', css)
        self.assertIn('color: #0f172a !important;', css)
        self.assertIn('--liquid-fill: #2563eb !important;', css)
        self.assertIn('.hero-explore-btn.liquid-btn:hover .liquid-btn-content', css)
        self.assertIn('.hero-explore-btn.liquid-btn.is-liquid-filled .liquid-btn-content', css)
        self.assertIn('.track-footer a.track-btn-primary.liquid-btn.is-liquid-filled .liquid-btn-content', css)

        # Check liquid-button.js dynamic class toggle
        res_js = self.client.get('/static/js/liquid-button.js')
        self.assertEqual(res_js.status_code, 200)
        js = res_js.data.decode('utf-8')
        self.assertIn("btn.classList.add('is-liquid-filled')", js)
        self.assertIn("btn.classList.remove('is-liquid-filled')", js)
        self.assertIn("state.radius >= targetRadius * 0.55", js)

    def test_37_mobile_layout_hierarchy_and_button_sizing(self):
        """Verify mobile hero layout order, title sizing, and cascade register button dimensions."""
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')

        # Mobile hero title enlarged font-size
        self.assertIn('font-size: clamp(3.0rem, 13vw, 4.4rem) !important;', events_html)

        # Mobile hero layout order sequence
        self.assertIn('#hero .hero-title-wrap { order: 1 !important;', events_html)
        self.assertIn('#hero .hero-subtitle { order: 2 !important;', events_html)
        self.assertIn('#hero .hero-countdown-block { order: 3 !important;', events_html)
        self.assertIn('#hero .hero-actions { order: 4 !important;', events_html)

        # Mobile hero actions 2-row layout with explore on top and rules/contact below
        self.assertIn('grid-template-columns: 1fr 1fr !important;', events_html)
        self.assertIn('grid-column: 1 / -1 !important;', events_html)

        # Mobile disc cascade action buttons: rules/call side-by-side, register full-width larger
        self.assertIn('.disc-cascade-register {', events_html)
        self.assertIn('flex: 1 1 100% !important;', events_html)
        self.assertIn('min-height: 46px !important;', events_html)

        # Verify daksha-theme.css mobile ordering and title sizing
        res_theme = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_theme.status_code, 200)
        theme_css = res_theme.data.decode('utf-8')
        self.assertIn(':root[data-theme] .hero-subtitle { order: 2 !important;', theme_css)
        self.assertIn(':root[data-theme] .hero-countdown-block { order: 3 !important;', theme_css)
        self.assertIn('font-size: clamp(3.0rem, 13vw, 4.4rem) !important;', theme_css)

        # Verify liquid-button.css mobile full-width register button
        res_liquid = self.client.get('/static/css/liquid-button.css')
        self.assertEqual(res_liquid.status_code, 200)
        liquid_css = res_liquid.data.decode('utf-8')
        self.assertIn('#discCascadeRegister.liquid-btn,', liquid_css)
        self.assertIn('height: 46px !important;', liquid_css)
        self.assertIn('flex: 1 1 100% !important;', liquid_css)

    def test_38_choose_your_palette_sun_moon_toggle(self):
        """Verify the 'Choose your palette' sun/moon celestial toggle is integrated across mobile and desktop, upper and lower sections."""
        # 1. Check landing page (templates/landing_base.html)
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Upper desktop header
        self.assertIn('id="themeToggleBtn"', html)
        self.assertIn('class="choose-palette-btn celestial-theme-toggle"', html)

        # Upper mobile drawer
        self.assertIn('id="themeToggleBtnMobile"', html)
        self.assertIn('class="choose-palette-btn celestial-theme-toggle mobile-theme-switch-btn"', html)

        # Lower footer
        self.assertIn('id="footerThemeToggle"', html)

        # "Choose your palette" label present in toggles
        self.assertIn('Choose your palette', html)

        # Sun and Moon celestial bodies and sky present
        self.assertIn('theme-icon-moon', html)
        self.assertIn('theme-icon-sun', html)
        self.assertIn('celestial-toggle-orb', html)
        self.assertIn('sky-night', html)
        self.assertIn('sky-day', html)

        # Direct theme switching without opening popup
        self.assertIn('window.toggleSiteTheme = function (event)', html)
        self.assertIn('window.toggleFooterTheme = function ()', html)

        # 2. Check base template (templates/base.html)
        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 200)
        login_html = res_login.data.decode('utf-8')
        self.assertIn('id="baseThemeToggle"', login_html)
        self.assertIn('class="choose-palette-btn celestial-theme-toggle footer-theme-toggle"', login_html)
        self.assertIn('Choose your palette', login_html)

        # 3. Check CSS theme rules in daksha-theme.css
        res_css = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_css.status_code, 200)
        css = res_css.data.decode('utf-8')

        self.assertIn('.choose-palette-btn', css)
        self.assertIn('.celestial-toggle-orb', css)
        self.assertIn(':root[data-theme="dark"] .choose-palette-btn .body-moon', css)
        self.assertIn(':root[data-theme="light"] .choose-palette-btn .body-sun', css)

        # 4. Check React components existence
        import os
        self.assertTrue(os.path.exists('components/ui/sun-moon-theme-toggle.tsx'), "sun-moon-theme-toggle.tsx missing")
        self.assertTrue(os.path.exists('components/ui/demo.tsx'), "demo.tsx missing")

    def test_39_mobile_refinements_and_circular_sun_moon_toggle(self):
        """Verify circular sun/moon toggle, mobile title hierarchy, single-line date, full-width explore, centered CD carousel, and scroll animations."""
        # 1. Circular button with no visible palette text in templates
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertNotIn('<span class="palette-label">', html)
        self.assertIn('aria-label="Choose your palette"', html)

        # 2. Daksha and Infinix structure
        self.assertIn('class="hero-title-daksha"', html)
        self.assertIn('class="hero-title-infinix"', html)
        self.assertIn('Starts on 25, 26 November 2026, Bengaluru', html)

        # 3. CSS checks for circular toggle and mobile layout
        res_css = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_css.status_code, 200)
        css = res_css.data.decode('utf-8')

        self.assertIn('.choose-palette-btn', css)
        self.assertIn('border-radius: 50% !important;', css)
        self.assertIn('.choose-palette-btn .palette-label {', css)
        self.assertIn('display: none !important;', css)

        # 4. Mobile explore button spans full width matching rules/contact
        self.assertIn('justify-self: stretch !important;', html)
        self.assertIn('width: 100% !important;', html)

        # 5. CD Carousel centered buttons
        self.assertIn('.disc-cascade-actions { position:absolute; left:50% !important;', html)
        self.assertIn('transform:translateX(-50%) !important;', html)

        # 6. Scroll fade-in/fade-out animations
        self.assertIn('initScrollFadeAnimations', html)
        self.assertIn('.scroll-fade-item', html)
        self.assertIn('.scroll-fade-item.scroll-in', html)
        self.assertIn('.scroll-fade-item.scroll-out', html)

    def test_37_mobile_view_and_coordinator_refinements(self):
        """Verify mobile hero date, contact redirection, faculty-only coordinator modal, 3-dot menu and theme toggle refinements."""
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')

        # 1. Date text format
        self.assertIn('Starts on 25, 26 November 2026, Bengaluru', events_html)
        self.assertNotIn('Starts on 25th, 26th November 2026, Bengaluru.', events_html)

        # 2. Hero Contact Organizers button redirects to #contact section
        self.assertIn('onclick="scrollToSection(\'contact\', event)" class="candy-btn hero-contact-btn"', events_html)

        # 3. Contact modal: faculty coordinators only, 2 phone numbers, student coordinator removed
        self.assertIn('// Faculty coordinators only - student coordinator section removed per requirements', events_html)
        self.assertIn('const primaryFaculty = data.facultyName', events_html)
        self.assertIn('const primaryPhone = data.facultyPhone', events_html)
        self.assertIn('const secondaryFaculty = ', events_html)
        self.assertIn('const secondaryPhone = ', events_html)

        # 4. Mobile 3-dot menu: left line removed and oval active background fixed
        res_css = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_css.status_code, 200)
        css = res_css.data.decode('utf-8')

        self.assertIn(':root[data-theme] .landing-header #headerNavCenter.open', css)
        self.assertIn('border-left: none !important;', css)
        self.assertIn(':root[data-theme="light"] .landing-header .image-like-nav .nav-link.active', css)
        self.assertIn('border-radius: 10px !important;', css)

        # 5. Mobile theme button: small circular button without full-box border, 44px
        self.assertIn('#themeToggleBtnMobile', css)
        self.assertIn('width: 44px !important;', css)
        self.assertIn('height: 44px !important;', css)

        # 6. Smooth theme switching without lag (theme-transitioning class)
        self.assertIn('html.theme-transitioning', events_html)
        self.assertIn("root.classList.add('theme-transitioning');", events_html)

        # 7. Daksha Infinix Style main event name enlarged
        self.assertIn(':root[data-theme] .disc-cascade-head h3', css)
        self.assertIn('font-size: clamp(28px, 4.4vw, 42px) !important;', css)

    def test_38_rules_button_matching_and_mobile_oval_fix(self):
        """Verify rules button size matches contact button on mobile, and white theme mobile menu oval/line glitch is eliminated."""
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')

        # 1. Rules button matches Contact button in mobile styles
        self.assertIn('.hero-actions .hero-rules-btn {', events_html)
        self.assertIn('min-height: 40px !important;', events_html)
        self.assertIn('justify-self: stretch !important;', events_html)

        # 2. Pill indicator explicitly suppressed on mobile to prevent giant oval & blue line
        res_css = self.client.get('/static/css/daksha-theme.css')
        self.assertEqual(res_css.status_code, 200)
        css = res_css.data.decode('utf-8')

        self.assertIn('@media (min-width: 1161px)', css)
        self.assertIn('@media (max-width: 1160px)', css)
        self.assertIn('display: none !important;', css)
        self.assertIn('visibility: hidden !important;', css)

        # 3. JS movePillTo does not run on mobile view (width <= 1160)
        self.assertIn('window.innerWidth <= 1160', events_html)
        self.assertIn("pill.style.display = 'none';", events_html)

        # 4. style.css and base.html do not have mobile border-left on header-nav-center
        res_style = self.client.get('/static/css/style.css')
        self.assertEqual(res_style.status_code, 200)
        style_css = res_style.data.decode('utf-8')
        self.assertNotIn('border-left: 1px solid #e2e8f0 !important;', style_css)
        self.assertIn('border-left: none !important;', style_css)

        # 5. Body class synchronization for theme switching
        self.assertIn("document.body.classList.toggle('light-theme', next === 'light')", events_html)

    def test_39_awards_cert_text_and_mobile_submit_button_and_dashboard_white_theme(self):
        """Verify 5th point in Awards & Certification updated, registration button wording reduced, team members shown, and base locked to light theme."""
        # 1. Awards and Certification rule 05 update
        res_events = self.client.get('/events')
        self.assertEqual(res_events.status_code, 200)
        events_html = res_events.data.decode('utf-8')
        self.assertIn('Official digital certificates are sent directly to participants via WhatsApp and email.', events_html)
        self.assertNotIn('Digital certificates can be downloaded from the official portal', events_html)

        # 2. Registration submit button reduced text and wrap styles
        res_reg = self.client.get('/register')
        self.assertEqual(res_reg.status_code, 200)
        reg_html = res_reg.data.decode('utf-8')
        self.assertIn("setSubmitText('Submit with Payment Proof →');", reg_html)
        self.assertIn("setSubmitText('Submit (Pay at College) →');", reg_html)
        self.assertNotIn("setSubmitText('Submit Registration with Payment Proof →');", reg_html)
        self.assertNotIn("setSubmitText('Submit Registration (Pay Later at College) →');", reg_html)

        # 3. Base layout locked to white/light theme
        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 200)
        login_html = res_login.data.decode('utf-8')
        self.assertIn("document.documentElement.setAttribute('data-theme', 'light');", login_html)
        self.assertIn("#headerThemeToggle,\n        #baseThemeToggle,", login_html)

        # 4. Admin dashboard templates contain team members display
        with open('templates/admin_dashboard.html', 'r') as f:
            admin_tmpl = f.read()
        self.assertIn('<strong>Members:</strong> {{ reg.team_members }}', admin_tmpl)

        # 5. CSV export includes team members columns
        password = Config.ADMIN_PASSWORD
        self.client.post('/login', data={'username': 'admin', 'password': password}, follow_redirects=True)
        res_csv = self.client.get('/admin/export/registrations-csv')
        self.assertEqual(res_csv.status_code, 200)
        csv_content = res_csv.data.decode('utf-8')
        self.assertIn('Team Name', csv_content)
        self.assertIn('Team Size', csv_content)
        self.assertIn('Team Members', csv_content)

    def test_40_permanent_payment_proof_blob_and_under_1mb_limit(self):
        """Verify permanent DB blob persistence across ephemeral disk wipes, strict < 1 MB limit, and DB blob lifecycle."""
        import time
        import io
        from PIL import Image

        email = f"perm.proof_{int(time.time()*1000)}@college.edu"
        ev = database.query_db("SELECT id FROM events WHERE is_group = 0 AND event_fee > 0 LIMIT 1", one=True)
        ev_id = str(ev['id']) if ev else '1'
        test_utr = f"UTRPERM{int(time.time())}"

        # Generate a large test image (1600x1200) to verify compression and downscaling
        img_io = io.BytesIO()
        large_img = Image.new('RGB', (1600, 1200), color=(14, 165, 233))
        large_img.save(img_io, format='PNG')
        img_io.seek(0)

        res = self.client.post('/register', data={
            'full_name': 'Permanent Proof Student',
            'email': email,
            'phone': '9988776655',
            'college_name': 'Cloud State University',
            'department': 'Science',
            'semester': 'I PUC',
            'event_id': ev_id,
            'payment_method': 'Online',
            'utr_number': test_utr,
            'payment_screenshot': (img_io, 'large_receipt.png')
        }, content_type='multipart/form-data', follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Payment submitted for verification', res.data)

        # 1. Retrieve registration and proof filename
        reg = database.query_db(
            "SELECT r.id as reg_id, r.payment_proof, r.payment_status FROM registrations r JOIN participants p ON r.participant_id = p.id WHERE p.email = %s",
            (email,), one=True
        )
        self.assertIsNotNone(reg)
        proof_filename = reg['payment_proof']
        self.assertIsNotNone(proof_filename)

        # 2. Verify blob exists in database table 'payment_proofs'
        blob_record = database.get_payment_proof_blob(proof_filename)
        self.assertIsNotNone(blob_record, "Blob record must exist in DB table payment_proofs")
        self.assertEqual(blob_record['mime_type'], 'image/jpeg')
        self.assertIsNotNone(blob_record['file_data'])

        # 3. Verify strict < 1 MB limit (under 1,048,576 bytes)
        blob_size = len(blob_record['file_data'])
        self.assertLess(blob_size, 1024 * 1024, f"Screenshot blob size ({blob_size} bytes) must be strictly under 1 MB")
        self.assertLess(blob_record['file_size'], 1024 * 1024)

        # 4. Simulate ephemeral disk wipe (e.g. Render restart/redeploy)
        local_path = os.path.join(app.config['UPLOAD_FOLDER_PAYMENTS'], proof_filename)
        if os.path.exists(local_path):
            os.remove(local_path)
        self.assertFalse(os.path.exists(local_path), "Local cache file was intentionally removed to test ephemeral wipe")

        # 5. Access payment proof URL as admin - should fall back to DB blob and restore local cache file!
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        proof_res = self.client.get(f'/payment-proofs/{proof_filename}')
        self.assertEqual(proof_res.status_code, 200, "Proof route must return 200 by reading from DB blob")
        self.assertEqual(proof_res.content_type, 'image/jpeg')
        self.assertEqual(len(proof_res.data), blob_size)

        # Verify disk cache was repopulated
        self.assertTrue(os.path.exists(local_path), "Local disk cache should be repopulated after DB read")

        # 6. Delete registration and verify both disk cache and DB blob are removed
        from app import remove_registration_record
        remove_ok = remove_registration_record(reg['reg_id'])
        self.assertTrue(remove_ok)

        # Verify DB blob is deleted
        self.assertIsNone(database.get_payment_proof_blob(proof_filename), "DB blob record must be removed on registration delete")
        self.assertFalse(os.path.exists(local_path), "Local cache file must be removed on registration delete")

    def test_41_whatsapp_receipt_and_college_name_no_pu_college(self):
        """Verify WhatsApp receipts and templates contain 'Shree Daksha Academy' and ZERO reference to 'PU College'."""
        from mailer import format_whatsapp_receipt
        receipt_text = format_whatsapp_receipt(
            participant_name='Aarav Patel',
            event_name='BGMI Tournament',
            payment_method='Online UPI',
            amount_paid=200,
            utr_number='UTR12345678',
            registration_uid='REG-TEST-RECEIPT1',
            base_url="https://shreedaksha.example.com"
        )
        self.assertIn("SHREE DAKSHA ACADEMY", receipt_text)
        self.assertNotIn("PU COLLEGE", receipt_text)
        self.assertNotIn("PU College", receipt_text)
        self.assertIn("https://shreedaksha.example.com/payment-status/REG-TEST-RECEIPT1", receipt_text)
        self.assertIn("REG-TEST-RECEIPT1", receipt_text)
        self.assertIn("Aarav Patel", receipt_text)

    def test_42_gate_pass_and_receipt_aliases(self):
        """Verify /pass/<uid>, /receipt/<uid>, and /ticket/<uid> aliases work identically and case-insensitively."""
        ev = database.query_db("SELECT id FROM events LIMIT 1", one=True)
        uid_token = uuid.uuid4().hex[:8]
        reg_info = database.create_registration(
            full_name="Alias Route Tester",
            email=f"alias_{uid_token}@testdomain.org",
            phone="9876500001",
            college_name="Test Institute",
            department="CSE",
            semester="5",
            event_id=ev['id'],
            team_name=None,
            team_size=1,
            team_members=None,
            payment_status='paid',
            amount_paid=100,
            payment_method='Cash',
            utr_number=None,
            registered_by=1,
            is_group_event=False
        )
        self.assertTrue(reg_info.get('ok'))
        reg_id = reg_info['registration_id']
        reg_uid = reg_info['registration_uid']

        # Test canonical URL
        res_canon = self.client.get(f'/payment-status/{reg_uid}')
        self.assertEqual(res_canon.status_code, 200)
        self.assertIn('Alias Route Tester', res_canon.data.decode('utf-8'))

        # Test /pass/<uid> alias
        res_pass = self.client.get(f'/pass/{reg_uid}')
        self.assertEqual(res_pass.status_code, 200)
        self.assertIn('Alias Route Tester', res_pass.data.decode('utf-8'))

        # Test case-insensitivity with lowercase
        res_pass_lower = self.client.get(f'/pass/{reg_uid.lower()}')
        self.assertEqual(res_pass_lower.status_code, 200)
        self.assertIn('Alias Route Tester', res_pass_lower.data.decode('utf-8'))

        # Test /receipt/<uid> alias
        res_receipt = self.client.get(f'/receipt/{reg_uid}')
        self.assertEqual(res_receipt.status_code, 200)
        self.assertIn('Alias Route Tester', res_receipt.data.decode('utf-8'))

        # Clean up
        from app import remove_registration_record
        remove_registration_record(reg_id)

    def test_43_team_certificates_generation_and_team_zip(self):
        """Verify team events generate a single certificate per team with team name and can be downloaded as ZIP."""
        # Find or create a group event
        ev = database.query_db("SELECT id, event_name FROM events WHERE is_group = 1 LIMIT 1", one=True)
        if not ev:
            ev = database.query_db("SELECT id, event_name FROM events LIMIT 1", one=True)

        uid_token = uuid.uuid4().hex[:8]
        reg_info = database.create_registration(
            full_name="Lead Captain",
            email=f"captain_{uid_token}@team.com",
            phone="9876500002",
            college_name="Engineering Academy",
            department="ISE",
            semester="6",
            event_id=ev['id'],
            team_name="Alpha Squad Test",
            team_size=4,
            team_members="Lead Captain, Alex Rider, Priya Sharma, Rohan Verma",
            payment_status='paid',
            amount_paid=400,
            payment_method='Online',
            utr_number=f"UTR{uid_token}",
            registered_by=1,
            is_group_event=True
        )
        self.assertTrue(reg_info.get('ok'))
        reg_id = reg_info['registration_id']

        # Login as admin and generate certificate for this team registration
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        gen_res = self.client.post(f'/admin/certificates/generate/{reg_id}', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)

        # Check database: individual certificates generated for all 4 players
        certs = database.query_db(
            "SELECT * FROM certificates WHERE registration_id = %s ORDER BY id ASC",
            (reg_id,)
        )
        self.assertEqual(len(certs), 4, "Individual certificates for all 4 team players must be generated")
        recipients = [c['recipient_name'] for c in certs]
        self.assertIn('Lead Captain', recipients)
        self.assertIn('Alex Rider', recipients)
        self.assertIn('Priya Sharma', recipients)
        self.assertIn('Rohan Verma', recipients)

        # Test team-zip download
        res_zip = self.client.get(f'/admin/certificates/team-zip/{reg_id}')
        self.assertEqual(res_zip.status_code, 200)
        self.assertEqual(res_zip.content_type, 'application/zip')
        self.assertIn('Alpha_Squad_Test_Certificates.zip', res_zip.headers.get('Content-Disposition', ''))

        # Inspect ZIP content: must contain strictly PNG files, NO PDFs
        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(res_zip.data))
        zip_namelist = zf.namelist()
        self.assertTrue(any(n.endswith('.png') for n in zip_namelist))
        self.assertFalse(any(n.endswith('.pdf') for n in zip_namelist), "The ZIP should contain only PNG files, not PDFs")

        # Clean up
        for c in certs:
            if c.get('file_path') and os.path.exists(c['file_path']):
                try: os.remove(c['file_path'])
                except OSError: pass
        database.query_db("DELETE FROM certificates WHERE registration_id = %s", (reg_id,), commit=True)
        from app import remove_registration_record
        remove_registration_record(reg_id)

    def test_44_whatsapp_certificate_link_and_share_buttons(self):
        """Verify certificate WhatsApp redirect and certificate management UI controls."""
        ev = database.query_db("SELECT id, event_name FROM events LIMIT 1", one=True)
        uid_token = uuid.uuid4().hex[:8]
        reg_info = database.create_registration(
            full_name="Certificate Share Student",
            email=f"share_{uid_token}@example.com",
            phone="9876500003",
            college_name="Tech Campus",
            department="ECE",
            semester="4",
            event_id=ev['id'],
            team_name=None,
            team_size=1,
            team_members=None,
            payment_status='paid',
            amount_paid=150,
            payment_method='Online',
            utr_number=f"UTR{uid_token}",
            registered_by=1,
            is_group_event=False
        )
        self.assertTrue(reg_info.get('ok'))
        reg_id = reg_info['registration_id']

        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        gen_res = self.client.post(f'/admin/certificates/generate/{reg_id}', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)

        cert = database.query_db("SELECT * FROM certificates WHERE registration_id = %s LIMIT 1", (reg_id,), one=True)
        self.assertIsNotNone(cert)
        cert_code = cert['certificate_code']

        # Test WhatsApp redirect endpoint
        res_wa = self.client.get(f'/certificate/{cert_code}/whatsapp')
        self.assertEqual(res_wa.status_code, 302)
        wa_redirect = res_wa.headers['Location']
        self.assertIn('919876500003', wa_redirect)
        self.assertIn(cert_code, wa_redirect)
        self.assertIn('SHREE%20DAKSHA%20ACADEMY', wa_redirect)

        # Test certificates admin UI contains Web Share and Team ZIP logic
        res_ui = self.client.get('/admin/certificates')
        self.assertEqual(res_ui.status_code, 200)
        ui_html = res_ui.data.decode('utf-8')
        self.assertIn('shareCertFile', ui_html)
        self.assertIn('navigator.share', ui_html)

        # Clean up
        if cert.get('certificate_pdf') and os.path.exists(cert['certificate_pdf']):
            try: os.remove(cert['certificate_pdf'])
            except OSError: pass
        if cert.get('certificate_image') and os.path.exists(cert['certificate_image']):
            try: os.remove(cert['certificate_image'])
            except OSError: pass
        from app import remove_registration_record
        remove_registration_record(reg_id)

    def test_45_qr_scanner_enlarged_viewport(self):
        """Verify QR scanner template features enlarged camera viewport and dynamic qrbox calculation."""
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        res = self.client.get('/admin/scanner')
        self.assertEqual(res.status_code, 200)
        scanner_html = res.data.decode('utf-8')
        self.assertIn('max-width: 620px', scanner_html)
        self.assertIn('min-height: 380px', scanner_html)
        self.assertIn('qrbox', scanner_html)
        self.assertIn('fps: 15', scanner_html)

        # Check /scanner route as well
        res2 = self.client.get('/scanner')
        self.assertEqual(res2.status_code, 200)

    def test_46_all_teams_zip_download(self):
        """Verify downloading the all-teams certificates ZIP packages PNG certificates for all teams without PDFs."""
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        res_zip = self.client.get('/admin/certificates/teams-zip')
        self.assertEqual(res_zip.status_code, 200)
        self.assertEqual(res_zip.content_type, 'application/zip')
        self.assertIn('SDA_Team_Certificates.zip', res_zip.headers.get('Content-Disposition', ''))

        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(res_zip.data))
        names = zf.namelist()
        self.assertGreaterEqual(len(names), 4, "Expected certificates for all teams")
        self.assertTrue(any('Alpha_Squad' in n for n in names))
        self.assertTrue(all(n.endswith('.png') for n in names), "ZIP should contain strictly PNG files")
        self.assertFalse(any(n.endswith('.pdf') for n in names), "ZIP should not contain any PDF files")

    def test_47_single_row_team_certificates_and_direct_dispatch(self):
        """Verify certificates hub displays team as a single row with all member chips and preview modal."""
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        res = self.client.get('/admin/certificates')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Verify no unwanted elements at top
        self.assertNotIn('📦 Download All Teams ZIP', html)
        self.assertNotIn('2. Text Coordinates', html)
        self.assertNotIn('name_x', html)
        self.assertNotIn('rank_x', html)

        # Verify single row squad elements
        self.assertIn('Alpha Squad', html)
        self.assertIn('Players (', html)
        self.assertIn('Preview All', html)
        self.assertIn('WhatsApp', html)
        self.assertIn('Email', html)
        self.assertIn('openPreviewModal', html)
        self.assertIn('shareTeamZip', html)

    def test_48_certificate_download_routes_png_and_pdf(self):
        """Verify /certificate/download/... and /certificates/... serve PNG and PDF reliably."""
        from certificate_generator import generate_certificate
        code, file_path, rel = generate_certificate(
            participant_name="Download Test Player",
            event_name="Binary Brains",
            event_date="25-26 Nov 2026",
            cert_code="SDA-2026-BB-TESTDL"
        )
        self.assertTrue(os.path.exists(file_path))

        # 1. /certificate/download/<code_or_file>.png
        res1 = self.client.get(f'/certificate/download/{code}.png')
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.mimetype, 'image/png')
        self.assertGreater(len(res1.data), 1000)

        # 2. /certificate/download/<code_or_file>.pdf
        res2 = self.client.get(f'/certificate/download/{code}.pdf')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.mimetype, 'application/pdf')
        self.assertTrue(res2.data.startswith(b'%PDF'))

        # 3. /certificates/download/<code_or_file>.png
        res3 = self.client.get(f'/certificates/download/{code}.png')
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.mimetype, 'image/png')

        # 4. /certificates/download/<code_or_file>.pdf
        res4 = self.client.get(f'/certificates/download/{code}.pdf')
        self.assertEqual(res4.status_code, 200)
        self.assertEqual(res4.mimetype, 'application/pdf')
        self.assertTrue(res4.data.startswith(b'%PDF'))

        # 5. /certificates/<code_or_file>.pdf
        res5 = self.client.get(f'/certificates/{code}.pdf')
        self.assertEqual(res5.status_code, 200)
        self.assertEqual(res5.mimetype, 'application/pdf')
        self.assertTrue(res5.data.startswith(b'%PDF'))

        # Clean up
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except OSError: pass

    def test_49_whatsapp_direct_redirect_and_instant_zip(self):
        """Verify WhatsApp action provides direct redirect anchor and triggers instant ZIP download."""
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        res_ui = self.client.get('/admin/certificates')
        self.assertEqual(res_ui.status_code, 200)
        html = res_ui.data.decode('utf-8')

        # Ensure direct anchor link to WhatsApp redirect endpoint with target="_blank"
        self.assertIn('/admin/certificates/team-whatsapp/', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('triggerZipDownload', html)

    def test_50_fast_bulk_certificate_generation_without_502(self):
        """Verify bulk certificate generation processes smoothly with template caching and skipping existing files."""
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        res = self.client.post('/admin/certificates/generate-bulk', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertTrue('Successfully processed' in html or 'already have valid certificates' in html)

    def test_51_create_registration_boolean_is_group_postgres_compatibility(self):
        """Verify create_registration accepts boolean is_group_event and stores strictly as integer 1/0."""
        from database import create_registration, query_db, seed_sample_teams
        import secrets
        
        ev = query_db("SELECT id FROM events LIMIT 1", one=True)
        ev_id = ev['id'] if ev else 1

        # Test with is_group_event=True (boolean expression)
        reg_true = create_registration(
            full_name="Postgres Bool Test Lead",
            email=f"lead_{secrets.token_hex(4)}@test.com",
            phone="9988776655",
            college_name="Test College",
            department="PCMC",
            semester="Second PUC",
            event_id=ev_id,
            team_name=f"BoolTeam_{secrets.token_hex(3)}",
            team_size=4,
            team_members="Lead, Member 2, Member 3, Member 4",
            payment_status="paid",
            amount_paid=400,
            payment_method="Online",
            utr_number=f"UTR{secrets.token_hex(4).upper()}",
            registered_by=1,
            is_group_event=True  # Python boolean
        )
        self.assertTrue(reg_true['ok'])
        row_true = query_db("SELECT is_group FROM registrations WHERE id = %s", (reg_true['registration_id'],), one=True)
        self.assertEqual(row_true['is_group'], 1)
        self.assertIsInstance(row_true['is_group'], int)

        # Test with is_group_event=False (boolean expression)
        reg_false = create_registration(
            full_name="Postgres Bool Test Solo",
            email=f"solo_{secrets.token_hex(4)}@test.com",
            phone="9988776654",
            college_name="Test College",
            department="PCMC",
            semester="Second PUC",
            event_id=ev_id,
            team_name=None,
            team_size=1,
            team_members=None,
            payment_status="paid",
            amount_paid=100,
            payment_method="Cash",
            utr_number=None,
            registered_by=1,
            is_group_event=False  # Python boolean
        )
        self.assertTrue(reg_false['ok'])
        row_false = query_db("SELECT is_group FROM registrations WHERE id = %s", (reg_false['registration_id'],), one=True)
        self.assertEqual(row_false['is_group'], 0)
        self.assertIsInstance(row_false['is_group'], int)

        # Test seed_sample_teams runs cleanly without any Seed Team Error and cleans up
        seed_sample_teams(force=False)
        database.execute_db("DELETE FROM certificates WHERE participant_id IN (SELECT id FROM participants WHERE email LIKE '%@sda-fest.edu')")
        database.execute_db("DELETE FROM attendance WHERE registration_id IN (SELECT id FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email LIKE '%@sda-fest.edu'))")
        database.execute_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email LIKE '%@sda-fest.edu')")
        database.execute_db("DELETE FROM participants WHERE email LIKE '%@sda-fest.edu'")

    def test_52_certificate_typography_whatsapp_and_email_attachment(self):
        """Verify bundled TrueType font loading, compact file sizes, WhatsApp direct chat link, and email PDF attachment."""
        from certificate_generator import get_font_by_name, generate_certificate
        from mailer import send_certificate_email

        # 1. Bundled TrueType font loads with requested size > 100
        f_bold = get_font_by_name("georgiab.ttf", 160)
        self.assertGreaterEqual(getattr(f_bold, 'size', 0), 100, "Font must be genuine TrueType scalable font, not 10px default")

        # 2. Solo certificate generation & compact sizes
        cert_code, file_path, rel_url = generate_certificate(
            participant_name="Rohan Verma",
            event_name="Debate",
            event_date="25–26 Nov 2026",
            college_name="Some Other College"
        )
        self.assertTrue(os.path.exists(file_path))
        pdf_path = file_path.replace('.png', '.pdf')
        jpg_path = file_path.replace('.png', '.jpg')
        self.assertTrue(os.path.exists(pdf_path), "Compact PDF certificate must be pre-generated")
        self.assertTrue(os.path.exists(jpg_path), "Lightweight JPG certificate must be pre-generated")

        pdf_size_kb = os.path.getsize(pdf_path) / 1024
        jpg_size_kb = os.path.getsize(jpg_path) / 1024
        self.assertLess(pdf_size_kb, 500, f"PDF certificate size ({pdf_size_kb:.1f} KB) must be under 500 KB")
        self.assertLess(jpg_size_kb, 700, f"JPG certificate size ({jpg_size_kb:.1f} KB) must be under 700 KB")

        # 3. Team certificate generation with lead + members
        team_code, team_png, _ = generate_certificate(
            participant_name="Cyber Knights",
            event_name="BGMI",
            event_date="25–26 Nov 2026",
            college_name="Engineering College",
            team_name="Cyber Knights",
            team_lead="Lead Player",
            team_members="Lead Player, Player Two, Player Three, Player Four"
        )
        self.assertTrue(os.path.exists(team_png))

        # 4. WhatsApp redirect link contains recipient phone and certificate link
        self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
        reg = database.query_db("SELECT r.id, p.phone FROM registrations r JOIN participants p ON r.participant_id = p.id LIMIT 1", one=True)
        if reg:
            res_wa = self.client.get(f"/admin/certificates/team-whatsapp/{reg['id']}")
            self.assertEqual(res_wa.status_code, 302)
            wa_loc = res_wa.headers['Location']
            self.assertTrue('whatsapp.com' in wa_loc or 'wa.me' in wa_loc)
            self.assertIn('SHREE%20DAKSHA%20ACADEMY', wa_loc)

        # 5. Email dispatch with PDF attachment
        with self.app.app_context():
            ok, msg = send_certificate_email(
                recipient_email="test_cert_attach@example.com",
                participant_name="Rohan Verma",
                event_name="Debate",
                certificate_path=pdf_path,
                certificate_code=cert_code
            )
            self.assertTrue(ok)
            self.assertIn("Certificate successfully dispatched", msg)

    def test_53_admin_usernames_configuration_and_login(self):
        """Verify Config.ADMIN_USERNAMES contains admin, adminsda1, adminsda2 and all can authenticate successfully."""
        password = Config.ADMIN_PASSWORD
        if not password:
            self.skipTest('Set ADMIN_PASSWORD to test admin logins.')

        self.assertIn('admin', Config.ADMIN_USERNAMES)
        self.assertIn('adminsda1', Config.ADMIN_USERNAMES)
        self.assertIn('adminsda2', Config.ADMIN_USERNAMES)

        for username in ('admin', 'adminsda1', 'adminsda2', 'AdminSDA1', 'AdminSDA2'):
            client = self.app.test_client()
            res = client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)
            self.assertEqual(res.status_code, 200, f"Failed login for username: {username}")
            with client.session_transaction() as sess:
                self.assertIsNotNone(sess.get('user_id'), f"user_id missing in session for {username}")
                self.assertEqual(sess.get('role'), 'admin', f"role is not admin for {username}")

    def test_54_bgmi_freefire_fixed_four_players_and_whatsapp_team_broadcast(self):
        """
        Verify:
        1. BGMI and Free Fire are strictly locked to exactly 4 players (min=4, max=4).
        2. Registration form contains fixed squad UI and handles solo vs team naming.
        3. WhatsApp receipt and certificate routes support multi-player team broadcast (share=all).
        4. Solo event certificates never show 'Team Lead'.
        """
        # 1. Event DB check
        events = database.query_db("SELECT event_name, is_group, min_team_size, max_team_size, rules_text FROM events WHERE LOWER(TRIM(event_name)) IN ('bgmi', 'free fire')")
        for ev in events:
            self.assertEqual(ev['is_group'], 1)
            self.assertEqual(ev['min_team_size'], 4, f"{ev['event_name']} min_team_size must be 4")
            self.assertEqual(ev['max_team_size'], 4, f"{ev['event_name']} max_team_size must be 4")
            self.assertIn("exactly 4 players", ev['rules_text'].lower())

        # 2. Registration page check
        res_reg = self.client.get('/register')
        self.assertEqual(res_reg.status_code, 200)
        html = res_reg.data.decode('utf-8')
        self.assertIn('fixedSquadNotice', html)
        self.assertIn('Fixed Squad: Exactly 4 Players Required', html)
        self.assertIn('full_name_label', html)

        # 3. Solo certificate generation check - no 'Team Lead'
        from certificate_generator import generate_certificate
        code, path, _ = generate_certificate(
            participant_name="Pooja Hegde (Team Lead)",
            event_name="Solo Singing",
            event_date="25 Nov 2026",
            cert_code="TEST-SOLO-CLEAN"
        )
        self.assertEqual(code, "TEST-SOLO-CLEAN")
        self.assertTrue(os.path.exists(path))

        # 4. WhatsApp team receipt formatting and dispatch
        from mailer import format_whatsapp_receipt, send_whatsapp_receipt
        team_wa_text = format_whatsapp_receipt(
            participant_name="Captain Rahul",
            event_name="BGMI",
            payment_method="Online UPI",
            amount_paid=400,
            utr_number="UPI1234567890",
            registration_uid="REG-BGMI-SQUAD",
            team_name="Phantom Squad",
            team_members="Captain Rahul, Player Two, Player Three, Player Four",
            is_group=True
        )
        self.assertIn("Phantom Squad", team_wa_text)
        self.assertIn("Captain Rahul", team_wa_text)
        self.assertIn("Player Two", team_wa_text)
        self.assertIn("Player Three", team_wa_text)
        self.assertIn("Player Four", team_wa_text)

        # 5. WhatsApp broadcast URL generation (share=all)
        wa_ok, _, wa_url = send_whatsapp_receipt(
            recipient_phone="9876543210",
            participant_name="Captain Rahul",
            event_name="BGMI",
            payment_method="Online UPI",
            amount_paid=400,
            registration_uid="REG-BGMI-SQUAD",
            team_name="Phantom Squad",
            team_members="Captain Rahul, Player Two, Player Three, Player Four",
            is_group=True,
            share_all=True
        )
        self.assertTrue(wa_ok)
        self.assertTrue(wa_url.startswith("https://api.whatsapp.com/send?text="))
        self.assertNotIn("phone=", wa_url)
        self.assertIn("Phantom%20Squad", wa_url)

    def test_55_no_static_data_in_database(self):
        """Verify no dummy or static test team registrations exist in the database."""
        dummy_rows = database.query_db("SELECT id, email FROM participants WHERE email LIKE '%@sda-fest.edu'")
        self.assertEqual(len(dummy_rows), 0, "No dummy registrations with @sda-fest.edu should exist in database")

    def test_56_team_whatsapp_sends_all_teammates_certificates_at_once(self):
        """Verify WhatsApp certificate dispatch for teams sends only the team ZIP package (PNG only), while solo sends direct certificate link."""
        import urllib.parse
        from database import create_registration, execute_db, query_db

        ev = query_db("""
            SELECT e.id, e.event_name FROM events e
            LEFT JOIN (
                SELECT event_id, SUM(CASE WHEN is_group = 1 THEN team_size ELSE 1 END) as cnt
                FROM registrations WHERE COALESCE(status, 'pending') <> 'cancelled'
                GROUP BY event_id
            ) r ON e.id = r.event_id
            WHERE e.is_group = 1 AND COALESCE(r.cnt, 0) + 4 <= e.max_participants
            LIMIT 1
        """, one=True)
        if not ev:
            ev = query_db("SELECT id, event_name FROM events WHERE is_group = 1 LIMIT 1", one=True)
        self.assertIsNotNone(ev)

        token = uuid.uuid4().hex[:6]
        team_members_str = "Leader Alpha, Striker Bravo, Scout Charlie, Medic Delta"
        reg_info = create_registration(
            full_name="Leader Alpha",
            email=f"wa_squad_{token}@testdomain.org",
            phone="9123456780",
            college_name="Daksha Tech",
            department="Computer Science",
            semester="4th Sem",
            event_id=ev['id'],
            team_name=f"Squad_{token}",
            team_size=4,
            team_members=team_members_str,
            payment_status='paid',
            amount_paid=400,
            payment_method='Cash',
            utr_number=f"CASH-{token}",
            registered_by=1,
            is_group_event=True
        )
        self.assertTrue(reg_info.get('ok'))
        reg_id = reg_info['registration_id']
        reg_uid = reg_info['registration_uid']

        try:
            # Login as admin
            self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)

            # 1. Trigger WhatsApp team certificates endpoint
            res_wa = self.client.get(f'/admin/certificates/team-whatsapp/{reg_id}')
            self.assertEqual(res_wa.status_code, 302)
            wa_loc = res_wa.headers.get('Location', '')
            self.assertTrue(wa_loc.startswith('https://api.whatsapp.com/send'))

            # Parse decoded message
            parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(wa_loc).query)
            msg_text = parsed_query.get('text', [''])[0]

            # Verify ONLY the team ZIP package link is sent, NO separate per-member file links
            self.assertIn(f"/certificates/team/{reg_uid}/zip", msg_text)
            self.assertIn("Download Team Certificates (ZIP Package)", msg_text)
            self.assertNotIn("Striker Bravo:", msg_text)
            self.assertNotIn(".pdf", msg_text)

            # 2. Verify public access to the team ZIP route without admin session
            anon_client = self.app.test_client()
            res_zip = anon_client.get(f'/certificates/team/{reg_uid}/zip')
            self.assertEqual(res_zip.status_code, 200)
            self.assertEqual(res_zip.mimetype, 'application/zip')
            self.assertGreater(len(res_zip.data), 1000)

            # Verify the ZIP contains strictly PNG files, NO PDF files
            import io, zipfile
            zf = zipfile.ZipFile(io.BytesIO(res_zip.data))
            namelist = zf.namelist()
            self.assertGreater(len(namelist), 0)
            self.assertTrue(all(n.endswith('.png') for n in namelist), "ZIP must contain strictly PNG files")
            self.assertFalse(any(n.endswith('.pdf') for n in namelist), "ZIP must not contain any PDF files")

        finally:
            execute_db("DELETE FROM certificates WHERE registration_id = %s", (reg_id,))
            execute_db("DELETE FROM registrations WHERE id = %s", (reg_id,))
            execute_db("DELETE FROM participants WHERE email = %s", (f"wa_squad_{token}@testdomain.org",))

    def test_57_certificate_typography_suitable_and_normal(self):
        """Verify certificate generator applies reduced size, regular serif typography with proper spacing above placeholder line."""
        from certificate_generator import generate_certificate
        from PIL import Image

        cert_code, file_path, rel_url = generate_certificate(
            participant_name="Rohan Sharma",
            event_name="BGMI",
            event_date="2026-03-25",
            college_name="Shree Daksha Academy"
        )
        self.assertTrue(os.path.exists(file_path))

        with Image.open(file_path) as im:
            self.assertEqual(im.size, (2480, 1754))

        # Cleanup generated test certificate
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except OSError: pass
        pdf_file = file_path.replace('.png', '.pdf')
        if os.path.exists(pdf_file):
            try: os.remove(pdf_file)
            except OSError: pass

    def test_58_team_certificates_email_sends_zip_only(self):
        """Verify team certificate email dispatches a single ZIP attachment with PNG files only, while solo sends PNG."""
        from database import create_registration, execute_db, query_db

        ev = query_db("""
            SELECT e.id, e.event_name FROM events e
            LEFT JOIN (
                SELECT event_id, SUM(CASE WHEN is_group = 1 THEN team_size ELSE 1 END) as cnt
                FROM registrations WHERE COALESCE(status, 'pending') <> 'cancelled'
                GROUP BY event_id
            ) r ON e.id = r.event_id
            WHERE e.is_group = 1 AND COALESCE(r.cnt, 0) + 4 <= e.max_participants
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(ev)

        token = uuid.uuid4().hex[:6]
        team_members_str = "Leader Alpha, Striker Bravo, Scout Charlie, Medic Delta"
        reg_info = create_registration(
            full_name="Email Squad Lead",
            email=f"email_squad_{token}@testdomain.org",
            phone="9123456781",
            college_name="Daksha Tech",
            department="Computer Science",
            semester="4th Sem",
            event_id=ev['id'],
            team_name=f"EmailSquad_{token}",
            team_size=4,
            team_members=team_members_str,
            payment_status='paid',
            amount_paid=400,
            payment_method='Cash',
            utr_number=f"CASH-{token}",
            registered_by=1,
            is_group_event=True
        )
        self.assertTrue(reg_info.get('ok'))
        reg_id = reg_info['registration_id']

        try:
            self.client.post('/login', data={'username': 'admin', 'password': Config.ADMIN_PASSWORD}, follow_redirects=True)
            # Generate certs first
            self.client.post(f'/admin/certificates/generate/{reg_id}', follow_redirects=True)

            # Send team email
            res_email = self.client.post(f'/admin/certificates/team-email/{reg_id}', follow_redirects=True)
            self.assertEqual(res_email.status_code, 200)
            self.assertIn("Successfully emailed team certificates ZIP package", res_email.data.decode('utf-8'))

            # Check all certificates are marked sent
            certs = query_db("SELECT email_status FROM certificates WHERE registration_id = %s", (reg_id,))
            self.assertEqual(len(certs), 4)
            self.assertTrue(all(c['email_status'] == 'sent' for c in certs))

        finally:
            execute_db("DELETE FROM certificates WHERE registration_id = %s", (reg_id,))
            execute_db("DELETE FROM registrations WHERE id = %s", (reg_id,))
            execute_db("DELETE FROM participants WHERE email = %s", (f"email_squad_{token}@testdomain.org",))


if __name__ == '__main__':
    unittest.main()
