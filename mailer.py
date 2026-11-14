import os
import re
import datetime
import smtplib
import base64
import json
import urllib.error
import urllib.request
import urllib.parse
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from config import Config

PLACEHOLDER_PASSWORDS = {
    '',
    'paste_your_16_letter_password_here',
    'your_16_character_app_password',
    'your_gmail_app_password',
    'emailuser@26',
    'your_password',
    'password',
    'changeme',
    'xxxx xxxx xxxx xxxx'
}


def _sanitize_header_value(value):
    """Strip CR/LF characters to prevent SMTP header injection."""
    return re.sub(r'[\r\n]+', ' ', str(value or '')).strip()


def is_demo_mode():
    """
    Determines whether email sending should operate in Safe Demo Mode (simulation)
    or attempt live Gmail SMTP dispatch.
    Returns: (is_demo: bool, reason: str)
    """
    load_dotenv(override=True)

    # Guard: Automated test environments and test runners always operate in Safe Demo Mode
    if os.environ.get('FLASK_TESTING') == 'True' or os.environ.get('TESTING') == 'True' or getattr(Config, 'TESTING', False):
        return True, "Automated test execution detected (FLASK_TESTING=True)"

    try:
        from flask import current_app
        if current_app and current_app.config.get('TESTING'):
            return True, "Flask application TESTING flag is active"
    except Exception:
        pass

    smtp_mode = os.environ.get('SMTP_MODE', getattr(Config, 'SMTP_MODE', 'demo')).strip().lower()
    smtp_username = os.environ.get('SMTP_USERNAME', getattr(Config, 'SMTP_USERNAME', '')).strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', getattr(Config, 'SMTP_PASSWORD', '')).strip()
    resend_key = os.environ.get('RESEND_API_KEY', getattr(Config, 'RESEND_API_KEY', '')).strip()
    resend_sender = os.environ.get('RESEND_FROM_EMAIL', getattr(Config, 'RESEND_FROM_EMAIL', '')).strip()

    if resend_key and resend_sender:
        return False, 'Resend HTTPS email credentials detected'

    if smtp_mode == 'demo':
        return True, "Safe Demo Mode is active in .env (SMTP_MODE=demo)"

    if not smtp_username or '@' not in smtp_username or smtp_username.lower() in ('your_email@gmail.com', 'emailuser'):
        return True, "No valid Gmail address configured in SMTP_USERNAME"

    pwd_lower = smtp_password.lower()
    pwd_upper = smtp_password.upper()
    if not smtp_password or pwd_lower in PLACEHOLDER_PASSWORDS or any(p in pwd_upper for p in ['PASTE_', 'YOUR_', 'PASSWORD', 'APP_PASS']):
        return True, "No 16-character Google App Password configured in SMTP_PASSWORD"

    return False, "Live SMTP credentials detected"


def get_smtp_info():
    """
    Returns current SMTP configuration status for the UI.
    """
    load_dotenv(override=True)
    is_demo, reason = is_demo_mode()
    smtp_username = os.environ.get('SMTP_USERNAME', getattr(Config, 'SMTP_USERNAME', '')).strip()
    smtp_sender = os.environ.get('SMTP_SENDER_EMAIL', getattr(Config, 'SMTP_SENDER_EMAIL', smtp_username or 'info@shreedakshaacademyedu.in')).strip()
    resend_sender = os.environ.get('RESEND_FROM_EMAIL', getattr(Config, 'RESEND_FROM_EMAIL', '')).strip()
    resend_configured = bool(os.environ.get('RESEND_API_KEY', getattr(Config, 'RESEND_API_KEY', '')).strip() and resend_sender)

    return {
        'mode': 'resend' if resend_configured else ('demo' if is_demo else 'smtp'),
        'is_demo': is_demo and not resend_configured,
        'reason': reason,
        'server': os.environ.get('SMTP_SERVER', Config.SMTP_SERVER),
        'port': int(os.environ.get('SMTP_PORT', Config.SMTP_PORT)),
        'username': smtp_username,
        'sender': resend_sender or smtp_sender,
        'has_password': bool(resend_configured or not is_demo)
    }


