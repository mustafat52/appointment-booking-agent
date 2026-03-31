/**
 * MedSchedule AI — Doctor Dashboard
 * doc_dashboard.js
 *
 * ── REAL API ENDPOINTS USED ─────────────────────────────────────────────
 *   GET  /auth/doctor/me                                 → session check
 *   POST /auth/doctor/logout                             → logout
 *   GET  /api/doctor/appointments                        → appointment list
 *   POST /api/doctor/appointments/:id/cancel             → cancel
 *   POST /api/doctor/appointments/:id/reschedule         → reschedule
 *   GET  /api/doctor/whatsapp-qr                         → QR code
 *
 * ── MOCK DATA ───────────────────────────────────────────────────────────
 *   Stats, analytics, and inventory still use mock data.
 *   When your backend endpoints are ready, replace the fetchStats(),
 *   fetchAnalytics(), and fetchInventory() functions below with real
 *   fetch() calls following the same JSON shape.
 * ────────────────────────────────────────────────────────────────────────
 */

"use strict";

/* ═══════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════ */

function showToast(message, type = "success") {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();

  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${type === "success" ? "✓" : "⚠"}</span><span>${message}</span>`;
  document.body.appendChild(t);

  setTimeout(() => {
    t.style.animation = "slideInToast 0.3s ease reverse";
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

function formatDate(d) {
  return new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function todayLabel() {
  return new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function monthLabel() {
  return new Date().toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

function el(id) { return document.getElementById(id); }

/* ═══════════════════════════════════════════════
   AUTH GUARD
   Uses your existing /auth/doctor/me endpoint.
   Redirects to /static/doc_login.html on failure.
═══════════════════════════════════════════════ */

async function ensureLoggedIn() {
  try {
    const res = await fetch("/auth/doctor/me", { credentials: "include" });
    if (!res.ok) {
      window.location.href = "/static/doc_login.html";
      return null;
    }
    return await res.json();
  } catch {
    window.location.href = "/static/doc_login.html";
    return null;
  }
}

/* ═══════════════════════════════════════════════
   REAL API — APPOINTMENTS
   Uses your existing /api/doctor/appointments endpoint.
═══════════════════════════════════════════════ */

async function fetchAppointments() {
  try {
    const res = await fetch("/api/doctor/appointments", { credentials: "include" });
    if (!res.ok) throw new Error("Failed to fetch appointments");
    return await res.json();
  } catch (err) {
    console.warn("[Dashboard] Appointments fetch failed, using mock data:", err.message);
    // Fallback mock so dashboard doesn't break during development
    const today = new Date().toISOString().split("T")[0];
    return [
      { appointment_id:"a1", date:today, time:"09:00", patient_name:"Arjun Mehta",   patient_phone:"9876543210", status:"BOOKED" },
      { appointment_id:"a2", date:today, time:"09:45", patient_name:"Priya Sharma",  patient_phone:"9123456789", status:"BOOKED" },
      { appointment_id:"a3", date:today, time:"10:00", patient_name:"Rohan Nair",    patient_phone:"9988776655", status:"BOOKED" },
      { appointment_id:"a4", date:today, time:"11:00", patient_name:"Sneha Gupta",   patient_phone:"9871234560", status:"BOOKED" },
      { appointment_id:"a5", date:today, time:"14:00", patient_name:"Vikram Iyer",   patient_phone:"9765432100", status:"BOOKED" },
      { appointment_id:"a6", date:today, time:"15:30", patient_name:"Deepa Rao",     patient_phone:"9654321098", status:"BOOKED" },
      { appointment_id:"a7", date:today, time:"16:15", patient_name:"Karthik Das",   patient_phone:null,         status:"CANCELLED" },
      { appointment_id:"a8", date:today, time:"17:00", patient_name:"Ananya Pillai", patient_phone:"9543210987", status:"BOOKED" },
    ];
  }
}

/* ═══════════════════════════════════════════════
   MOCK DATA — Stats, Analytics, Inventory
   Replace each with real fetch() when backend
   endpoints /api/doctor/stats, /api/doctor/analytics,
   /api/doctor/inventory are ready.
═══════════════════════════════════════════════ */

async function fetchStats() {
  // TODO: return await fetch("/api/doctor/stats", { credentials:"include" }).then(r=>r.json());
  return {
    today_count:    8,
    month_count:    143,
    avg_wait_min:   11,
    noshow_rate:    8,
    return_rate:    72,
    satisfaction:   4.7,
    low_stock_count: 3,
  };
}

async function fetchAnalytics() {
  // TODO: return await fetch("/api/doctor/analytics", { credentials:"include" }).then(r=>r.json());
  return {
    monthly_new:       [24,19,34,28,31,22,38,30,26,29,33,21],
    monthly_returning: [68,72,109,94,101,88,112,98,91,96,105,84],
    treatments: {
      Cleaning:48, Filling:36, "Root Canal":22,
      Extraction:19, "X-Ray":31, Whitening:14, Consult:28,
    },
    age_groups: { "0–12":38,"13–17":22,"18–30":84,"31–45":121,"46–60":97,"60+":68 },
    peak_hours: {
      "8am":12,"9am":28,"10am":34,"11am":29,"12pm":15,
      "1pm":8,"2pm":24,"3pm":31,"4pm":27,"5pm":18,
    },
    status_counts:     { Completed:118, Cancelled:13, "No-show":12 },
    weekly_completed:  [6,8,5,9,7,4,2],
    weekly_scheduled:  [0,0,0,0,0,0,6],
  };
}

async function fetchInventory() {
  // TODO: return await fetch("/api/doctor/inventory", { credentials:"include" }).then(r=>r.json());
  return [
    { name:"Lidocaine 2% Cartridges",  category:"Anesthetics",  in_stock:4,   unit:"units",    min_required:20,  spend:8200  },
    { name:"Composite Resin (A2)",      category:"Restorative",  in_stock:2,   unit:"syringes", min_required:10,  spend:5400  },
    { name:"Examination Gloves (S)",    category:"PPE",          in_stock:30,  unit:"pcs",      min_required:200, spend:1200  },
    { name:"Dental Floss Rolls",        category:"Consumables",  in_stock:8,   unit:"rolls",    min_required:25,  spend:800   },
    { name:"Sodium Fluoride Varnish",   category:"Preventive",   in_stock:12,  unit:"ml",       min_required:50,  spend:3100  },
    { name:"Surgical Masks (N95)",      category:"PPE",          in_stock:45,  unit:"pcs",      min_required:100, spend:2200  },
    { name:"Prophy Paste (Mint)",       category:"Consumables",  in_stock:18,  unit:"cups",     min_required:40,  spend:1600  },
    { name:"Dental Mirrors (Disp.)",    category:"Instruments",  in_stock:60,  unit:"pcs",      min_required:100, spend:900   },
    { name:"Articulating Paper",        category:"Restorative",  in_stock:8,   unit:"packs",    min_required:10,  spend:600   },
    { name:"Disposable Bibs",           category:"Consumables",  in_stock:190, unit:"pcs",      min_required:200, spend:1800  },
    { name:"Impression Material",       category:"Restorative",  in_stock:4,   unit:"kits",     min_required:8,   spend:7200  },
    { name:"Sterilization Pouches",     category:"Instruments",  in_stock:200, unit:"pcs",      min_required:150, spend:2400  },
  ];
}

/* ═══════════════════════════════════════════════
   CHART REGISTRY  (prevents double-init on tab switch)
═══════════════════════════════════════════════ */

const _charts = {};

function createChart(id, config) {
  if (_charts[id]) { _charts[id].destroy(); }
  const canvas = el(id);
  if (!canvas) return;
  _charts[id] = new Chart(canvas, config);
}

const CHART_DEFAULTS = {
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false }, ticks: { font: { size: 11 } } },
    y: { grid: { color: "rgba(0,0,0,0.06)" }, ticks: { font: { size: 11 } } },
  },
};

/* ═══════════════════════════════════════════════
   OVERVIEW TAB
═══════════════════════════════════════════════ */

async function renderOverview(doctor) {
  // Date labels across all tabs
  ["todayDate","patientDateBadge","inventoryDateBadge","apptDateBadge"]
    .forEach(id => { if (el(id)) el(id).textContent = todayLabel(); });

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  el("welcomeMessage").textContent = `${greeting}, ${doctor.name ? "Dr. " + doctor.name : ""} 👋`;

  // KPI cards
  const stats = await fetchStats();
  el("ov-today").textContent = stats.today_count;
  el("ov-month").textContent = stats.month_count;
  el("ov-wait").innerHTML    = `${stats.avg_wait_min}<span style="font-size:14px;font-weight:400;color:var(--text-gray)">min</span>`;
  el("ov-stock").textContent  = stats.low_stock_count;
  el("ov-today-delta").textContent = `${stats.today_count > 6 ? "↑" : "↓"} vs yesterday`;
  el("ov-month-delta").textContent = "↑ 12% vs last month";
  el("ov-wait-delta").className    = "mc-delta down";
  el("ov-wait-delta").textContent  = "↓ 3 min vs last week";

  // Low stock alert banner
  if (stats.low_stock_count > 0) {
    el("stockAlertBanner").style.display = "flex";
    el("stockAlertText").innerHTML =
      `<strong>${stats.low_stock_count} supplies are running low</strong> — Switch to the <strong>Inventory</strong> tab to reorder.`;
  }

  // Today's schedule — pulled from the real appointments API
  const appts  = await fetchAppointments();
  const today  = new Date().toISOString().split("T")[0];
  const todayAppts = appts
    .filter(a => a.date === today && a.status !== "CANCELLED")
    .slice(0, 7);

  const now    = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const schedEl = el("ov-schedule");
  schedEl.innerHTML = "";

  let nextFound = false;
  todayAppts.forEach(a => {
    const [h, m] = a.time.split(":").map(Number);
    const apptMin = h * 60 + m;
    const isPast  = apptMin < nowMin;
    const isNext  = !isPast && !nextFound && a.status === "BOOKED";
    if (isNext) nextFound = true;

    const row = document.createElement("div");
    row.className = "appt-row" + (isNext ? " next-up" : "");
    row.innerHTML = `
      <span class="appt-time${isNext ? " highlight" : ""}">${a.time}</span>
      <span class="appt-name">${a.patient_name || "—"}</span>
      <span class="status-pill ${isNext ? "pill-next" : isPast ? "pill-done" : "pill-booked"}">
        ${isNext ? "Next" : isPast ? "Done" : "Booked"}
      </span>`;
    schedEl.appendChild(row);
  });

  if (!todayAppts.length) {
    schedEl.innerHTML = `<div style="color:var(--text-gray);font-size:0.85rem;padding:12px 0;">No appointments scheduled for today.</div>`;
  }

  el("ov-schedule-sub").textContent = `${stats.today_count} appointments today`;

  // Weekly bar chart
  const analytics = await fetchAnalytics();
  createChart("weeklyChart", {
    type: "bar",
    data: {
      labels: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
      datasets: [
        { label:"Completed", data:analytics.weekly_completed, backgroundColor:"#1D9E75", borderRadius:4 },
        { label:"Scheduled", data:analytics.weekly_scheduled, backgroundColor:"#9FE1CB", borderRadius:4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, ...CHART_DEFAULTS,
      scales: {
        x: { stacked:true, grid:{display:false}, ticks:{font:{size:11}} },
        y: { stacked:true, grid:{color:"rgba(0,0,0,0.06)"}, ticks:{font:{size:11}} },
      },
    },
  });
}

/* ═══════════════════════════════════════════════
   PATIENT ANALYTICS TAB
═══════════════════════════════════════════════ */

async function renderPatients() {
  el("patientDateBadge").textContent = monthLabel();

  const stats = await fetchStats();
  el("pa-total").textContent       = "486";
  el("pa-total-delta").textContent = "↑ 34 new this month";
  el("pa-return").innerHTML        = `${stats.return_rate}<span style="font-size:14px;font-weight:400;color:var(--text-gray)">%</span>`;
  el("pa-return-delta").textContent = "↑ 4% vs Q1";
  el("pa-noshow").innerHTML        = `${stats.noshow_rate}<span style="font-size:14px;font-weight:400;color:var(--text-gray)">%</span>`;
  el("pa-noshow-delta").textContent = "↑ 2% — needs attention";
  el("pa-sat").innerHTML           = `${stats.satisfaction}<span style="font-size:14px;font-weight:400;color:var(--text-gray)">/5</span>`;

  const a = await fetchAnalytics();

  // Monthly stacked bar
  createChart("monthlyVisits", {
    type: "bar",
    data: {
      labels: ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
      datasets: [
        { label:"New",       data:a.monthly_new,       backgroundColor:"#1D9E75", borderRadius:4 },
        { label:"Returning", data:a.monthly_returning, backgroundColor:"#9FE1CB", borderRadius:4 },
      ],
    },
    options: {
      responsive:true, maintainAspectRatio:false, ...CHART_DEFAULTS,
      scales: {
        x: { stacked:true, grid:{display:false}, ticks:{font:{size:11}} },
        y: { stacked:true, grid:{color:"rgba(0,0,0,0.06)"}, ticks:{font:{size:11}} },
      },
    },
  });

  // Treatment horizontal bar
  const tLabels = Object.keys(a.treatments);
  const tColors = ["#1D9E75","#3B8BD4","#EF9F27","#E24B4A","#9FE1CB","#FAC775","#B5D4F4"];
  createChart("treatmentChart", {
    type:"bar", indexAxis:"y",
    data: { labels:tLabels, datasets:[{ data:Object.values(a.treatments), backgroundColor:tColors.slice(0,tLabels.length), borderRadius:4 }] },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false} },
      scales: {
        x: { grid:{color:"rgba(0,0,0,0.06)"}, ticks:{font:{size:11}} },
        y: { grid:{display:false}, ticks:{font:{size:11}} },
      },
    },
  });

  // Age distribution bar
  createChart("ageChart", {
    type:"bar",
    data: { labels:Object.keys(a.age_groups), datasets:[{ data:Object.values(a.age_groups), backgroundColor:"#3B8BD4", borderRadius:4 }] },
    options: { responsive:true, maintainAspectRatio:false, ...CHART_DEFAULTS },
  });

  // Status donut
  const sc = a.status_counts;
  const totalStatus = Object.values(sc).reduce((s,v) => s+v, 0);
  el("statusDonutCenter").textContent = totalStatus;
  createChart("statusDonut", {
    type:"doughnut",
    data: {
      labels: Object.keys(sc),
      datasets:[{ data:Object.values(sc), backgroundColor:["#1D9E75","#EF9F27","#E24B4A"], borderWidth:0, hoverOffset:4 }],
    },
    options: { cutout:"68%", responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}} },
  });

  // Peak hours bar
  const phColors = Object.values(a.peak_hours).map(v => v >= 30 ? "#1D9E75" : v >= 20 ? "#9FE1CB" : "#D3D1C7");
  createChart("peakChart", {
    type:"bar",
    data: { labels:Object.keys(a.peak_hours), datasets:[{ data:Object.values(a.peak_hours), backgroundColor:phColors, borderRadius:4 }] },
    options: { responsive:true, maintainAspectRatio:false, ...CHART_DEFAULTS },
  });
}

/* ═══════════════════════════════════════════════
   INVENTORY TAB
═══════════════════════════════════════════════ */

async function renderInventory() {
  el("inventoryDateBadge").textContent = monthLabel();

  const items = await fetchInventory();

  const totalItems    = items.length;
  const criticalItems = items.filter(i => (i.in_stock / i.min_required) < 0.25);
  const lowItems      = items.filter(i => { const r = i.in_stock/i.min_required; return r >= 0.25 && r < 0.5; });
  const totalSpend    = items.reduce((s,i) => s + i.spend, 0);

  el("inv-total").textContent    = totalItems;
  el("inv-total-sub").textContent = `Across ${[...new Set(items.map(i=>i.category))].length} categories`;
  el("inv-low").textContent      = lowItems.length;
  el("inv-critical").textContent = criticalItems.length;
  el("inv-spend").textContent    = `₹${Math.round(totalSpend/1000)}k`;
  el("inv-spend-delta").textContent = "↑ 8% vs last month";
  el("inv-spend-delta").className   = "mc-delta down";

  // Usage line chart
  createChart("usageChart", {
    type:"line",
    data: {
      labels: ["Oct","Nov","Dec","Jan","Feb","Mar"],
      datasets: [
        { label:"Consumables", data:[180,195,210,188,202,215], borderColor:"#1D9E75", backgroundColor:"rgba(29,158,117,0.08)", tension:0.4, fill:true, pointRadius:3 },
        { label:"Anesthetics", data:[88,94,102,90,97,108],     borderColor:"#3B8BD4", backgroundColor:"rgba(59,139,212,0.06)", tension:0.4, fill:true, pointRadius:3 },
        { label:"Restorative", data:[64,70,75,68,71,78],       borderColor:"#EF9F27", backgroundColor:"rgba(239,159,39,0.06)", tension:0.4, fill:true, pointRadius:3 },
        { label:"PPE",         data:[120,134,142,128,136,149], borderColor:"#E24B4A", backgroundColor:"rgba(226,75,74,0.05)",  tension:0.4, fill:true, pointRadius:3 },
      ],
    },
    options: { responsive:true, maintainAspectRatio:false, ...CHART_DEFAULTS },
  });

  // Spend donut
  const spendByCategory = {};
  items.forEach(i => { spendByCategory[i.category] = (spendByCategory[i.category]||0) + i.spend; });
  const catLabels = Object.keys(spendByCategory);
  const catValues = Object.values(spendByCategory);
  const catColors = ["#1D9E75","#3B8BD4","#EF9F27","#E24B4A","#888780","#9FE1CB","#FAC775"];

  el("spendDonutCenter").textContent = `₹${Math.round(totalSpend/1000)}k`;
  createChart("spendDonut", {
    type:"doughnut",
    data: { labels:catLabels, datasets:[{ data:catValues, backgroundColor:catColors.slice(0,catLabels.length), borderWidth:0, hoverOffset:4 }] },
    options: { cutout:"66%", responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}} },
  });

  // Spend legend
  const legendEl = el("spendLegend");
  legendEl.innerHTML = catLabels.map((l,i) => {
    const pct = Math.round(catValues[i]/totalSpend*100);
    return `<span><span class="legend-dot" style="background:${catColors[i]};"></span>${l} ${pct}%</span>`;
  }).join("");

  // Inventory table sorted by urgency (critical first)
  const sorted = [...items].sort((a,b) => (a.in_stock/a.min_required) - (b.in_stock/b.min_required));
  const tbody  = el("inventoryTableBody");
  tbody.innerHTML = sorted.map(item => {
    const ratio = item.in_stock / item.min_required;
    const pct   = Math.min(100, Math.round(ratio * 100));
    let cls, lbl;
    if (ratio < 0.25)     { cls="stock-critical"; lbl=`<span class="stock-label-critical">Critical</span>`; }
    else if (ratio < 0.5) { cls="stock-low";      lbl=`<span class="stock-label-low">Low</span>`; }
    else                  { cls="stock-ok";        lbl=`<span class="stock-label-ok">OK</span>`; }

    return `
      <tr>
        <td><strong>${item.name}</strong></td>
        <td>${item.category}</td>
        <td>${item.in_stock} ${item.unit}</td>
        <td>${item.min_required} ${item.unit}</td>
        <td><div class="stock-bar-wrap"><div class="stock-bar ${cls}" style="width:${pct}%"></div></div></td>
        <td>${lbl}</td>
      </tr>`;
  }).join("");
}

/* ═══════════════════════════════════════════════
   APPOINTMENTS TAB
   Uses the REAL /api/doctor/appointments endpoint.
═══════════════════════════════════════════════ */

let activeAppointmentId = null;

async function renderAppointments() {
  el("apptDateBadge").textContent = todayLabel();
  const appts = await fetchAppointments();
  const tbody = el("appointmentsTableBody");

  if (!appts.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text-gray);">No appointments found.</td></tr>`;
    return;
  }

  tbody.innerHTML = appts.map(a => {
    const isBooked  = a.status === "BOOKED";
    const statusCls = a.status === "BOOKED" ? "pill-booked" : a.status === "CANCELLED" ? "pill-cancel" : "pill-pending";
    return `
      <tr>
        <td>${a.date}</td>
        <td>${a.time}</td>
        <td>${a.patient_name || "—"}</td>
        <td>${a.patient_phone || "—"}</td>
        <td><span class="status-pill ${statusCls}">${a.status}</span></td>
        <td>
          <button class="btn-sm btn-cancel"
            data-id="${a.appointment_id}"
            data-date="${a.date}"
            data-time="${a.time}"
            data-patient="${a.patient_name||""}"
            data-phone="${a.patient_phone||""}"
            ${!isBooked ? "disabled" : ""}>Cancel</button>
          <button class="btn-sm btn-reschedule"
            data-id="${a.appointment_id}"
            data-date="${a.date}"
            data-time="${a.time}"
            data-patient="${a.patient_name||""}"
            data-phone="${a.patient_phone||""}"
            ${!isBooked ? "disabled" : ""}>Reschedule</button>
        </td>
      </tr>`;
  }).join("");
}

