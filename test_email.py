"""
EventMate - SMTP Email Diagnostics & Test Tool
Run: python test_email.py [recipient@example.com]
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

def run_smtp_test(recipient=None):
    print("=" * 60)
    print("EventMate - Email Diagnostics & Connection Test")
    print("=" * 60)

    # 1. Check if .env file exists
    env_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '.env')
    if not os.path.exists(env_path):
        print("\n[ERROR] '.env' file NOT found in project folder!")
        print("Note: You may have edited '.env.example'. Flask only reads '.env'.")
        print("To fix: Copy '.env.example' to a new file named '.env'.")
        return False

    load_dotenv(dotenv_path=env_path, override=True)

    mode = os.environ.get('SMTP_MODE', 'demo').strip().lower()
    server_host = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    server_port = int(os.environ.get('SMTP_PORT', 587))
    username = os.environ.get('SMTP_USERNAME', '').strip()
    password = os.environ.get('SMTP_PASSWORD', '').strip()
    sender_email = os.environ.get('SMTP_SENDER_EMAIL', username).strip()
    use_tls = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')
    use_ssl = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't')

    target_recipient = recipient or sender_email or username

    print(f"\nConfiguration detected from .env:")
    print(f" - Mode          : {mode.upper()} ({'Simulated Delivery' if mode == 'demo' else 'Live Gmail SMTP'})")
    print(f" - SMTP Server   : {server_host}:{server_port}")
    print(f" - SMTP Username : {username or '(Empty)'}")
    print(f" - SMTP Password : {'*' * len(password) if password else '(Empty)'}")
    print(f" - Sender Email  : {sender_email or '(Empty)'}")
    print(f" - Target Recipient: {target_recipient or '(Empty)'}")
    print(f" - Use TLS       : {use_tls}")
    print(f" - Use SSL       : {use_ssl}")

    # Check for placeholder passwords
    is_placeholder = (
        not password 
        or password.lower() in ('paste_your_16_letter_password_here', 'your_16_character_app_password', 'your_gmail_app_password', 'emailuser@26')
        or any(k in password.upper() for k in ['PASTE_', 'YOUR_', 'PASSWORD'])
    )

    if mode == 'demo' or is_placeholder:
        print("\n" + "=" * 60)
        print("SAFE DEMO MODE ACTIVE")
        print("=" * 60)
        print("[OK] Certificate email dispatch is fully active in Safe Demo Mode.")
        print("[OK] Clicking 'Email' in the web interface will simulate instant delivery,")
        print("     update participant certificate status to 'EMAIL SENT', and log output.")
        print("\nTo send REAL live emails to participant inboxes:")
        print(" 1. Enable 2-Step Verification in Google Account -> Security.")
        print(" 2. Generate a 16-character App Password (search 'App Passwords' in Google).")
        print(" 3. In .env, set:")
        print("    SMTP_MODE=live")
        print("    SMTP_PASSWORD=your16charpassword")
        print("=" * 60)
        return True

    # Live Mode check
    if not username or "@" not in username:
        print("\n[ERROR] SMTP_USERNAME must be a valid Gmail address.")
        return False

    print("\nConnecting to live mail server...")
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(server_host, server_port, timeout=15)
            server.ehlo()
        else:
            server = smtplib.SMTP(server_host, server_port, timeout=15)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()

        print("Authenticating with SMTP credentials...")
        server.login(username, password)
        print("[SUCCESS] SMTP Login authenticated successfully!")

        if target_recipient and "@" in target_recipient:
            print(f"Sending test email to {target_recipient}...")
            msg = MIMEMultipart()
            msg['From'] = f"EventMate Test <{sender_email}>"
            msg['To'] = target_recipient
            msg['Subject'] = "EventMate - Live SMTP Test Email"
            msg.attach(MIMEText(
                "Hello!\n\nThis is a confirmation that your EventMate email configuration is working properly.\nCertificates can now be emailed directly to attendees.\n\nBest regards,\nEventMate Team",
                'plain'
            ))
            server.send_message(msg)
            print(f"[SUCCESS] Test email successfully delivered to {target_recipient}!")

        server.quit()
        print("\nAll checks passed! Your email sending is ready for live use.")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"\n[AUTHENTICATION FAILED] {e}")
        print("\nCommon reasons:")
        print(" 1. You used your regular Gmail password instead of a Google App Password.")
        print(" 2. 2-Step Verification is not enabled on the Google Account.")
        print(" 3. The 16-character App Password was mistyped.")
        print(" (EventMate will continue operating seamlessly in Safe Demo Mode).")
        return False
    except Exception as e:
        print(f"\n[CONNECTION ERROR] {e}")
        return False

if __name__ == '__main__':
    recipient_arg = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_smtp_test(recipient_arg)
    sys.exit(0 if success else 1)
