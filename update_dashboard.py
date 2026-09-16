import re

with open('/Users/akash/Documents/manager/templates/admin_dashboard.html', 'r') as f:
    content = f.read()

# 1. Update Export section to include Clear All
old_export = """        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <a href="{{ url_for('export_csv', status='all') }}" class="btn btn-primary">⬇️ All Participants</a>
            <a href="{{ url_for('export_csv', status='approved') }}" class="btn btn-outline-primary" style="border-color: #166534; color: #166534;">⬇️ Approved Only</a>
            <a href="{{ url_for('export_csv', status='pending') }}" class="btn btn-outline-primary" style="border-color: #d97706; color: #d97706;">⬇️ Pending/Unapproved</a>
        </div>"""

new_export = """        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <a href="{{ url_for('export_csv', status='all') }}" class="btn btn-primary">⬇️ All Participants</a>
            <a href="{{ url_for('export_csv', status='approved') }}" class="btn btn-outline-primary" style="border-color: #166534; color: #166534;">⬇️ Approved Only</a>
            <a href="{{ url_for('export_csv', status='pending') }}" class="btn btn-outline-primary" style="border-color: #d97706; color: #d97706;">⬇️ Pending/Unapproved</a>
        </div>
        <hr style="margin: 1.5rem 0; border: none; border-top: 1px dashed var(--border-color);">
        <h4 style="margin-bottom: 0.8rem; color: #ef4444;">Danger Zone</h4>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <button onclick="openClearModal()" class="btn btn-outline-danger" style="border-color: #ef4444; color: #ef4444;">⚠️ Clear All Registrations</button>
        </div>"""

content = content.replace(old_export, new_export)

# 2. Rename Task 2
old_task2 = '<h3 class="table-title" style="color: #10b981;">Task 2: Approved Final Participants ({{ stats.total_approved }} Total)</h3>'
new_task2 = '<h3 class="table-title" style="color: #10b981;">Final Confirmation List (All Approved Participants: {{ stats.total_approved }} Total)</h3>'

content = content.replace(old_task2, new_task2)

# 3. Add Modal at the end of the file
modal_html = """
<!-- Clear All Registrations Modal -->
<div id="clearModal" style="display: none; position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); z-index: 9999; align-items: center; justify-content: center; backdrop-filter: blur(4px);">
    <div style="background: #ffffff; width: 90%; max-width: 500px; border-radius: 16px; padding: 24px 28px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);">
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 14px; margin-bottom: 18px;">
            <h3 style="margin: 0; font-size: 1.25rem; font-weight: 700; color: #ef4444; display: flex; align-items: center; gap: 8px;">
                <span>⚠️</span> Warning: Clear All Data
            </h3>
            <button type="button" onclick="closeClearModal()" style="background: none; border: none; font-size: 1.5rem; line-height: 1; cursor: pointer; color: #64748b;">&times;</button>
        </div>
        <p style="color: #334155; line-height: 1.5; margin-bottom: 1rem;">
            You are about to permanently delete <strong>ALL</strong> registrations, participants, attendance records, and certificates.
        </p>
        <p style="color: #ef4444; font-weight: bold; margin-bottom: 1.5rem;">
            This action cannot be undone!
        </p>
        
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 0.9rem; color: #1e293b; font-weight: 600;">Step 1: Download Backup</p>
            <p style="margin: 5px 0 10px 0; font-size: 0.8rem; color: #64748b;">Please download a CSV backup of all registrations before proceeding.</p>
            <a href="{{ url_for('export_registrations_csv') }}" class="btn btn-outline-primary btn-sm" onclick="enableClearBtn()" style="width: 100%;">⬇️ Download CSV File</a>
        </div>

        <form method="POST" action="{{ url_for('clear_all_registrations') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button type="submit" id="confirmClearBtn" class="btn btn-lg" style="width: 100%; background: #ef4444; color: white; opacity: 0.5; pointer-events: none; border: none;">Delete All Registrations</button>
        </form>
    </div>
</div>

<script>
function openClearModal() {
    const modal = document.getElementById('clearModal');
    if (modal) modal.style.display = 'flex';
}
function closeClearModal() {
    const modal = document.getElementById('clearModal');
    if (modal) modal.style.display = 'none';
    // Reset button state
    document.getElementById('confirmClearBtn').style.opacity = '0.5';
    document.getElementById('confirmClearBtn').style.pointerEvents = 'none';
}
function enableClearBtn() {
    document.getElementById('confirmClearBtn').style.opacity = '1';
    document.getElementById('confirmClearBtn').style.pointerEvents = 'auto';
}
// Close modal on click outside
window.addEventListener('click', function(e) {
    const modal = document.getElementById('clearModal');
    if (e.target === modal) closeClearModal();
});
</script>
"""

content = content.replace('{% endblock %}', modal_html + '\n{% endblock %}')

with open('/Users/akash/Documents/manager/templates/admin_dashboard.html', 'w') as f:
    f.write(content)

print("Updated dashboard HTML")