def _send_via_resend(recipient_email, subject, html_content, attachments=None):
    """Send transactional mail through Resend's HTTPS API without SMTP ports."""
    api_key = os.environ.get('RESEND_API_KEY', getattr(Config, 'RESEND_API_KEY', '')).strip()
    sender = os.environ.get('RESEND_FROM_EMAIL', getattr(Config, 'RESEND_FROM_EMAIL', '')).strip()
    if not api_key or not sender:
        return None

    payload = {
        'from': sender,
        'to': [_sanitize_header_value(recipient_email)],
        'subject': _sanitize_header_value(subject),
        'html': html_content,
    }
    if attachments:
        payload['attachments'] = attachments

    request = urllib.request.Request(
        'https://api.resend.com/emails',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                return True, 'Email delivered through Resend.'
            return False, f'Resend returned HTTP {response.status}.'
    except urllib.error.HTTPError as error:
        detail = error.read().decode('utf-8', errors='replace')[:240]
        print(f'[Resend HTTP Error] {error.code}: {detail}')
        return False, 'Resend rejected the email request.'
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(f'[Resend Connection Error] {error}')
        return False, 'Resend could not be reached; retry delivery later.'


def send_certificate_email(recipient_email, participant_name, event_name, certificate_path, certificate_code, attachment_bytes=None, attachment_filename=None):
    """
    Send an email with the attached Certificate of Participation.
    If credentials are missing or in Demo Mode, safely simulates dispatch with full verification.
    Returns: (success: bool, message: str)
    """
    load_dotenv(override=True)
    is_demo, demo_reason = is_demo_mode()

    clean_recipient = _sanitize_header_value(recipient_email)

    # If in Demo Mode, execute Safe Simulation
    if is_demo:
        print("=" * 60)
        print("[SMTP Safe Demo Mode] Certificate Email Simulated")
        print("=" * 60)
        print(f" - Recipient Email : {clean_recipient}")
        print(f" - Participant Name: {participant_name}")
        print(f" - Event Name      : {event_name}")
        print(f" - Certificate ID  : {certificate_code}")
        print(f" - Attachment File : {certificate_path}")
        print(f" - Reason for Demo : {demo_reason}")
        print("=" * 60)
        return True, f"Certificate successfully dispatched to {clean_recipient}! [Safe Demo Mode: Simulated delivery]"

    # Live Mode - Attempt real Gmail SMTP delivery
    smtp_server = os.environ.get('SMTP_SERVER', Config.SMTP_SERVER)
    smtp_port = int(os.environ.get('SMTP_PORT', Config.SMTP_PORT))
    smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()
    smtp_sender = _sanitize_header_value(os.environ.get('SMTP_SENDER_EMAIL', smtp_username or 'info@shreedakshaacademyedu.in'))
    use_ssl = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't')
    use_tls = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

    try:
        # SEC-03: Escape all dynamic strings before interpolating into HTML email body and sanitize headers
        safe_college_name = escape(str(Config.COLLEGE_NAME))
        safe_college_subtitle = escape(str(Config.COLLEGE_SUBTITLE))
        safe_participant_name = escape(str(participant_name))
        safe_event_name = escape(str(event_name))
        subject_event_name = _sanitize_header_value(event_name)
        subject_line = f"Congratulations! Your Certificate of Participation for {subject_event_name} - Shree Daksha Academy"

        msg = MIMEMultipart('alternative')
        msg['From'] = f"{_sanitize_header_value(Config.COLLEGE_NAME)} <{smtp_sender}>"
        msg['To'] = clean_recipient
        msg['Subject'] = subject_line

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #1e293b; }}
                .email-container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
                .header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: #ffffff; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; }}
                .header p {{ margin: 5px 0 0; opacity: 0.9; font-size: 14px; }}
                .content {{ padding: 30px; line-height: 1.6; font-size: 15px; }}
                .highlight-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 15px; margin: 20px 0; }}
                .badge {{ display: inline-block; background: #2563eb; color: #fff; padding: 4px 10px; border-radius: 4px; font-weight: 600; font-size: 13px; }}
                .btn {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; margin-top: 15px; text-align: center; }}
                .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>{safe_college_name}</h1>
                    <p>{safe_college_subtitle}</p>
                </div>
                <div class="content">
                    <h2>Hello {safe_participant_name},</h2>
                    <p>Thank you for attending <strong>{safe_event_name}</strong>!</p>
                    
                    <div class="highlight-box">
                        <p style="margin: 0 0 8px 0;"><strong>Status:</strong> Verified</p>
                        <p style="margin: 0;"><strong>Issue Date:</strong> {datetime.date.today().strftime('%B %d, %Y')}</p>
                    </div>
                </div>
                <div class="footer">
                    <p>This is an automated notification from Shree Daksha Academy Event Management System.</p>
                    <p>&copy; 2026 {safe_college_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))

        safe_attach_name = re.sub(r'[^A-Za-z0-9._-]+', '_', str(attachment_filename or '')) if attachment_filename else None

        # Attach Certificate File if exists
        if attachment_bytes and safe_attach_name:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={safe_attach_name}"
            )
            msg.attach(part)
        elif certificate_path and os.path.exists(certificate_path):
            with open(certificate_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(certificate_path)}"
            )
            msg.attach(part)

        resend_attachments = []
        if attachment_bytes and safe_attach_name:
            resend_attachments.append({
                'filename': safe_attach_name,
                'content': base64.b64encode(attachment_bytes).decode('ascii'),
            })
        elif certificate_path and os.path.exists(certificate_path):
            with open(certificate_path, 'rb') as attachment:
                resend_attachments.append({
                    'filename': os.path.basename(certificate_path),
                    'content': base64.b64encode(attachment.read()).decode('ascii'),
                })

        resend_result = _send_via_resend(
            clean_recipient,
            subject_line,
            html_content,
            resend_attachments,
        )
        if resend_result is not None:
            return resend_result

        # Dispatch via SMTP
        if smtp_port == 465 or (use_ssl and smtp_port != 587):
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=20)
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=20)
            server.ehlo()
            if use_tls or smtp_port == 587:
                server.starttls()
                server.ehlo()

        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()

        return True, f"Certificate successfully emailed to {clean_recipient} via Gmail SMTP!"

    except smtplib.SMTPAuthenticationError as auth_err:
        print(f"[SMTP Auth Error] {auth_err}")
        return False, 'SMTP authentication failed; configure the provider credentials.'

    except Exception as e:
        print(f"[SMTP Connection Error] {e}")
        return False, 'SMTP delivery failed; the certificate remains queued for retry.'


