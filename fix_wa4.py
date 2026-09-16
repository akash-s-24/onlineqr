import re

with open('/Users/akash/Documents/manager/templates/member_dashboard.html', 'r') as f:
    content = f.read()

# Make sure WA Cert button uses exact row fields in member dashboard
wa_cert_button = """                            {% if reg.payment_status == 'paid' %}
                                <span class="badge badge-success" style="background-color: #d1fae5; color: #065f46; margin-bottom: 5px; display: inline-block;">Paid (₹{{ reg.amount_paid }})</span><br>
                                <a href="https://wa.me/91{{ reg.phone|replace(' ', '')|replace('+91', '') }}?text=Hello {{ reg.full_name|urlencode }}, your cash payment for {{ reg.event_name|urlencode }} is confirmed! See you at Shree Daksha Academy!" target="_blank" class="btn btn-sm" style="background: #25D366; color: white; padding: 4px 8px; font-size: 0.75rem; text-decoration: none; border-radius: 4px;">📱 WA</a>
                            {% else %}
                                <span class="badge badge-warning" style="background-color: #fef3c7; color: #92400e; margin-bottom: 5px; display: inline-block;">Unpaid</span><br>
                                <a href="https://wa.me/91{{ reg.phone|replace(' ', '')|replace('+91', '') }}?text=Hello {{ reg.full_name|urlencode }}, you are registered for {{ reg.event_name|urlencode }}. Please complete your cash payment at the venue desk to receive your certificate." target="_blank" class="btn btn-sm" style="background: #25D366; color: white; padding: 4px 8px; font-size: 0.75rem; text-decoration: none; border-radius: 4px;">📱 WA Reminder</a>
                            {% endif %}"""

content = re.sub(r"\{\% if reg\.payment_status == 'paid' \%\}.*?\{\% endif \%\}", wa_cert_button, content, flags=re.DOTALL)

with open('/Users/akash/Documents/manager/templates/member_dashboard.html', 'w') as f:
    f.write(content)
