/* === My Brain — PWA companion app === */

let todayData = null;
let currentTab = "today";
let currentList = null;

// --- Helpers ---

function api(path, opts = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
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

// --- Dashboard (unified feed) ---

async function loadDashboard() {
  const content = $(".content");
  content.innerHTML = '<div class="loading">Loading</div>';

  try {
    const res = await api("/api/feed");
    if (res.status === 401) { show("#login-screen"); return; }
    todayData = await res.json();
    renderDashboard();
  } catch (e) {
    content.innerHTML = '<div class="empty">Could not load data. Pull down to retry.</div>';
  }
}

function renderDashboard() {
  const content = $(".content");

  // Update header
  $(".greeting").textContent = greeting();

  let html = "";

  // Capture bar
  html += `<div class="capture-bar-inline">
    <input type="text" class="capture-input" placeholder="What's on your mind?" autocomplete="off">
    <button class="capture-send" onclick="sendCapture()">↑</button>
  </div>
  <div class="chat-bubble" style="display:none"></div>`;

  // Quick-tap pills (mood / energy / sleep — tap to set)
  html += renderQuickTaps(todayData.quick_taps);

  // Feed items
  const items = todayData.items || [];
  const actionItems = items.filter(i => i.urgency !== "done");
  const doneItems = items.filter(i => i.urgency === "done");

  if (actionItems.length === 0 && doneItems.length === 0) {
    html += `<div class="feed-empty">
      <div class="feed-empty-icon">✨</div>
      <div>All clear for today</div>
    </div>`;
  }

  for (const item of actionItems) {
    html += renderFeedItem(item);
  }

  // Completed today (dimmed)
  if (doneItems.length > 0) {
    html += `<div class="feed-section-label">Done today</div>`;
    for (const item of doneItems) {
      html += renderFeedItem(item);
    }
  }

  // Later section (upcoming items, dimmed)
  const later = todayData.later || [];
  if (later.length > 0) {
    html += `<div class="feed-section-label">Coming up</div>`;
    for (const item of later) {
      html += renderFeedItem({ ...item, urgency: "later" });
    }
  }

  // Add todo at bottom
  html += `<div class="add-todo-row" style="margin-top:16px">
    <input type="text" class="add-todo-input" placeholder="Add a task..." autocomplete="off"
           onkeydown="if(event.key==='Enter')addTodoInline(this)">
    <button class="add-todo-btn" onclick="addTodoInline(this.previousElementSibling)">+</button>
  </div>`;

  content.innerHTML = html;
  bindCaptureInput();
}

// --- Quick-tap pills ---

function renderQuickTaps(taps) {
  const types = [
    { key: "mood", label: "Mood", icon: "😊", max: 10 },
    { key: "energy", label: "Energy", icon: "⚡", max: 10 },
    { key: "sleep", label: "Sleep", icon: "😴", max: 12 },
  ];
  const pills = types.map(t => {
    const val = taps[t.key];
    const filled = val != null;
    const cls = filled ? "qt-pill qt-filled" : "qt-pill";
    const display = filled ? `${t.icon} ${val}` : `${t.icon} ${t.label}`;
    return `<button class="${cls}" onclick="quickTap('${t.key}', ${t.max})">${display}</button>`;
  }).join("");
  return `<div class="quick-taps">${pills}</div>`;
}

async function quickTap(type, max) {
  const val = prompt(`${type} (1-${max}):`);
  if (val === null) return;
  const num = parseFloat(val);
  if (isNaN(num) || num < 1 || num > max) { toast("Invalid value"); return; }

  const res = await api("/api/quicktap", {
    method: "POST",
    body: JSON.stringify({ type, value: num }),
  });
  if (res.ok) {
    toast(`${type}: ${num}`);
    loadDashboard();
  } else {
    toast("Failed to save");
  }
}

// --- Feed item rendering ---

function renderFeedItem(item) {
  if (item.type === "task") return renderFeedTask(item);
  if (item.type === "checkin") return renderFeedCheckin(item);
  if (item.type === "habits") return renderFeedHabits(item);
  return "";
}

function renderFeedTask(item) {
  const done = item.done || item.urgency === "done";
  const urgClass = item.urgency === "overdue" ? "feed-row-overdue"
    : item.urgency === "done" ? "feed-row-done"
    : item.urgency === "later" ? "feed-row-later"
    : "";
  const checkClass = done ? "item-check checked" : "item-check";
  const checkIcon = done ? "✓" : "";
  const textClass = done ? "feed-text done-text" : "feed-text";

  return `<div class="feed-row ${urgClass}">
    <div class="${checkClass}"
         onclick="toggleItem(${item.id}, ${done})">${checkIcon}</div>
    <div class="feed-main">
      <div class="${textClass}">${escHtml(item.text)}</div>
      <div class="feed-detail">${escHtml(item.detail || "")}${item.list_name ? ` · ${escHtml(item.list_name)}` : ""}</div>
    </div>
  </div>`;
}

function renderFeedCheckin(item) {
  const icon = item.checkin_type === "morning" ? "☀️" : "🌙";
  const cardId = item.checkin_type === "morning" ? "morning-card" : "evening-card";
  return `<div class="feed-row feed-row-nudge" onclick="openCheckin('${item.checkin_type}')">
    <div class="feed-nudge-icon">${icon}</div>
    <div class="feed-main">
      <div class="feed-text">${escHtml(item.text)}</div>
      <div class="feed-detail">${escHtml(item.detail || "")}</div>
    </div>
    <div class="feed-nudge-arrow">›</div>
  </div>`;
}

function renderFeedHabits(item) {
  const habitBtns = item.habits.map(h => {
    const streak = h.streak > 0 ? ` ${h.streak}🔥` : "";
    return `<button class="feed-habit-btn" onclick="event.stopPropagation();logHabit('${escAttr(h.name)}')">${escHtml(h.name)}${streak}</button>`;
  }).join("");
  return `<div class="feed-row feed-row-habits">
    <div class="feed-nudge-icon">🔄</div>
    <div class="feed-main">
      <div class="feed-text">${escHtml(item.text)}</div>
      <div class="feed-habit-list">${habitBtns}</div>
    </div>
  </div>`;
}

// --- Checkin sheets ---

let checkinOpen = null;

function openCheckin(type) {
  if (checkinOpen === type) { closeCheckin(); return; }
  checkinOpen = type;
  const existing = $("#checkin-sheet");
  if (existing) existing.remove();

  const sheet = document.createElement("div");
  sheet.id = "checkin-sheet";
  sheet.className = "checkin-sheet";
  sheet.innerHTML = type === "morning" ? morningSheetHTML() : eveningSheetHTML();
  $(".content").insertBefore(sheet, $(".content").firstChild.nextSibling?.nextSibling?.nextSibling || null);
  requestAnimationFrame(() => sheet.classList.add("open"));
}

function closeCheckin() {
  checkinOpen = null;
  const sheet = $("#checkin-sheet");
  if (sheet) {
    sheet.classList.remove("open");
    setTimeout(() => sheet.remove(), 200);
  }
}

function morningSheetHTML() {
  return `<div class="sheet-content">
    <div class="sheet-header">☀️ Morning check-in <button class="sheet-close" onclick="closeCheckin()">✕</button></div>
    <div class="slider-group">
      <div class="slider-label"><span>Mood</span><span class="slider-value" id="mood-val">5</span></div>
      <input type="range" min="1" max="10" value="5" id="mood-slider" oninput="$('#mood-val').textContent=this.value">
    </div>
    <div class="slider-group">
      <div class="slider-label"><span>Energy</span><span class="slider-value" id="energy-val">5</span></div>
      <input type="range" min="1" max="10" value="5" id="energy-slider" oninput="$('#energy-val').textContent=this.value">
    </div>
    <div class="slider-group">
      <div class="slider-label"><span>Sleep (hours)</span><span class="slider-value" id="sleep-val">7</span></div>
      <input type="range" min="0" max="12" step="0.5" value="7" id="sleep-slider" oninput="$('#sleep-val').textContent=this.value">
    </div>
    <div class="slider-group">
      <label class="slider-label"><span>How are you feeling?</span></label>
      <textarea id="morning-notes" placeholder="Slept ok, bit groggy..."></textarea>
    </div>
    <div class="slider-group">
      <label class="slider-label"><span>What do you want to get done today?</span></label>
      <textarea id="morning-intentions" placeholder="One thing per line"></textarea>
    </div>
    <button class="btn btn-primary" onclick="submitMorning()">Save check-in</button>
  </div>`;
}

function eveningSheetHTML() {
  return `<div class="sheet-content">
    <div class="sheet-header">🌙 Evening wrap-up <button class="sheet-close" onclick="closeCheckin()">✕</button></div>
    <div class="slider-group">
      <div class="slider-label"><span>End-of-day mood</span><span class="slider-value" id="eve-mood-val">5</span></div>
      <input type="range" min="1" max="10" value="5" id="eve-mood-slider" oninput="$('#eve-mood-val').textContent=this.value">
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
  </div>`;
}

function bindCaptureInput() {
  const input = $(".capture-input");
  if (input) {
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") sendCapture();
    });
  }
}

