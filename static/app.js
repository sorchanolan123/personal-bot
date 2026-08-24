/* === My Brain — PWA companion app === */

const API = "";  // same origin
let data = null;
let currentTab = "today";
let currentList = null;  // when viewing a specific list

// --- Helpers ---

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  return res;
}

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

function show(screenId) {
  $$(".screen").forEach(s => s.classList.remove("active"));
  $(screenId).classList.add("active");
}

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2500);
}

function timeOfDay() {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}

function greeting() {
  const tod = timeOfDay();
  if (tod === "morning") return "Good morning";
  if (tod === "afternoon") return "Good afternoon";
  return "Good evening";
}

// --- Auth ---

async function checkAuth() {
  try {
    const res = await api("/api/auth/check");
    const d = await res.json();
    if (d.authenticated) {
      show("#app-screen");
      loadDashboard();
    } else {
      show("#login-screen");
      $(".pin-input").focus();
    }
  } catch {
    show("#login-screen");
    $(".pin-input").focus();
  }
}

async function doLogin() {
  const pin = $(".pin-input").value;
  if (!pin) return;

  const res = await api("/api/auth", {
    method: "POST",
    body: JSON.stringify({ pin }),
  });

  if (res.ok) {
    show("#app-screen");
    loadDashboard();
  } else {
    $(".pin-input").classList.add("error");
    $(".pin-input").value = "";
    setTimeout(() => $(".pin-input").classList.remove("error"), 600);
  }
}

// --- Dashboard ---

async function loadDashboard() {
  const content = $(".content");
  content.innerHTML = '<div class="loading">Loading</div>';

  try {
    const res = await api("/api/today");
    if (res.status === 401) { show("#login-screen"); return; }
    data = await res.json();
    renderDashboard();
  } catch (e) {
    content.innerHTML = '<div class="empty">Could not load data. Pull down to retry.</div>';
  }
}

function renderDashboard() {
  const content = $(".content");
  const tod = timeOfDay();

  // Update header
  $(".greeting").textContent = greeting();
  $(".pending-badge").textContent = `${data.pending_count} pending`;

  let html = "";

  // Morning check-in card
  html += renderMorningCard(data.morning_done);

  // Overdue items
  if (data.overdue.length > 0) {
    html += `<div class="card" style="border-left: 3px solid #D46B6B">
      <div class="card-header">
        <span class="emoji">🔴</span> Overdue
        <span class="count">${data.overdue.length}</span>
      </div>
      <ul class="item-list">${data.overdue.map(renderItem).join("")}</ul>
    </div>`;
  }

  // Today's focus
  html += `<div class="card">
    <div class="card-header">
      <span class="emoji">🎯</span> Today
      <span class="count">${data.focus.filter(i => !i.done).length} left</span>
    </div>`;
  if (data.focus.length > 0) {
    html += `<ul class="item-list">${data.focus.map(renderItem).join("")}</ul>`;
  } else {
    html += `<div class="empty">Nothing due today</div>`;
  }
  html += `</div>`;

  // Habits
  if (data.habits.length > 0) {
    const done = data.habits.filter(h => h.done).length;
    html += `<div class="card">
      <div class="card-header">
        <span class="emoji">🔄</span> Habits
        <span class="count">${done}/${data.habits.length}</span>
      </div>
      ${data.habits.map(renderHabit).join("")}
    </div>`;
  }

  // Today's tracking summary
  if (data.tracking.length > 0) {
    const nonMeta = data.tracking.filter(t =>
      !["morning_notes", "reflection", "gratitude"].includes(t.type)
    );
    if (nonMeta.length > 0) {
      html += `<div class="card">
        <div class="card-header">
          <span class="emoji">📊</span> Logged today
        </div>
        <div class="tracking-pills">
          ${nonMeta.map(t => `
            <span class="tracking-pill">
              ${t.type}${t.value !== null ? `: <span class="pill-value">${t.value}</span>` : ""}
            </span>
          `).join("")}
        </div>
      </div>`;
    }
  }

  // Evening wrap-up card (show after 5pm)
  if (tod === "evening") {
    html += renderEveningCard();
  }

  content.innerHTML = html;
  bindCardEvents();
}