def format_whatsapp_receipt(participant_name, event_name, payment_method, amount_paid, utr_number=None, registration_uid=None):
    """
    Format a clean, official WhatsApp receipt message for Daksha Udbhav 2026.
    """
    base_url = getattr(Config, 'BASE_URL', 'https://shreedakshaacademyedu.in')
    pass_link = f"{base_url}/payment-status/{registration_uid}" if registration_uid else base_url

    utr_text = f"\n💳 *Transaction / UTR:* {utr_number}" if utr_number else ""
    uid_text = f"\n🆔 *Registration ID:* {registration_uid}" if registration_uid else ""

    message = (
        f"🎓 *SHREE DAKSHA ACADEMY PU COLLEGE*\n"
        f"✨ *Daksha Udbhav 2026 - Official Payment Receipt*\n"
        f"----------------------------------------\n"
        f"✅ *Status:* Confirmed & Verified\n\n"
        f"👤 *Participant:* {participant_name}{uid_text}\n"
        f"🎪 *Event:* {event_name}\n"
        f"💰 *Amount Paid:* ₹{amount_paid}\n"
        f"💵 *Payment Mode:* {payment_method}{utr_text}\n"
        f"📅 *Date:* {datetime.date.today().strftime('%d %B %Y')}\n\n"
        f"🎟️ *Your Gate Pass & Receipt QR:* \n"
        f"{pass_link}\n\n"
        f"📍 *Venue:* No.596, Andrahalli Main Road, Opp. D.Group Layout Arch, Bengaluru - 560091\n\n"
        f"📞 *Event Coordinators:*\n"
        f"• NARASIMHAREDDY Y V: 6362436295\n"
        f"• PREETI P: 79752 87515\n"
        f"----------------------------------------\n"
        f"Keep this receipt and present your Gate Pass at the registration desk upon campus arrival."
    )
    return message