async function addTodoInline(input) {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  const res = await api("/api/list/todo/add", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  if (res.ok) {
    toast("Added ✓");
    loadDashboard();
  } else {
    toast("Failed to add");
  }
}

// --- Morning check-in ---

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
    closeCheckin();
    loadDashboard();
  } else {
    toast("Failed to save");
  }
}

// --- Evening wrap-up ---

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
    closeCheckin();
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

// --- Smart input (unified capture + chat + commands) ---

async function sendCapture() {
  const input = $(".capture-input");
  const text = input.value.trim();
  if (!text) return;

  input.value = "";
  const btn = $(".capture-send");
  btn.disabled = true;

  showChatBubble("thinking", text);

  try {
    const res = await api("/api/smart", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    const d = await res.json();
    showChatBubble("reply", d.reply || "Done");

    // Refresh if actions were taken
    if (d.actions_taken && d.actions_taken.length > 0) {
      setTimeout(() => {
        if (currentTab === "today") loadDashboard();
        else if (currentTab === "lists") { if (currentList) openList(currentList); else loadLists(); }
      }, 500);
    }
  } catch {
    showChatBubble("reply", "Network error — try again");
  } finally {
    btn.disabled = false;
  }
}

function showChatBubble(type, text) {
  const bubble = $(".chat-bubble");
  if (!bubble) return;

  if (type === "thinking") {
    bubble.innerHTML = `<div class="chat-q">${escHtml(text)}</div><div class="chat-a thinking">Thinking...</div>`;
    bubble.style.display = "block";
  } else if (type === "reply") {
    const existing = bubble.querySelector(".chat-a");
    if (existing) {
      existing.classList.remove("thinking");
      existing.textContent = text;
    }
    // Auto-dismiss after 10 seconds
    setTimeout(() => { bubble.style.display = "none"; }, 10000);
  }
}

// --- UI helpers ---

function toggleCheckin(id) {
  // Legacy — kept for track view if needed
  const card = document.getElementById(id);
  if (card) card.classList.toggle("open");
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
  } else if (tab === "track") {
    $(".app-header h1").innerHTML = "📊 Track";
    loadTrack();
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

// --- Track view ---

let trackData = null;

async function loadTrack() {
  const content = $(".content");
  content.innerHTML = '<div class="loading">Loading</div>';

  try {
    const res = await api("/api/tracking/overview");
    if (res.status === 401) { show("#login-screen"); return; }
    if (!res.ok) {
      const errText = await res.text();
      console.error("Track API error:", res.status, errText);
      content.innerHTML = `<div class="empty">Error loading tracking (${res.status})</div>`;
      return;
    }
    trackData = await res.json();
    renderTrack();
  } catch (err) {
    console.error("Track load error:", err);
    content.innerHTML = `<div class="empty">Could not load tracking data: ${err.message}</div>`;
  }
}

function renderTrack() {
  const content = $(".content");
  const { day_labels, habits, trackers } = trackData;
  let html = "";

  // Habits section
  if (habits.length > 0) {
    html += `<div class="card">
      <div class="card-header">
        <span class="emoji">🔄</span> Habits
      </div>`;
    for (const h of habits) {
      html += renderHabitTrack(h, day_labels);
    }
    html += `</div>`;
  }

  // Trackers section
  if (trackers.length > 0) {
    html += `<div class="card">
      <div class="card-header">
        <span class="emoji">📈</span> Trackers
      </div>`;
    for (const t of trackers) {
      html += renderTrackerChart(t, day_labels);
    }
    html += `</div>`;
  }

  if (habits.length === 0 && trackers.length === 0) {
    html += '<div class="empty">No habits or trackers yet. Add one below!</div>';
  }

  // Add new section
  html += renderAddTracker();

  content.innerHTML = html;
}

function renderHabitTrack(habit, dayLabels) {
  const streakStr = habit.streak > 0 ? `${habit.streak} 🔥` : "";
  const logBtn = habit.done_today
    ? `<button class="habit-btn logged">✅</button>`
    : `<button class="habit-btn log" onclick="logHabitFromTrack('${escAttr(habit.name)}')">Log</button>`;

  const dots = habit.week.map((val, i) => {
    const filled = val ? "filled" : "";
    const isToday = i === 6 ? "today" : "";
    return `<div class="dot-day">
      <div class="dot ${filled} ${isToday}"></div>
      <span class="dot-label">${dayLabels[i]}</span>
    </div>`;
  }).join("");

  return `<div class="track-row">
    <div class="track-top">
      <span class="track-name">${escHtml(habit.name)}</span>
      <span class="track-streak">${streakStr}</span>
      ${logBtn}
    </div>
    <div class="dot-row">${dots}</div>
  </div>`;
}

function renderTrackerChart(tracker, dayLabels) {
  const vals = tracker.week.map(v => v !== null ? v : 0);
  const maxVal = Math.max(...vals, 1);

  const bars = tracker.week.map((val, i) => {
    if (val === null) {
      return `<div class="bar-day">
        <span class="bar-val"></span>
        <div class="bar empty"></div>
        <span class="bar-label">${dayLabels[i]}</span>
      </div>`;
    }
    const pct = Math.max(10, (val / maxVal) * 100);
    return `<div class="bar-day">
      <span class="bar-val">${val}</span>
      <div class="bar" style="height:${pct}%"></div>
      <span class="bar-label">${dayLabels[i]}</span>
    </div>`;
  }).join("");

  const latestStr = tracker.latest !== null ? tracker.latest : "—";

  return `<div class="track-row">
    <div class="track-top">
      <span class="track-name">${escHtml(tracker.type)}</span>
      <span class="track-latest">${latestStr}</span>
    </div>
    <div class="bar-row">${bars}</div>
  </div>`;
}

function renderAddTracker() {
  return `<div class="add-tracker-card">
    <div class="card-header" style="margin-bottom:8px">
      <span class="emoji">➕</span> Add new
    </div>
    <div class="add-tracker-type">
      <button class="type-btn selected" id="type-habit" onclick="selectTrackerType('habit')">🔄 Habit</button>
      <button class="type-btn" id="type-tracker" onclick="selectTrackerType('tracker')">📈 Tracker</button>
    </div>
    <div class="add-tracker-row">
      <input type="text" class="add-item-input" id="new-tracker-input"
             placeholder="e.g. meditate, read, stretch..."
             onkeydown="if(event.key==='Enter')addNewTracker()">
      <button class="add-item-btn" onclick="addNewTracker()">Add</button>
    </div>
    <div id="tracker-hint" style="font-size:12px;color:var(--text-muted);margin-top:6px">
      Daily yes/no — did you do it today?
    </div>
  </div>`;
}

let newTrackerType = "habit";

function selectTrackerType(type) {
  newTrackerType = type;
  $("#type-habit").classList.toggle("selected", type === "habit");
  $("#type-tracker").classList.toggle("selected", type === "tracker");

  const input = $("#new-tracker-input");
  const hint = $("#tracker-hint");
  if (type === "habit") {
    input.placeholder = "e.g. meditate, read, stretch...";
    hint.textContent = "Daily yes/no — did you do it today?";
  } else {
    input.placeholder = "e.g. mood, sleep, energy...";
    hint.textContent = "Numeric value — log a number each day.";
  }
}

async function addNewTracker() {
  const input = $("#new-tracker-input");
  const name = input.value.trim().toLowerCase();
  if (!name) return;

  if (newTrackerType === "habit") {
    const res = await api("/api/habit", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      toast(`Habit "${name}" created 🔄`);
      input.value = "";
      loadTrack();
    } else {
      const d = await res.json();
      toast(d.error || "Failed to create");
    }
  } else {
    // For trackers, just log a first entry with null to "register" it
    // Or explain that they'll appear once logged
    toast(`Start logging "${name}" via morning check-in or quick capture`);
    input.value = "";
  }
}

async function logHabitFromTrack(name) {
  const res = await api(`/api/habit/${encodeURIComponent(name)}/log`, { method: "POST" });
  if (res.ok) {
    const d = await res.json();
    const streakMsg = d.streak > 1 ? ` — ${d.streak} day streak! 🔥` : "";
    toast(`Logged ${name}${streakMsg}`);
    loadTrack();
  }
}

// --- Deploy ---

async function triggerDeploy() {
  if (!confirm("Pull latest code and reload?")) return;
  const btn = $(".deploy-btn");
  btn.classList.add("spinning");
  toast("Deploying...");

  try {
    const res = await api("/api/deploy", { method: "POST" });
    const d = await res.json();
    toast(d.git || d.message || "Deployed! 🚀");
  } catch {
    toast("Deploy triggered 🚀");
  }

  // Poll until the server is back, then reload
  btn.classList.remove("spinning");
  await waitForServer();
  window.location.reload();
}

async function waitForServer(maxWait = 30000) {
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const res = await fetch("/", { cache: "no-store" });
      if (res.ok) return;
    } catch {}
  }
}

// --- Init ---

document.addEventListener("DOMContentLoaded", () => {
  // Login form
  $(".pin-input").addEventListener("keydown", e => {
    if (e.key === "Enter") doLogin();
  });
  $(".login-btn").addEventListener("click", doLogin);

  // Start
  checkAuth();
});

// --- Service worker registration ---
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