/* ═══════════════════════════════════════════════
   MODAL LOGIC
═══════════════════════════════════════════════ */

function openModal(id) {
  el("modalOverlay").style.display = "block";
  el(id).style.display = "block";
}

window.closeModals = function() {
  el("modalOverlay").style.display  = "none";
  el("confirmModal").style.display  = "none";
  el("rescheduleModal").style.display = "none";
  el("rescheduleDate").value = "";
  el("rescheduleTime").value = "";
  activeAppointmentId = null;
};

/* ═══════════════════════════════════════════════
   PAGE SWITCHER
   Renders each tab only once (lazy init).
═══════════════════════════════════════════════ */

const _rendered = {};

window.showPage = function(name, tabEl) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  el("page-" + name).classList.add("active");
  if (tabEl) tabEl.classList.add("active");

  if (!_rendered[name]) {
    _rendered[name] = true;
    if (name === "patients")     renderPatients();
    if (name === "inventory")    renderInventory();
    if (name === "appointments") renderAppointments();
  }
};

/* ═══════════════════════════════════════════════
   WHATSAPP QR
   Uses your existing /api/doctor/whatsapp-qr endpoint.
═══════════════════════════════════════════════ */

function initWhatsApp() {
  const showBtn = el("showQrBtn");
  const qrSec   = el("qrSection");
  if (!showBtn) return;

  showBtn.addEventListener("click", async () => {
    if (!qrSec.classList.contains("hidden")) {
      qrSec.classList.add("hidden");
      showBtn.textContent = "Show QR Code";
      return;
    }
    try {
      const res = await fetch("/api/doctor/whatsapp-qr", { credentials:"include" });
      if (!res.ok) { showToast("Failed to load WhatsApp QR", "error"); return; }
      const data = await res.json();
      el("waLink").href         = data.wa_link;
      el("waLink").textContent  = data.wa_link;
      el("qrImage").src         = `data:image/png;base64,${data.qr_base64}`;
      qrSec.classList.remove("hidden");
      showBtn.textContent = "Hide QR Code";
    } catch {
      showToast("Failed to load WhatsApp QR", "error");
    }
  });

  const dlBtn = el("downloadQrBtn");
  if (dlBtn) {
    dlBtn.addEventListener("click", () => {
      const link = document.createElement("a");
      link.href     = el("qrImage").src;
      link.download = "whatsapp-booking-qr.png";
      link.click();
    });
  }
}