def send_whatsapp_receipt(recipient_phone, participant_name, event_name, payment_method, amount_paid, utr_number=None, registration_uid=None):
    """
    Dispatches a payment receipt to the participant via WhatsApp.
    Supports:
    1. WhatsApp Business Cloud API / Webhook if configured in environment.
    2. Click-to-chat URL (https://wa.me/<phone>?text=...) generation.
    3. Safe Demo Mode simulation when running tests or in development.
    Returns: (success: bool, message: str, wa_url: str)
    """
    load_dotenv(override=True)
    is_demo, demo_reason = is_demo_mode()

    # Clean phone number: keep only digits
    raw_digits = re.sub(r'\D', '', str(recipient_phone or ''))
    if not raw_digits:
        raw_digits = "919980846695"
    elif len(raw_digits) == 10:
        raw_digits = "91" + raw_digits
    elif len(raw_digits) == 11 and raw_digits.startswith('0'):
        raw_digits = "91" + raw_digits[1:]

    receipt_text = format_whatsapp_receipt(
        participant_name=participant_name,
        event_name=event_name,
        payment_method=payment_method,
        amount_paid=amount_paid,
        utr_number=utr_number,
        registration_uid=registration_uid
    )

    wa_url = f"https://wa.me/{raw_digits}?text={urllib.parse.quote(receipt_text)}"

    # Check for direct WhatsApp API integration (Cloud API or Webhook)
    wa_token = os.environ.get('WHATSAPP_API_TOKEN', getattr(Config, 'WHATSAPP_API_TOKEN', '')).strip()
    wa_phone_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', getattr(Config, 'WHATSAPP_PHONE_NUMBER_ID', '')).strip()
    wa_webhook = os.environ.get('WHATSAPP_WEBHOOK_URL', getattr(Config, 'WHATSAPP_WEBHOOK_URL', '')).strip()

    if is_demo or (not wa_token and not wa_webhook):
        print("=" * 60)
        print("[WhatsApp Safe Demo Mode] Receipt Simulated")
        print("=" * 60)
        print(f" - Recipient Phone : +{raw_digits}")
        print(f" - Participant Name: {participant_name}")
        print(f" - Event Name      : {event_name}")
        print(f" - Amount Paid     : ₹{amount_paid}")
        print(f" - Registration ID : {registration_uid or 'N/A'}")
        print(f" - WhatsApp Link   : {wa_url}")
        print("=" * 60)
        return True, f"Receipt dispatched to WhatsApp (+{raw_digits})! [Safe Demo Mode]", wa_url

    # Live Cloud API dispatch
    if wa_token and wa_phone_id:
        try:
            api_url = f"https://graph.facebook.com/v19.0/{wa_phone_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": raw_digits,
                "type": "text",
                "text": {"preview_url": True, "body": receipt_text}
            }
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Authorization": f"Bearer {wa_token}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if 200 <= resp.status < 300:
                    return True, f"Receipt delivered via WhatsApp to +{raw_digits}.", wa_url
        except Exception as e:
            print(f"[WhatsApp API Error] {e}")
            return False, f"WhatsApp delivery failed: {e}", wa_url

    # Live Webhook dispatch
    if wa_webhook:
        try:
            payload = {
                "phone": raw_digits,
                "message": receipt_text,
                "participant_name": participant_name,
                "event_name": event_name,
                "amount_paid": amount_paid,
                "registration_uid": registration_uid,
                "utr_number": utr_number
            }
            req = urllib.request.Request(
                wa_webhook,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if 200 <= resp.status < 300:
                    return True, f"Receipt delivered via WhatsApp webhook to +{raw_digits}.", wa_url
        except Exception as e:
            print(f"[WhatsApp Webhook Error] {e}")
            return False, f"WhatsApp delivery failed: {e}", wa_url

    return True, f"Receipt prepared for WhatsApp (+{raw_digits}).", wa_url


def send_receipt_email(recipient_email, participant_name, event_name, payment_method, amount_paid, utr_number=None, registration_uid=None):
    """
    Send a flawless email receipt for event registration payment.
    Includes registration UID, gate pass link, college branding, and coordinator details.
    """
    load_dotenv(override=True)
    is_demo, demo_reason = is_demo_mode()

    clean_recipient = _sanitize_header_value(recipient_email)

    if is_demo:
        print("=" * 60)
        print("[SMTP Safe Demo Mode] Receipt Email Simulated")
        print("=" * 60)
        print(f" - Recipient Email : {clean_recipient}")
        print(f" - Participant Name: {participant_name}")
        print(f" - Event Name      : {event_name}")
        print(f" - Registration ID : {registration_uid or 'N/A'}")
        print(f" - Amount Paid     : ₹{amount_paid}")
        print(f" - Payment Method  : {payment_method}")
        print(f" - UTR Number      : {utr_number or 'N/A'}")
        print("=" * 60)
        return True, f"Receipt successfully dispatched to {clean_recipient}! [Safe Demo Mode]"

    smtp_server = os.environ.get('SMTP_SERVER', Config.SMTP_SERVER)
    smtp_port = int(os.environ.get('SMTP_PORT', Config.SMTP_PORT))
    smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()
    smtp_sender = _sanitize_header_value(os.environ.get('SMTP_SENDER_EMAIL', smtp_username or 'info@shreedakshaacademyedu.in'))
    use_ssl = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 't')
    use_tls = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 't')

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{_sanitize_header_value(Config.COLLEGE_NAME)} <{smtp_sender}>"
        msg['To'] = clean_recipient
        safe_event_name = escape(str(event_name))
        safe_participant_name = escape(str(participant_name))
        safe_payment_method = escape(str(payment_method))
        safe_utr_number = escape(str(utr_number)) if utr_number else ''
        safe_college_name = escape(str(Config.COLLEGE_NAME))
        safe_uid = escape(str(registration_uid)) if registration_uid else ''
        subject_event_name = _sanitize_header_value(event_name)
        msg['Subject'] = f"Payment Receipt: Registration Confirmed for {subject_event_name} - Shree Daksha Academy"

        base_url = getattr(Config, 'BASE_URL', 'https://shreedakshaacademyedu.in')
        pass_link = f"{base_url}/payment-status/{registration_uid}" if registration_uid else base_url

        payment_details = f"<strong>Payment Mode:</strong> {safe_payment_method}"
        if utr_number:
            payment_details += f"<br><strong>Transaction / UTR:</strong> <code>{safe_utr_number}</code>"

        uid_row = f"""
        <tr>
            <td style="padding: 10px 0; color: #64748b; font-size: 14px; border-bottom: 1px solid #f1f5f9;">Registration ID</td>
            <td style="padding: 10px 0; font-weight: 700; color: #1e3a8a; font-family: monospace; font-size: 15px; text-align: right; border-bottom: 1px solid #f1f5f9;">{safe_uid}</td>
        </tr>
        """ if registration_uid else ""

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; color: #0f172a; }}
                .email-container {{ max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05); }}
                .header {{ background: linear-gradient(135deg, #0b192c 0%, #1e3a8a 100%); color: #ffffff; padding: 36px 30px 28px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; color: #ffffff; }}
                .header .subtitle {{ margin: 6px 0 0; opacity: 0.85; font-size: 12px; letter-spacing: 0.2px; color: #cbd5e1; }}
                .badge {{ display: inline-block; background: #f59e0b; color: #000000; font-size: 11px; font-weight: 800; padding: 4px 12px; border-radius: 9999px; margin-top: 14px; text-transform: uppercase; letter-spacing: 0.5px; }}
                .content {{ padding: 32px 30px; line-height: 1.6; font-size: 15px; }}
                .receipt-card {{ background: #f8fafc; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 20px; margin: 24px 0; }}
                .receipt-table {{ width: 100%; border-collapse: collapse; }}
                .btn-pass {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 14px 28px; border-radius: 10px; font-weight: 700; font-size: 15px; margin: 20px 0 10px; text-align: center; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3); }}
                .coordinators-box {{ background: #eff6ff; border-radius: 10px; padding: 16px; margin-top: 24px; font-size: 13px; color: #1e40af; border: 1px solid #bfdbfe; }}
                .footer {{ background: #f8fafc; padding: 24px 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>{safe_college_name}</h1>
                    <p class="subtitle">Recognized by Govt. of Karnataka | Affiliated to Bangalore University | Approved by AICTE</p>
                    <div class="badge">Official Payment Receipt • Daksha Udbhav 2026</div>
                </div>
                <div class="content">
                    <h2 style="margin: 0 0 12px; font-size: 18px; color: #0f172a;">Dear {safe_participant_name},</h2>
                    <p style="margin: 0 0 18px; color: #334155;">Your registration and payment for <strong>{safe_event_name}</strong> have been successfully verified and confirmed!</p>
                    
                    <div class="receipt-card">
                        <table class="receipt-table">
                            {uid_row}
                            <tr>
                                <td style="padding: 10px 0; color: #64748b; font-size: 14px; border-bottom: 1px solid #f1f5f9;">Event Name</td>
                                <td style="padding: 10px 0; font-weight: 600; color: #0f172a; text-align: right; border-bottom: 1px solid #f1f5f9;">{safe_event_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #64748b; font-size: 14px; border-bottom: 1px solid #f1f5f9;">Amount Paid</td>
                                <td style="padding: 10px 0; font-weight: 800; color: #16a34a; font-size: 18px; text-align: right; border-bottom: 1px solid #f1f5f9;">₹{escape(str(amount_paid))}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #64748b; font-size: 14px; border-bottom: 1px solid #f1f5f9;">Payment Mode</td>
                                <td style="padding: 10px 0; font-weight: 600; color: #334155; text-align: right; border-bottom: 1px solid #f1f5f9;">{safe_payment_method}</td>
                            </tr>
                            {"<tr><td style='padding: 10px 0; color: #64748b; font-size: 14px; border-bottom: 1px solid #f1f5f9;'>Transaction / UTR</td><td style='padding: 10px 0; font-weight: 600; font-family: monospace; color: #334155; text-align: right; border-bottom: 1px solid #f1f5f9;'>" + safe_utr_number + "</td></tr>" if utr_number else ""}
                            <tr>
                                <td style="padding: 10px 0; color: #64748b; font-size: 14px;">Status</td>
                                <td style="padding: 10px 0; font-weight: 700; color: #16a34a; text-align: right;">Verified & Confirmed ✅</td>
                            </tr>
                        </table>
                    </div>

                    <div style="text-align: center;">
                        <a href="{pass_link}" class="btn-pass">🎟️ View & Download Official Gate Pass</a>
                    </div>
                    <p style="text-align: center; margin: 4px 0 20px; font-size: 12px; color: #64748b;">Save or screenshot your Gate Pass QR code for quick check-in upon arrival.</p>

                    <div class="coordinators-box">
                        <strong style="display: block; margin-bottom: 6px;">📞 Event Support & Coordinators:</strong>
                        <span>• Narasimhareddy Y V: <strong>6362436295</strong></span><br>
                        <span>• Preeti P: <strong>79752 87515</strong></span>
                    </div>
                </div>
                <div class="footer">
                    <p style="margin: 0 0 6px;">Venue: No.596, Andrahalli Main Road, Opp. D.Group Layout Arch, Bengaluru – 560091</p>
                    <p style="margin: 0;">&copy; 2026 {safe_college_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))

        resend_result = _send_via_resend(
            clean_recipient,
            f"Payment Receipt: Registration Confirmed for {subject_event_name}",
            html_content,
        )
        if resend_result is not None:
            return resend_result

        if smtp_port == 465 or (use_ssl and smtp_port != 587):
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=20)
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=20)
            server.ehlo()
            if use_tls or smtp_port == 587:
                server.starttls()
                server.ehlo()

        server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()

        return True, f"Receipt successfully emailed to {clean_recipient}!"

    except smtplib.SMTPAuthenticationError as auth_err:
        print(f"[SMTP Auth Error] {auth_err}. Falling back smoothly to Safe Demo Mode.")
        return False, f"SMTP authentication failed for {clean_recipient}."

    except Exception as e:
        print(f"[SMTP Connection Error] {e}.")
        return False, f"SMTP delivery failed: {e}"
