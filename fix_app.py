import re

with open('/Users/akash/Documents/manager/app.py', 'r') as f:
    content = f.read()

# Make sure member_dashboard gets phone numbers too just in case
old_query = """        SELECT r.id as registration_id, r.registration_uid, r.payment_status, r.amount_paid, r.payment_method, r.team_name, r.status as approval_status, r.utr_number,
               p.full_name, p.email, p.college_name, p.department, e.event_name"""

new_query = """        SELECT r.id as registration_id, r.registration_uid, r.payment_status, r.amount_paid, r.payment_method, r.team_name, r.status as approval_status, r.utr_number,
               p.full_name, p.email, p.phone, p.college_name, p.department, e.event_name"""

content = content.replace(old_query, new_query)

with open('/Users/akash/Documents/manager/app.py', 'w') as f:
    f.write(content)