/* ═══════════════════════════════════════════════
   CANCEL / RESCHEDULE
   Uses your existing secure endpoints:
     POST /api/doctor/appointments/:id/cancel
     POST /api/doctor/appointments/:id/reschedule
═══════════════════════════════════════════════ */

document.addEventListener("click", e => {
  if (e.target.classList.contains("btn-cancel") && !e.target.disabled) {
    activeAppointmentId = e.target.dataset.id;
    el("confirmMessage").innerText =
      `Are you sure you want to cancel this appointment?\n\nDate: ${e.target.dataset.date}\nTime: ${e.target.dataset.time}\nPatient: ${e.target.dataset.patient||"—"}\nPhone: ${e.target.dataset.phone||"—"}\n\nThe patient will need to be notified separately.`;
    openModal("confirmModal");
  }

  if (e.target.classList.contains("btn-reschedule") && !e.target.disabled) {
    activeAppointmentId = e.target.dataset.id;
    el("rescheduleInfo").innerText =
      `Current appointment:\nDate: ${e.target.dataset.date}\nTime: ${e.target.dataset.time}\nPatient: ${e.target.dataset.patient||"—"}`;
    el("rescheduleDate").min = new Date().toISOString().split("T")[0];
    openModal("rescheduleModal");
  }
});