// --- Morning check-in ---

function renderMorningCard(done) {
  const openClass = done ? "done-card" : "open";
  const icon = done ? "✅" : "☀️";
  const label = done ? "Morning check-in done" : "Morning check-in";

  return `<div class="card checkin-card ${openClass}" id="morning-card">
    <div class="checkin-toggle" onclick="toggleCheckin('morning-card')">
      <div class="card-header" style="margin-bottom:0">
        <span class="emoji">${icon}</span> ${label}
      </div>
      <span class="chevron">▼</span>
    </div>
    <div class="checkin-body">
      <div style="padding-top:14px">
        <div class="slider-group">
          <div class="slider-label">
            <span>Mood</span>
            <span class="slider-value" id="mood-val">5</span>
          </div>
          <input type="range" min="1" max="10" value="5" id="mood-slider"
                 oninput="$('#mood-val').textContent=this.value">
        </div>
        <div class="slider-group">
          <div class="slider-label">
            <span>Energy</span>
            <span class="slider-value" id="energy-val">5</span>
          </div>
          <input type="range" min="1" max="10" value="5" id="energy-slider"
                 oninput="$('#energy-val').textContent=this.value">
        </div>
        <div class="slider-group">
          <div class="slider-label">
            <span>Sleep (hours)</span>
            <span class="slider-value" id="sleep-val">7</span>
          </div>
          <input type="range" min="0" max="12" step="0.5" value="7" id="sleep-slider"
                 oninput="$('#sleep-val').textContent=this.value">
        </div>
        <div class="slider-group">
          <label class="slider-label"><span>How are you feeling?</span></label>
          <textarea id="morning-notes" placeholder="Slept ok, bit groggy..."></textarea>
        </div>
        <div class="slider-group">
          <label class="slider-label"><span>What do you want to get done today?</span></label>
          <textarea id="morning-intentions" placeholder="One thing per line&#10;Call the dentist&#10;Finish the report"></textarea>
        </div>
        <button class="btn btn-primary" onclick="submitMorning()">Save check-in</button>
      </div>
    </div>
  </div>`;
}

async function submitMorning() {
  const mood = parseFloat($("#mood-slider").value);
  const energy = parseFloat($("#energy-slider").value);
  const sleep = parseFloat($("#sleep-slider").value);
  const notes = $("#morning-notes").value.trim();
  const intentionsRaw = $("#morning-intentions").value.trim();
  const intentions = intentionsRaw ? intentionsRaw.split("\n").filter(l => l.trim()) : [];

  const res = await api("/api/checkin/morning", {
    method: "POST",
    body: JSON.stringify({ mood, energy, sleep, notes, mood_notes: notes, intentions }),
  });

  if (res.ok) {
    toast("Morning check-in saved ☀️");
    loadDashboard();
  } else {
    toast("Failed to save");
  }
}

// --- Evening wrap-up ---

function renderEveningCard() {
  const hasReflection = data.tracking.some(t => t.type === "reflection");
  const openClass = hasReflection ? "done-card" : "";
  const icon = hasReflection ? "✅" : "🌙";
  const label = hasReflection ? "Evening wrap-up done" : "Evening wrap-up";

  // Summary of the day
  const doneCount = data.focus.filter(i => i.done).length;
  const totalFocus = data.focus.length;
  const habitsLogged = data.habits.filter(h => h.done).length;
  const totalHabits = data.habits.length;

  return `<div class="card checkin-card ${openClass}" id="evening-card">
    <div class="checkin-toggle" onclick="toggleCheckin('evening-card')">
      <div class="card-header" style="margin-bottom:0">
        <span class="emoji">${icon}</span> ${label}
      </div>
      <span class="chevron">▼</span>
    </div>
    <div class="checkin-body">
      <div style="padding-top:14px">
        <div style="margin-bottom:14px;font-size:14px;color:var(--text-secondary)">
          Today: ${doneCount}/${totalFocus} tasks done, ${habitsLogged}/${totalHabits} habits logged
        </div>
        <div class="slider-group">
          <div class="slider-label">
            <span>End-of-day mood</span>
            <span class="slider-value" id="eve-mood-val">5</span>
          </div>
          <input type="range" min="1" max="10" value="5" id="eve-mood-slider"
                 oninput="$('#eve-mood-val').textContent=this.value">
        </div>
        <div class="slider-group">
          <label class="slider-label"><span>How did today go?</span></label>
          <textarea id="eve-reflection" placeholder="What went well? What was hard?"></textarea>
        </div>
        <div class="slider-group">
          <label class="slider-label"><span>One thing you're grateful for</span></label>
          <input type="text" class="text-input" id="eve-gratitude" placeholder="Anything at all...">
        </div>
        <button class="btn btn-primary" onclick="submitEvening()">Save wrap-up</button>
      </div>
    </div>
  </div>`;
}

