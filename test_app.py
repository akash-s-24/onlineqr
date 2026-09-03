import unittest
import json
import os
from app import app
import database
from config import Config

class EventMateTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = self.app.test_client()
        self.app.config['TESTING'] = True

    def test_01_homepage_redirect(self):
        """Test home page redirects to events for guests"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/events', response.location)

    def test_02_events_page(self):
        """Test events page lists required symposium events"""
        response = self.client.get('/events')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'CodeCraft', response.data)
        self.assertIn(b'CodeStorm', response.data)
        self.assertIn(b'CodeVerse', response.data)
        self.assertIn(b'ByteBattle', response.data)
        self.assertIn(b'18-sep-2026', response.data)
        self.assertIn(b'19-sep-2026', response.data)
        self.assertIn(b'20-sep-2026', response.data)

    def test_03_login_page_renders(self):
        """Test login page renders properly and securely"""
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'EventMate Portal', response.data)
        self.assertIn(b'Administrator Sign In', response.data)
        # Ensure credentials are not exposed on page
        self.assertNotIn(b'Varshitha@2007', response.data)

    def test_04_admin_authentication(self):
        """Test admin login flow with varshitha / Varshitha@2007"""
        response = self.client.post('/login', data={
            'username': 'varshitha',
            'password': 'Varshitha@2007'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Control Dashboard', response.data)
        self.assertIn(b'Total Events', response.data)

    def test_05_student_registration_and_duplicate_prevention(self):
        """Test participant registration and duplicate check"""
        import time
        test_email = f"test.student_{int(time.time()*1000)}@college.edu"
        
        # 1. First registration for CodeCraft (event_id 1)
        response1 = self.client.post('/register', data={
            'full_name': 'Test Participant',
            'email': test_email,
            'phone': '9988776655',
            'college_name': 'City Engineering College',
            'department': 'BCA',
            'semester': '5th Sem',
            'event_id': '1'
        }, follow_redirects=True)
        self.assertEqual(response1.status_code, 200)
        self.assertIn(b'Registration successful', response1.data)

        # 2. Duplicate registration attempt for same event
        response2 = self.client.post('/register', data={
            'full_name': 'Test Participant',
            'email': test_email,
            'phone': '9988776655',
            'college_name': 'City Engineering College',
            'department': 'BCA',
            'semester': '5th Sem',
            'event_id': '1'
        }, follow_redirects=True)
        self.assertEqual(response2.status_code, 200)
        self.assertIn(b'Duplicate registration is prevented', response2.data)

    def test_06_attendance_toggle_and_certificate_flow(self):
        """Test attendance toggle via AJAX and certificate generation"""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'varshitha'
            sess['role'] = 'admin'

        # Fetch a registration record
        reg = database.query_db("SELECT id FROM registrations LIMIT 1", one=True)
        reg_id = reg['id']

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

        # 4. Public verification lookup
        verify_res = self.client.get(f'/verify?id={cert_code}')
        self.assertEqual(verify_res.status_code, 200)
        self.assertIn(b'OFFICIALLY VERIFIED', verify_res.data)
        self.assertIn(cert_code.encode(), verify_res.data)

        # 5. Invalid verification lookup
        invalid_res = self.client.get('/verify?id=INVALID-CODE-999')
        self.assertEqual(invalid_res.status_code, 200)
        self.assertIn(b'Certificate Not Found', invalid_res.data)

    def test_07_certificate_email_dispatch_flow(self):
        """Test certificate email dispatch in Safe Demo Mode"""
        # Login as admin
        self.client.post('/login', data={
            'username': 'varshitha',
            'password': 'Varshitha@2007'
        }, follow_redirects=True)

        # Get an existing certificate
        cert = database.query_db("SELECT id FROM certificates LIMIT 1", one=True)
        if cert:
            cert_id = cert['id']
            email_res = self.client.post(f'/admin/certificates/send-email/{cert_id}', follow_redirects=True)
            self.assertEqual(email_res.status_code, 200)
            self.assertIn(b'Certificate successfully dispatched', email_res.data)

            # Check certificates hub renders with smtp_info
            hub_res = self.client.get('/admin/certificates')
            self.assertEqual(hub_res.status_code, 200)
            self.assertIn(b'Email Dispatch', hub_res.data)

if __name__ == '__main__':
    unittest.main()