el("confirmCancel").onclick = closeModals;

el("confirmOk").onclick = async () => {
  if (!activeAppointmentId) { closeModals(); return; }
  try {
    const res = await fetch(
      `/api/doctor/appointments/${activeAppointmentId}/cancel`,
      { method:"POST", credentials:"include" }
    );
    closeModals();
    if (res.ok) {
      showToast("Appointment cancelled successfully");
      _rendered.appointments = false;
      renderAppointments();
    } else {
      const d = await res.json().catch(()=>({}));
      showToast(d.detail || d.message || "Failed to cancel", "error");
    }
  } catch {
    closeModals();
    showToast("Network error. Please try again.", "error");
  }
};

el("rescheduleCancel").onclick  = closeModals;

el("rescheduleSubmit").onclick = async () => {
  const newDate = el("rescheduleDate").value;
  const newTime = el("rescheduleTime").value;
  if (!newDate || !newTime)  { showToast("Please select both date and time", "error"); return; }
  if (new Date(`${newDate}T${newTime}`) < new Date()) { showToast("Cannot reschedule to a past date/time", "error"); return; }
  if (!activeAppointmentId) { closeModals(); return; }
  try {
    const res = await fetch(
      `/api/doctor/appointments/${activeAppointmentId}/reschedule`,
      {
        method:"POST", credentials:"include",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({ new_date: newDate, new_time: newTime }),
      }
    );
    closeModals();
    if (res.ok) {
      showToast("Appointment rescheduled successfully");
      _rendered.appointments = false;
      renderAppointments();
    } else {
      const d = await res.json().catch(()=>({}));
      showToast(d.detail || d.message || "Failed to reschedule", "error");
    }
  } catch {
    closeModals();
    showToast("Network error. Please try again.", "error");
  }
};

/* ═══════════════════════════════════════════════
   LOGOUT
   Uses your existing POST /auth/doctor/logout endpoint.
═══════════════════════════════════════════════ */

el("logoutBtn").addEventListener("click", async () => {
  try { await fetch("/auth/doctor/logout", { method:"POST", credentials:"include" }); } catch {}
  window.location.href = "/static/doc_login.html";
});

/* ═══════════════════════════════════════════════
   BOOT  — runs once on page load
═══════════════════════════════════════════════ */

(async () => {
  const doctor = await ensureLoggedIn();
  if (!doctor) return;

  // Populate nav doctor badge
  el("doctorName").textContent = doctor.name ? `Dr. ${doctor.name}` : "Doctor";
  const initials = doctor.name
    ? doctor.name.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2)
    : "DR";
  el("doctorAvatar").textContent = initials;

  // Render overview (first tab)
  _rendered.overview = true;
  await renderOverview(doctor);

  // Wire up WhatsApp QR button
  initWhatsApp();
})();
