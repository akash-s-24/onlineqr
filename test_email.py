from mailer import send_receipt_email
print("Attempting to send email...")
success, msg = send_receipt_email('levelupgamerz28@gmail.com', 'Akash', 'Tech Quiz', 250, 'REG-TEST-999')
print(f"Success: {success}")
print(f"Message: {msg}")
