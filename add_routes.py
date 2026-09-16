import re

with open('/Users/akash/Documents/manager/app.py', 'r') as f:
    content = f.read()

new_routes = """
@app.route('/admin/export/csv')
@admin_required
def export_registrations_csv():
    import csv
    import io
    from flask import Response
    
    # Query all participants/registrations
    records = query_db(\"\"\"
        SELECT r.registration_uid, p.full_name, p.email, p.phone, p.college_name, p.department,
               e.event_name, r.payment_status, r.amount_paid, r.registration_date, r.utr_number
        FROM registrations r
        JOIN participants p ON r.participant_id = p.id
        JOIN events e ON r.event_id = e.id
        ORDER BY r.registration_date DESC
    \"\"\")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Registration UID', 'Full Name', 'Email', 'Phone', 'College', 'Department', 'Event', 'Payment Status', 'Amount Paid', 'Registration Date', 'UTR'])
    
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
"""

# Append just before the if __name__ == '__main__': block
if "if __name__ == '__main__':" in content:
    content = content.replace("if __name__ == '__main__':", new_routes + "\nif __name__ == '__main__':")
else:
    content += new_routes

with open('/Users/akash/Documents/manager/app.py', 'w') as f:
    f.write(content)

print("Added routes to app.py")
