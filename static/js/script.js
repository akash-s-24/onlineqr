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

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('.cert-preview-trigger');
    if (!trigger) return;
    openCertModal(trigger.dataset.imageSrc, trigger.dataset.certCode);
  });

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
          'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
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
          buttonElement.className = 'candy-btn candy-btn-warning';
          buttonElement.style.padding = '0.4rem 1rem';
          buttonElement.style.fontSize = '0.85rem';
          buttonElement.style.borderRadius = '6px';
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
          buttonElement.className = 'candy-btn candy-btn-success';
          buttonElement.style.padding = '0.4rem 1rem';
          buttonElement.style.fontSize = '0.85rem';
          buttonElement.style.borderRadius = '6px';
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

    // Limit to 3 toasts
    if (container.children.length >= 3) {
      container.removeChild(container.firstChild);
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.minWidth = '280px';
    toast.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.1)';
    toast.style.transform = 'translateY(20px)';
    toast.style.opacity = '0';
    toast.style.transition = 'all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
    toast.innerHTML = `
      <span>${message}</span>
      <button class="alert-close" onclick="this.parentElement.style.opacity='0'; setTimeout(()=>this.parentElement.remove(), 400);">&times;</button>
    `;

    container.appendChild(toast);
    
    // Animate in
    requestAnimationFrame(() => {
      toast.style.transform = 'translateY(0)';
      toast.style.opacity = '1';
    });

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  };

  // 7. Global Loading Overlay
  window.showGlobalLoading = function(message = 'Processing...') {
    let loader = document.getElementById('globalLoader');
    if (!loader) {
      loader = document.createElement('div');
      loader.id = 'globalLoader';
      loader.style.position = 'fixed';
      loader.style.top = '0';
      loader.style.left = '0';
      loader.style.width = '100vw';
      loader.style.height = '100vh';
      loader.style.background = 'rgba(255, 255, 255, 0.7)';
      loader.style.backdropFilter = 'blur(8px)';
      loader.style.zIndex = '10000';
      loader.style.display = 'flex';
      loader.style.flexDirection = 'column';
      loader.style.justifyContent = 'center';
      loader.style.alignItems = 'center';
      loader.style.opacity = '0';
      loader.style.transition = 'opacity 0.3s ease';
      
      loader.innerHTML = `
        <div class="spinner" style="width: 50px; height: 50px; border: 4px solid rgba(37, 99, 235, 0.2); border-top-color: #2563eb; border-radius: 50%; animation: spin 1s linear infinite;"></div>
        <p id="globalLoaderText" style="margin-top: 15px; font-weight: 600; color: #1e293b; font-size: 1.1rem; letter-spacing: 0.5px;">${message}</p>
        <style>@keyframes spin { to { transform: rotate(360deg); } }</style>
      `;
      document.body.appendChild(loader);
    } else {
      document.getElementById('globalLoaderText').innerText = message;
      loader.style.display = 'flex';
    }
    
    requestAnimationFrame(() => {
      loader.style.opacity = '1';
    });
  };

  window.hideGlobalLoading = function() {
    const loader = document.getElementById('globalLoader');
    if (loader) {
      loader.style.opacity = '0';
      setTimeout(() => {
        loader.style.display = 'none';
      }, 300);
    }
  };
});