async function submitEvening() {
  const mood = parseFloat($("#eve-mood-slider").value);
  const reflection = $("#eve-reflection").value.trim();
  const gratitude = $("#eve-gratitude").value.trim();

  const res = await api("/api/checkin/evening", {
    method: "POST",
    body: JSON.stringify({ mood, reflection, gratitude }),
  });

  if (res.ok) {
    toast("Evening wrap-up saved 🌙");
    loadDashboard();
  } else {
    toast("Failed to save");
  }
}

// --- Items ---

function renderItem(item) {
  const checked = item.done ? "checked" : "";
  const textClass = item.done ? "done-text" : "";
  const checkIcon = item.done ? "✓" : "";

  let dueBadge = "";
  if (item.due_date && !item.done) {
    const today = new Date().toISOString().slice(0, 10);
    const isOverdue = item.due_date < today;
    const cls = isOverdue ? "item-due item-overdue" : "item-due";
    dueBadge = `<span class="${cls}">${item.due_date}</span>`;
  }

  return `<li class="item-row">
    <div class="item-check ${checked}"
         onclick="toggleItem(${item.id}, ${item.done})">${checkIcon}</div>
    <div>
      <div class="item-text ${textClass}">${escHtml(item.text)}${dueBadge}</div>
      <div class="item-meta">${item.list_name}</div>
    </div>
  </li>`;
}

async function toggleItem(id, currentDone) {
  const action = currentDone ? "undone" : "done";
  const res = await api(`/api/item/${id}/${action}`, { method: "POST" });
  if (res.ok) {
    toast(currentDone ? "Restored" : "Done! ✅");
    loadDashboard();
  }
}

// --- Habits ---

function renderHabit(habit) {
  const btnClass = habit.done ? "habit-btn logged" : "habit-btn log";
  const btnText = habit.done ? "✅ Done" : "Log";
  const onclick = habit.done ? "" : `onclick="logHabit('${escAttr(habit.name)}')"`;
  const streak = habit.streak > 0 ? `<span class="habit-streak">${habit.streak} 🔥</span>` : "";

  return `<div class="habit-row">
    <span class="habit-name">${escHtml(habit.name)}</span>
    ${streak}
    <button class="${btnClass}" ${onclick}>${btnText}</button>
  </div>`;
}

async function logHabit(name) {
  const res = await api(`/api/habit/${encodeURIComponent(name)}/log`, { method: "POST" });
  if (res.ok) {
    const d = await res.json();
    const streakMsg = d.streak > 1 ? ` — ${d.streak} day streak! 🔥` : "";
    toast(`Logged ${name}${streakMsg}`);
    loadDashboard();
  }
}

// --- Quick capture ---

async function sendCapture() {
  const input = $(".capture-input");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  const btn = $(".capture-send");
  btn.disabled = true;

  try {
    const res = await api("/api/capture", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      const d = await res.json();
      toast(d.result || "Captured ✓");
      loadDashboard();
    } else {
      toast("Failed to capture");
    }
  } catch {
    toast("Network error");
  } finally {
    btn.disabled = false;
  }
}

// --- UI helpers ---

function toggleCheckin(id) {
  const card = document.getElementById(id);
  card.classList.toggle("open");
}

