import unittest
import json
import os
import time
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
        self.assertIn(b'26 November 2026', response.data)
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
            'college_name': 'City Engineering College',
            'department': 'BCA',
            'semester': '5th Sem',
            'event_id': target_event_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(response1.status_code, 200)
        self.assertTrue(b'Registration submitted' in response1.data or b'Registration successful' in response1.data)

        # 2. Duplicate registration attempt for same event
        response2 = self.client.post('/register', data={
            'full_name': 'Test Participant',
            'email': test_email,
            'phone': '9988776655',
            'college_name': 'City Engineering College',
            'department': 'BCA',
            'semester': '5th Sem',
            'event_id': target_event_id,
            'payment_method': 'Cash'
        }, follow_redirects=True)
        self.assertEqual(response2.status_code, 200)
        self.assertIn(b'Duplicate registration was prevented', response2.data)

        # Cleanup test registration to preserve event capacity for repeated test runs
        database.query_db("DELETE FROM registrations WHERE participant_id IN (SELECT id FROM participants WHERE email = %s)", (test_email,), commit=True)
        database.query_db("DELETE FROM participants WHERE email = %s", (test_email,), commit=True)

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
                ("Test Flow Student", f"flow.test_{int(time.time())}@example.com", "9876543210", "Test College", "BCA")
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
        """Test admin1 and admin2 access and formatting as admin SDA1 and admin SDA2"""
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

    def test_09_symposium_portal_sections(self):
        """Test the newly added countdown, stats, rules, registration, and FAQ sections on /events"""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')

        # 1. Event Dates & Hero Subtitle
        self.assertIn('Daksha Infinix', data)
        self.assertIn('Registration Open &bull; Daksha Infinix', data)
        self.assertNotIn('Daksha Infinitx', data)
        self.assertNotIn('Daksha Infinitix', data)
        self.assertNotIn('SDA 2026-27', data)
        self.assertNotIn('2026-27', data)
        self.assertNotIn('Annual Symposium 2026-27', data)
        self.assertIn('26th and 27th November', data)
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
        self.assertIn('stat-badge-events">12+<', data)
        self.assertNotIn('12+ EVENTS', data)
        self.assertNotIn('+ Events', data)
        self.assertIn('data-target="1"', data)
        self.assertNotIn('General Championship', data)
        self.assertIn('Prize Pool', data)
        self.assertIn('Lakh', data)

        # 3. Rules & Regulations Section
        self.assertIn('id="rules"', data)
        self.assertIn('General Rules & Regulations', data)
        self.assertIn('Eligibility & ID', data)
        self.assertIn('Campus Conduct', data)
        self.assertIn('Competitions & Timing', data)
        self.assertIn('id="rules-awards"', data)
        self.assertNotIn('id="rules-championship"', data)

        # 4. Registration Procedures & Payment (Online & Offline)
        self.assertIn('id="registration"', data)
        self.assertIn('Registration Procedures & Payment Details', data)
        self.assertIn('ONLINE COMPETITIONS', data)
        self.assertIn('OFFLINE & SPOT ENTRIES', data)
        self.assertIn('Important Payment & Receipt Terms', data)

        # 5. FAQ Section
        self.assertIn('id="faq"', data)
        self.assertIn('Frequently Asked Questions', data)
        self.assertIn('Who is eligible to participate', data)
        self.assertIn('Can students from different colleges form a combined team', data)
        self.assertIn('Will participants receive a certificate?', data)

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
        self.assertIn('sda_theme', data, "localStorage theme key missing")
        self.assertIn('[data-theme="light"]', data, "Light theme CSS rules missing")

        # 3. Verify robust light theme class targeting matching actual HTML classes
        # (the redesigned events page themes its header/nav/footer/celestial components;
        #  counters use .stat-number, and .stat-card/.principal-message-card no longer exist)
        self.assertIn('[data-theme="light"] .landing-header', data, "Light theme .landing-header rule missing")
        self.assertIn('[data-theme="light"] .image-like-nav', data, "Light theme .image-like-nav rule missing")
        self.assertIn('[data-theme="light"] .header-nav-center', data, "Light theme .header-nav-center rule missing")
        self.assertIn('[data-theme="light"] .l-footer', data, "Light theme .l-footer rule missing")
        self.assertIn('[data-theme="light"] .celestial-sky-day', data, "Light theme .celestial-sky-day rule missing")

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

        # 1. lenis-prevent attribute prevents scroll trapping
        self.assertIn('data-lenis-prevent', data)

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
                ("Backup Test Attendee", f"backup_{int(time.time())}@college.edu", "9988776655", "SDA College", "BCA")
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

    def test_18_general_championship_removal_and_prize_pool(self):
        """Verify General Championship is completely removed and Prize Pool is set to ₹1 Lakh"""
        res = self.client.get('/events')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        # General championship must NOT appear anywhere
        self.assertNotIn('General Championship', html)
        self.assertNotIn('general-championship', html)
        self.assertNotIn('rules-championship', html)
        
        # Prize pool must be ₹1 Lakh
        self.assertIn('₹1 Lakh', html)
        self.assertIn('data-target="1"', html)
        self.assertNotIn('₹ 2 Lakh', html)
        self.assertNotIn('₹2 Lakh', html)

        # 14 Events Lineup Dropdown
        self.assertIn('id="discCascadeIndex"', html)
        self.assertIn('id="discCascadeIndexButton"', html)
        self.assertIn('id="discCascadeIndexMenu"', html)
        self.assertIn('14 events', html)
        self.assertIn('disc-cascade-animated-arrow', html)
        self.assertIn('arrow-forward-backward', html)
        self.assertNotIn('Click here', html)
        self.assertNotIn('out of', html)
        self.assertIn('1 / ', html)

    def test_19_ui_improvements_attendance_and_event_config(self):
        """Verify 14 events in dropdown, forward/backward animated arrow, no 'Click here', no 'out of', single-line header with Register for Event button"""
        # 1. Check /events header button is "Register for Event" pointing to #events
        res = self.client.get('/events')
        html = res.data.decode('utf-8')
        self.assertIn('Register for Event', html)
        self.assertIn('14 events', html)
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
            'other_department': 'BCA Tech',
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
        edit_post_res = self.client.post(f"/admin/events/edit/{bgmi_event['id']}", data={
            'event_name': 'BGMI',
            'event_type': 'Gaming',
            'event_date': '26-nov-2026',
            'event_time': '10:00 AM',
            'venue': 'Computer Lab 3',
            'max_participants': '100',
            'is_group': '1',
            'min_team_size': '4',
            'max_team_size': '4',
            'event_fee': '400',
            'upi_id': 'admin@upi',
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

        # 6. Verify attendance view has no inflated 140 fake absence
        att_res = self.client.get('/admin/attendance')
        att_html = att_res.data.decode('utf-8')
        self.assertNotIn('140', att_html)
        self.assertIn('Awaiting Check-in', att_html)

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
        self.assertIn('Starts in', html)
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
        self.assertIn('Register Online Now', html)
        self.assertIn('View Campus Desk Location', html)
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

        # 6. Verify 14 authentic official event names and rules integrity
        official_names = [
            'BGMI', 'Free Fire', 'Pencil Sketch', 'Get the Shield',
            'Photography', 'Content Creator', 'Solo Dance', 'Group Dance',
            'Beat Boxing', 'Face Painting', 'Tech Quiz', 'Mad Adds',
            'Mono Acting', 'Ramp Walk'
        ]
        for name in official_names:
            self.assertIn(name, html)

        # 7. Check Free Fire has clean squad battle royale rules without Kannada text
        ff_ev = database.query_db("SELECT * FROM events WHERE event_name = 'Free Fire'", one=True)
        self.assertIsNotNone(ff_ev)
        self.assertIn('Mobile devices only', ff_ev['rules_text'])
        self.assertNotIn('Kannada', ff_ev['rules_text'])

        # 8. Check Mono Acting has its own theme and solo format
        mono_ev = database.query_db("SELECT * FROM events WHERE event_name = 'Mono Acting'", one=True)
        self.assertIsNotNone(mono_ev)
        self.assertIn('Mythology Characters', mono_ev['rules_text'])

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

        self.assertEqual(result['count'], 14)

    def test_official_events_use_confirmed_november_date(self):
        if database.DB_MODE != 'sqlite':
            self.skipTest('This regression checks the isolated SQLite seed.')

        dates = database.query_db("SELECT DISTINCT event_date FROM events")

        self.assertEqual(dates, [{'event_date': '26-nov-2026'}])

    def test_seed_migrates_all_legacy_event_dates(self):
        if database.DB_MODE != 'sqlite':
            self.skipTest('This regression checks the isolated SQLite seed.')

        fixture_name = 'Legacy Schedule Migration Fixture'
        database.execute_db(
            """INSERT INTO events (event_name, event_type, event_date, event_time, venue)
               VALUES (%s, %s, %s, %s, %s)""",
            (fixture_name, 'Test', '19-sep-2026', '10:00 AM', 'Test Venue')
        )
        initialized_before = database._DB_INITIALIZED
        try:
            database._DB_INITIALIZED = False
            database.create_tables_and_seed()
            migrated = database.query_db(
                "SELECT event_date FROM events WHERE event_name = %s",
                (fixture_name,), one=True
            )
            self.assertEqual(migrated['event_date'], '26-nov-2026')
        finally:
            database._DB_INITIALIZED = initialized_before
            database.execute_db("DELETE FROM events WHERE event_name = %s", (fixture_name,))

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

    def test_contact_cards_show_demo_phone_numbers_as_call_links(self):
        with patch.object(Config, 'CONTACT_PHONE_PRIMARY', '+91 90000 00001'), \
             patch.object(Config, 'CONTACT_PHONE_SECONDARY', '+91 90000 00002'):
            response = self.client.get('/events')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'tel:+919000000001', response.data)
        self.assertIn(b'tel:+919000000002', response.data)
        self.assertIn(b'+91 90000 00001', response.data)
        self.assertIn(b'+91 90000 00002', response.data)
        self.assertNotIn(b'Message official desk on WhatsApp', response.data)

    def test_pending_payment_pass_is_not_called_confirmed(self):
        pending_registration = {
            'registration_uid': 'REG-TEST12345',
            'payment_status': 'pending',
            'amount_paid': 0,
            'payment_method': 'Online',
            'utr_number': 'DEMO123456',
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

    def test_demo_upi_is_clearly_marked_as_test_only(self):
        if Config.PAYMENT_MODE != 'demo':
            self.skipTest('This regression covers demo payment messaging.')

        response = self.client.get('/register?event_id=1')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Demo only', response.data)
        self.assertIn(b'do not send real money', response.data.lower())

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
            'department': 'BCA',
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
            'department': 'BCA',
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

if __name__ == '__main__':
    unittest.main()
