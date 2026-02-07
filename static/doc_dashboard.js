document.addEventListener("DOMContentLoaded", () => {

  // -----------------------------
  // Helper: Show alert notifications
  // -----------------------------
  function showAlert(message, type = 'success') {
    // Remove existing alerts
    const existing = document.querySelector('.alert');
    if (existing) existing.remove();

    const alert = document.createElement('div');
    alert.className = `alert ${type}`;
    alert.innerHTML = `
      <span class="alert-icon">${type === 'success' ? '✓' : '⚠'}</span>
      <span class="alert-message">${message}</span>
    `;
    document.body.appendChild(alert);

    setTimeout(() => {
      alert.style.animation = 'slideIn 0.3s ease reverse';
      setTimeout(() => alert.remove(), 300);
    }, 3000);
  }

  // -----------------------------
  // Auth guard
  // -----------------------------
async function ensureLoggedIn() {
  try {
    const res = await fetch("/auth/doctor/me", {
      credentials: "include"
    });

    if (!res.ok) {
      window.location.href = "/static/doc_login.html";
      return false;
    }

    const doctor = await res.json();

    // ✅ Personalised welcome message
    const welcomeEl = document.getElementById("welcomeMessage");
    if (welcomeEl && doctor.name) {
      welcomeEl.textContent = `Welcome back, Dr. ${doctor.name} 👋`;
    }

    return true;
  } catch (error) {
    console.error("Auth check failed:", error);
    window.location.href = "/static/doc_login.html";
    return false;
  }
}

  // -----------------------------
  // Load appointments
  // -----------------------------
  async function loadAppointments() {
    try {
      const res = await fetch("/api/doctor/appointments", {
        credentials: "include"
      });

      if (!res.ok) {
        if (res.status === 401) {
          window.location.href = "/static/doc_login.html";
          return;
        }
        throw new Error("Failed to load appointments");
      }

      const data = await res.json();
      const tbody = document.getElementById("appointments");

      if (data.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="empty-state">
              <div class="empty-state-icon">📅</div>
              <h3>No Appointments</h3>
              <p>You don't have any upcoming appointments.</p>
            </td>
          </tr>`;
        return;
      }

      tbody.innerHTML = "";

      data.forEach(a => {
        const isBooked = a.status === "BOOKED";
        const statusClass = a.status.toLowerCase();

        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${a.date}</td>
          <td>${a.time}</td>
          <td>${a.patient_name || "-"}</td>
          <td>${a.patient_phone || "-"}</td>
          <td><span class="status-badge ${statusClass}">${a.status}</span></td>
          <td>
            <div class="action-buttons">
              <button 
                class="btn cancel-btn" 
                data-id="${a.appointment_id}"
                data-date="${a.date}"
                data-time="${a.time}"
                data-patient="${a.patient_name || 'No patient'}"
                data-phone="${a.patient_phone || '-'}"
                ${!isBooked ? "disabled" : ""}>
                Cancel
              </button>
              <button 
                class="btn reschedule-btn" 
                data-id="${a.appointment_id}"
                data-date="${a.date}"
                data-time="${a.time}"
                data-patient="${a.patient_name || 'No patient'}"
                data-phone="${a.patient_phone || '-'}"
                ${!isBooked ? "disabled" : ""}>
                Reschedule
              </button>
            </div>
          </td>
        `;
        tbody.appendChild(row);
      });
    } catch (error) {
      console.error("Error loading appointments:", error);
      showAlert("Failed to load appointments. Please try again.", "error");
    }
  }

  // -----------------------------
  // Modal helpers
  // -----------------------------
  let activeAppointmentId = null;

  window.openModal = function(modalId) {
    document.getElementById("modalOverlay").style.display = "block";
    document.getElementById(modalId).style.display = "block";
  }

  window.closeModals = function() {
    document.getElementById("modalOverlay").style.display = "none";
    document.getElementById("confirmModal").style.display = "none";
    document.getElementById("rescheduleModal").style.display = "none";
    
    // Reset form fields
    document.getElementById("rescheduleDate").value = "";
    document.getElementById("rescheduleTime").value = "";
    activeAppointmentId = null;
  }

  // -----------------------------
  // Appointment actions (Cancel / Reschedule)
  // -----------------------------
  document.addEventListener("click", async (e) => {

    // 🗑️ Cancel (open confirm modal)
    if (e.target.classList.contains("cancel-btn") && !e.target.disabled) {
      activeAppointmentId = e.target.dataset.id;
      const date = e.target.dataset.date;
      const time = e.target.dataset.time;
      const patient = e.target.dataset.patient;
      const phone = e.target.dataset.phone;
      document.getElementById("confirmMessage").innerText =
        `Are you sure you want to cancel this appointment?\n\nDate: ${date}\nTime: ${time}\nPatient: ${patient}\nPhone: ${phone}\n\nNote: The patient will need to be notified separately.`;

      openModal("confirmModal");
    }

    // 📝 Reschedule (open reschedule modal)
    if (e.target.classList.contains("reschedule-btn") && !e.target.disabled) {
      activeAppointmentId = e.target.dataset.id;
      const date = e.target.dataset.date;
      const time = e.target.dataset.time;
      const patient = e.target.dataset.patient;
      const phone = e.target.dataset.phone;

      document.getElementById("rescheduleInfo").innerText =
        `Current appointment:\nDate: ${date}\nTime: ${time}\nPatient: ${patient}\nPhone: ${phone}`;

      // Set minimum date to today
      const today = new Date().toISOString().split('T')[0];
      document.getElementById("rescheduleDate").min = today;

      openModal("rescheduleModal");
    }
  });

  // -----------------------------
  // Confirm cancel handlers
  // -----------------------------
  document.getElementById("confirmCancel").onclick = closeModals;

  document.getElementById("confirmOk").onclick = async () => {
    if (!activeAppointmentId) {
      closeModals();
      return;
    }

    try {
      const res = await fetch(
        `/api/doctor/appointments/${activeAppointmentId}/cancel`,
        {
          method: "POST",
          credentials: "include"
        }
      );

      closeModals();

      if (res.ok) {
        showAlert("Appointment cancelled successfully", "success");
        loadAppointments();
      } else {
        const errorData = await res.json().catch(() => ({}));
        showAlert(errorData.message || "Failed to cancel appointment", "error");
      }
    } catch (error) {
      console.error("Error cancelling appointment:", error);
      closeModals();
      showAlert("Failed to cancel appointment. Please try again.", "error");
    }
  };

  // -----------------------------
  // Reschedule handlers
  // -----------------------------
  document.getElementById("rescheduleCancel").onclick = closeModals;

  document.getElementById("rescheduleSubmit").onclick = async () => {
    const newDate = document.getElementById("rescheduleDate").value;
    const newTime = document.getElementById("rescheduleTime").value;

    if (!newDate || !newTime) {
      showAlert("Please select both date and time", "error");
      return;
    }

    if (!activeAppointmentId) {
      closeModals();
      return;
    }

    // Validate date is not in the past
    const selectedDateTime = new Date(`${newDate}T${newTime}`);
    const now = new Date();
    if (selectedDateTime < now) {
      showAlert("Cannot reschedule to a past date/time", "error");
      return;
    }

    try {
      const res = await fetch(
        `/api/doctor/appointments/${activeAppointmentId}/reschedule`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            new_date: newDate,
            new_time: newTime
          })
        }
      );

      closeModals();

      if (res.ok) {
        showAlert("Appointment rescheduled successfully", "success");
        loadAppointments();
      } else {
        const errorData = await res.json().catch(() => ({}));
        showAlert(errorData.message || "Failed to reschedule appointment", "error");
      }
    } catch (error) {
      console.error("Error rescheduling appointment:", error);
      closeModals();
      showAlert("Failed to reschedule appointment. Please try again.", "error");
    }
  };

  // -----------------------------
  // Logout
  // -----------------------------
  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await fetch("/auth/doctor/logout", {
          method: "POST",
          credentials: "include"
        });
      } catch (error) {
        console.error("Logout error:", error);
      } finally {
        window.location.href = "/static/doc_login.html";
      }
    });
  }

  // -----------------------------
  // Boot sequence
  // -----------------------------
  ensureLoggedIn().then(ok => {
    if (ok) {
      loadAppointments();
    }
  });

});