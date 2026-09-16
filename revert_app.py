import re
with open('/Users/akash/Documents/manager/app.py', 'r') as f:
    content = f.read()

# Revert imports
content = content.replace("from mailer import send_certificate_email, get_smtp_info, send_receipt_email, send_whatsapp_receipt, send_sms_receipt", "from mailer import send_certificate_email, get_smtp_info, send_receipt_email")

# Revert automated dispatch in toggle_payment
old_dispatch_block = """    # If marking as paid, get the event fee to update amount_paid
    if new_status == 'paid':
        event_info = query_db("SELECT e.event_fee FROM events e JOIN registrations r ON e.id = r.event_id WHERE r.id = %s", (reg_id,), one=True)
        fee = event_info['event_fee'] if event_info else 0
        execute_db("UPDATE registrations SET payment_status = %s, amount_paid = %s WHERE id = %s", (new_status, fee, reg_id))
        
        # Dispatch automated receipts
        reg_details = query_db(\"\"\"
            SELECT p.full_name, p.email, p.phone, e.event_name, r.payment_method, r.utr_number
            FROM registrations r
            JOIN participants p ON r.participant_id = p.id
            JOIN events e ON r.event_id = e.id
            WHERE r.id = %s
        \"\"\", (reg_id,), one=True)
        
        if reg_details:
            send_receipt_email(reg_details['email'], reg_details['full_name'], reg_details['event_name'], reg_details['payment_method'], fee, reg_details['utr_number'])
            send_whatsapp_receipt(reg_details['phone'], reg_details['full_name'], reg_details['event_name'], fee, reg_details['utr_number'])
            send_sms_receipt(reg_details['phone'], reg_details['full_name'], reg_details['event_name'], fee)
    else:"""

new_dispatch_block = """    # If marking as paid, get the event fee to update amount_paid
    if new_status == 'paid':
        event_info = query_db("SELECT e.event_fee FROM events e JOIN registrations r ON e.id = r.event_id WHERE r.id = %s", (reg_id,), one=True)
        fee = event_info['event_fee'] if event_info else 0
        execute_db("UPDATE registrations SET payment_status = %s, amount_paid = %s WHERE id = %s", (new_status, fee, reg_id))
    else:"""

content = content.replace(old_dispatch_block, new_dispatch_block)

# Revert query change in send_receipt_email_route
content = content.replace("SELECT r.*, p.full_name, p.email, p.phone, e.event_name", "SELECT r.*, p.full_name, p.email, e.event_name")

# Revert send_receipt_email_route logic
old_route_logic = """    success, msg = send_receipt_email(
        recipient_email=reg['email'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number']
    )
    
    send_whatsapp_receipt(
        recipient_phone=reg['phone'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number']
    )
    
    send_sms_receipt(
        recipient_phone=reg['phone'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        amount_paid=reg['amount_paid']
    )"""

new_route_logic = """    success, msg = send_receipt_email(
        recipient_email=reg['email'],
        participant_name=reg['full_name'],
        event_name=reg['event_name'],
        payment_method=reg['payment_method'],
        amount_paid=reg['amount_paid'],
        utr_number=reg['utr_number']
    )"""

content = content.replace(old_route_logic, new_route_logic)

with open('/Users/akash/Documents/manager/app.py', 'w') as f:
    f.write(content)