function bindCardEvents() {
  // Nothing extra needed — events are inline for simplicity
}

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function escAttr(s) {
  return s.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// --- Tab switching ---

function switchTab(tab) {
  currentTab = tab;
  currentList = null;
  $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));

  if (tab === "today") {
    $(".app-header h1").innerHTML = `<span class="greeting">${greeting()}</span> 🧠`;
    loadDashboard();
  } else if (tab === "lists") {
    $(".app-header h1").innerHTML = "📋 Lists";
    loadLists();
  }
}

// --- Lists view ---

async function loadLists() {
  const content = $(".content");
  content.innerHTML = '<div class="loading">Loading</div>';

  try {
    const res = await api("/api/lists");
    if (res.status === 401) { show("#login-screen"); return; }
    const lists = await res.json();
    renderLists(lists);
  } catch {
    content.innerHTML = '<div class="empty">Could not load lists.</div>';
  }
}

function renderLists(lists) {
  const content = $(".content");

  if (lists.length === 0) {
    content.innerHTML = '<div class="empty">No lists yet. Create one via Telegram with /newlist</div>';
    return;
  }

  const html = lists.map(l => `
    <div class="list-card" onclick="openList('${escAttr(l.name)}')">
      <span class="list-card-icon">📋</span>
      <div class="list-card-info">
        <div class="list-card-name">${escHtml(l.name)}</div>
        ${l.description ? `<div class="list-card-desc">${escHtml(l.description)}</div>` : ""}
      </div>
      <span class="list-card-count">${l.pending}</span>
      <span class="list-card-arrow">›</span>
    </div>
  `).join("");

  content.innerHTML = html;
}

// --- List detail view ---

async function openList(name) {
  currentList = name;
  const content = $(".content");
  content.innerHTML = '<div class="loading">Loading</div>';
  $(".app-header h1").innerHTML = `📋 ${escHtml(name)}`;

  try {
    const res = await api(`/api/list/${encodeURIComponent(name)}`);
    if (res.status === 401) { show("#login-screen"); return; }
    const items = await res.json();
    renderListDetail(name, items);
  } catch {
    content.innerHTML = '<div class="empty">Could not load list.</div>';
  }
}

function renderListDetail(name, items) {
  const content = $(".content");
  const pending = items.filter(i => !i.done);
  const done = items.filter(i => i.done);

  let html = `
    <div class="list-detail-header">
      <button class="back-btn" onclick="backToLists()">←</button>
      <span class="list-detail-title">${escHtml(name)}</span>
      <span class="pending-badge" style="font-size:12px">${pending.length} pending</span>
    </div>
    <div class="add-item-row">
      <input type="text" class="add-item-input" placeholder="Add an item..."
             onkeydown="if(event.key==='Enter')addItemToList('${escAttr(name)}')">
      <button class="add-item-btn" onclick="addItemToList('${escAttr(name)}')">Add</button>
    </div>
  `;

  if (pending.length > 0) {
    html += `<div class="card">
      <ul class="item-list">${pending.map(i => renderListItem(i, name)).join("")}</ul>
    </div>`;
  }

  if (done.length > 0) {
    html += `<div class="section-label">Completed</div>
    <div class="card" style="opacity:0.7">
      <ul class="item-list">${done.map(i => renderListItem(i, name)).join("")}</ul>
    </div>`;
  }

  if (items.length === 0) {
    html += '<div class="empty">This list is empty. Add something above!</div>';
  }

  content.innerHTML = html;
}

function renderListItem(item, listName) {
  const checked = item.done ? "checked" : "";
  const textClass = item.done ? "done-text" : "";
  const checkIcon = item.done ? "✓" : "";

  let dueBadge = "";
  if (item.due_date && !item.done) {
    const today = new Date().toISOString().slice(0, 10);
    const isOverdue = item.due_date < today;
    const cls = isOverdue ? "item-due item-overdue" : "item-due";
    dueBadge = ` <span class="${cls}">${item.due_date}</span>`;
  }

  return `<li class="item-row" id="item-${item.id}">
    <div class="item-check ${checked}"
         onclick="toggleListItem(${item.id}, ${item.done}, '${escAttr(listName)}')">${checkIcon}</div>
    <div class="item-text ${textClass}" id="item-text-${item.id}">${escHtml(item.text)}${dueBadge}</div>
    <div class="item-actions">
      ${!item.done ? `<button class="item-action-btn" onclick="startEdit(${item.id}, '${escAttr(item.text)}')" title="Edit">✏️</button>` : ""}
      <button class="item-action-btn" onclick="deleteItem(${item.id}, '${escAttr(listName)}')" title="Delete">🗑️</button>
    </div>
  </li>`;
}

