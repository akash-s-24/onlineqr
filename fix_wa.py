import re

with open('/Users/akash/Documents/manager/templates/certificates.html', 'r') as f:
    content = f.read()

# Make sure WA Cert button uses exact row fields
wa_cert_button = """                            <!-- Send WA Cert Button -->
                            {% set wa_msg = "Hello " ~ row.full_name ~ ",\\n\\nCongratulations on completing the event *" ~ row.event_name ~ "*!\\nYour official Certificate of Participation is now available. You can download and verify it here: " ~ url_for('verify_certificate', cert_code=row.certificate_code, _external=True) %}
                            <a href="https://wa.me/91{{ row.phone|replace(' ', '')|replace('+91', '') }}?text={{ wa_msg | urlencode }}" target="_blank" class="btn btn-success btn-sm" style="background-color: #25D366; border-color: #25D366;">📱 WA Cert</a>"""

content = re.sub(r"<!-- Send WA Cert Button -->.*?</a>", wa_cert_button, content, flags=re.DOTALL)

with open('/Users/akash/Documents/manager/templates/certificates.html', 'w') as f:
    f.write(content)
