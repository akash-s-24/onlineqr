// =========================================================
// EventMate – Interactive Client-side Scripting
// =========================================================

document.addEventListener('DOMContentLoaded', () => {
  // 1. Auto-dismiss alerts after 5 seconds
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      alert.style.transition = 'all 0.4s ease';
      setTimeout(() => alert.remove(), 400);
    }, 5000);
  });

  // 2. Generic Table Live Search
  const searchInput = document.getElementById('tableSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase().trim();
      const tableRows = document.querySelectorAll('table.custom-table tbody tr');
      
      tableRows.forEach(row => {
        const text = row.innerText.toLowerCase();
        if (text.includes(term)) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    });
  }

  // 3. Event Filter Dropdown
  const eventFilter = document.getElementById('eventFilterSelect');
  if (eventFilter) {
    eventFilter.addEventListener('change', (e) => {
      const selectedEvent = e.target.value.toLowerCase().trim();
      const rows = document.querySelectorAll('table.custom-table tbody tr');

      rows.forEach(row => {
        const eventCell = row.getAttribute('data-event-name') || row.innerText;
        if (!selectedEvent || eventCell.toLowerCase().includes(selectedEvent)) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    });
  }

  // 4. Modal Handlers (Certificate Preview)
  window.openCertModal = function(imageSrc, certCode) {
    const modal = document.getElementById('certPreviewModal');
    const modalImg = document.getElementById('modalCertImage');
    const modalTitle = document.getElementById('modalCertTitle');
    const modalDownload = document.getElementById('modalDownloadBtn');

    if (modal && modalImg) {
      modalImg.src = imageSrc;
      if (modalTitle) modalTitle.innerText = `Certificate Preview - ${certCode}`;
      if (modalDownload) modalDownload.href = imageSrc;
      modal.classList.add('active');
    }
  };

  window.closeCertModal = function() {
    const modal = document.getElementById('certPreviewModal');
    if (modal) {
      modal.classList.remove('active');
    }
  };

  // Close modal when clicking outside
  const modalOverlay = document.getElementById('certPreviewModal');
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) {
        closeCertModal();
      }
    });
  }

  // 5. Attendance Toggle AJAX Handler
  window.toggleAttendance = async function(registrationId, currentStatus, buttonElement) {
    const newStatus = (currentStatus === 'present') ? 'absent' : 'present';
    buttonElement.disabled = true;
    const originalText = buttonElement.innerHTML;
    buttonElement.innerHTML = 'Updating...';

    try {
      const response = await fetch('/attendance/toggle', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          registration_id: registrationId,
          status: newStatus
        })
      });

      const data = await response.json();
      if (data.success) {
        // Update UI badge & button
        const row = buttonElement.closest('tr');
        const badge = row.querySelector('.attendance-badge');
        
        if (newStatus === 'present') {
          badge.className = 'badge badge-success attendance-badge';
          badge.innerText = 'PRESENT';
          buttonElement.className = 'btn btn-outline-danger btn-sm';
          buttonElement.innerHTML = 'Mark Absent';
          buttonElement.setAttribute('onclick', `toggleAttendance(${registrationId}, 'present', this)`);

          // Update metric counts
          const presEl = document.getElementById('statPresentCount');
          const absEl = document.getElementById('statAbsentCount');
          if (presEl) presEl.innerText = parseInt(presEl.innerText || '0', 10) + 1;
          if (absEl) absEl.innerText = Math.max(0, parseInt(absEl.innerText || '0', 10) - 1);
        } else {
          badge.className = 'badge badge-danger attendance-badge';
          badge.innerText = 'ABSENT';
          buttonElement.className = 'btn btn-outline-primary btn-sm';
          buttonElement.innerHTML = 'Mark Present';
          buttonElement.setAttribute('onclick', `toggleAttendance(${registrationId}, 'absent', this)`);

          // Update metric counts
          const presEl = document.getElementById('statPresentCount');
          const absEl = document.getElementById('statAbsentCount');
          if (presEl) presEl.innerText = Math.max(0, parseInt(presEl.innerText || '0', 10) - 1);
          if (absEl) absEl.innerText = parseInt(absEl.innerText || '0', 10) + 1;
        }

        // Show toast notification
        showToast(data.message || `Attendance updated to ${newStatus.toUpperCase()}`, 'success');
      } else {
        showToast(data.error || 'Failed to update attendance', 'danger');
        buttonElement.innerHTML = originalText;
      }
    } catch (err) {
      showToast('Network error while updating attendance', 'danger');
      buttonElement.innerHTML = originalText;
    } finally {
      buttonElement.disabled = false;
    }
  };

  // 6. Toast Notification Helper
  window.showToast = function(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.style.position = 'fixed';
      container.style.bottom = '20px';
      container.style.right = '20px';
      container.style.zIndex = '9999';
      container.style.display = 'flex';
      container.style.flexDirection = 'column';
      container.style.gap = '10px';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.minWidth = '280px';
    toast.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.1)';
    toast.innerHTML = `
      <span>${message}</span>
      <button class="alert-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.4s ease';
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  };
});