async function toggleListItem(id, currentDone, listName) {
  const action = currentDone ? "undone" : "done";
  const res = await api(`/api/item/${id}/${action}`, { method: "POST" });
  if (res.ok) {
    toast(currentDone ? "Restored" : "Done! ✅");
    openList(listName);
  }
}

async function addItemToList(name) {
  const input = $(".add-item-input");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  const res = await api(`/api/list/${encodeURIComponent(name)}/add`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });

  if (res.ok) {
    const d = await res.json();
    const dueMsg = d.due_date ? ` (due ${d.due_date})` : "";
    toast(`Added: ${d.text}${dueMsg}`);
    openList(name);
  } else {
    toast("Failed to add");
  }
}

function startEdit(itemId, currentText) {
  const textEl = document.getElementById(`item-text-${itemId}`);
  if (!textEl) return;
  const row = document.getElementById(`item-${itemId}`);
  const actionsEl = row.querySelector(".item-actions");
  actionsEl.style.display = "none";

  textEl.innerHTML = `<div class="edit-row">
    <input type="text" class="edit-input" id="edit-input-${itemId}" value="${escAttr(currentText)}"
           onkeydown="if(event.key==='Enter')saveEdit(${itemId});if(event.key==='Escape')cancelEdit(${itemId},'${escAttr(currentText)}')">
    <button class="edit-save" onclick="saveEdit(${itemId})">✓</button>
    <button class="edit-cancel" onclick="cancelEdit(${itemId},'${escAttr(currentText)}')">✕</button>
  </div>`;

  const editInput = document.getElementById(`edit-input-${itemId}`);
  editInput.focus();
  editInput.select();
}

async function saveEdit(itemId) {
  const input = document.getElementById(`edit-input-${itemId}`);
  if (!input) return;
  const newText = input.value.trim();
  if (!newText) return;

  const res = await api(`/api/item/${itemId}/edit`, {
    method: "POST",
    body: JSON.stringify({ text: newText }),
  });

  if (res.ok) {
    toast("Updated ✏️");
    if (currentList) openList(currentList);
  } else {
    toast("Failed to update");
  }
}

function cancelEdit(itemId, originalText) {
  if (currentList) openList(currentList);
}

async function deleteItem(itemId, listName) {
  const res = await api(`/api/item/${itemId}`, { method: "DELETE" });
  if (res.ok) {
    toast("Deleted 🗑️");
    openList(listName);
  } else {
    toast("Failed to delete");
  }
}

function backToLists() {
  currentList = null;
  $(".app-header h1").innerHTML = "📋 Lists";
  loadLists();
}

// --- Refresh ---

async function refresh() {
  const btn = $(".refresh-btn");
  btn.classList.add("spinning");
  if (currentTab === "today") {
    await loadDashboard();
  } else if (currentList) {
    await openList(currentList);
  } else {
    await loadLists();
  }
  setTimeout(() => btn.classList.remove("spinning"), 600);
}

// --- Init ---

document.addEventListener("DOMContentLoaded", () => {
  // Login form
  $(".pin-input").addEventListener("keydown", e => {
    if (e.key === "Enter") doLogin();
  });
  $(".login-btn").addEventListener("click", doLogin);

  // Capture bar
  $(".capture-input").addEventListener("keydown", e => {
    if (e.key === "Enter") sendCapture();
  });
  $(".capture-send").addEventListener("click", sendCapture);

  // Refresh
  $(".refresh-btn").addEventListener("click", refresh);

  // Start
  checkAuth();
});

// --- Service worker registration ---
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
