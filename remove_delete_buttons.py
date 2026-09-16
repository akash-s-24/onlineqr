import re

# 1. Update attendance.html
with open('/Users/akash/Documents/manager/templates/attendance.html', 'r') as f:
    content = f.read()

# Remove the instruction mentioning the delete button
content = re.sub(r'<span style="font-size: 0\.85rem; color: var\(--text-muted\);">Use <strong>🗑️ Delete</strong> to remove registrations or toggle attendance status</span>', '', content)

# Remove the Delete Symbol Button
delete_btn_pattern = r'<!-- Delete Symbol Button -->.*?<button type="button" class="btn btn-outline-danger btn-sm delete-btn delete-attendance-btn".*?</button>'
content = re.sub(delete_btn_pattern, '', content, flags=re.DOTALL)

with open('/Users/akash/Documents/manager/templates/attendance.html', 'w') as f:
    f.write(content)

# 2. Update participants.html
with open('/Users/akash/Documents/manager/templates/participants.html', 'r') as f:
    content = f.read()

delete_participant_btn_pattern = r'<form method="POST" action="\{\{ url_for\(\'delete_participant\', participant_id=p\.id\) \}\}" onsubmit="return confirm\(\'Are you sure you want to delete this participant and all their event registrations\?\'\);".*?</form>'
content = re.sub(delete_participant_btn_pattern, '', content, flags=re.DOTALL)

with open('/Users/akash/Documents/manager/templates/participants.html', 'w') as f:
    f.write(content)

print("Removed delete buttons")
