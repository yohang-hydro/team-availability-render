const days = window.DAYS;
const slots = window.SLOTS;

const nameEl = document.querySelector("#name");
const startBtn = document.querySelector("#start");
const saveBtn = document.querySelector("#save");
const clearBtn = document.querySelector("#clear");
const refreshBtn = document.querySelector("#refresh");
const gridEl = document.querySelector("#grid");
const overlapEl = document.querySelector("#overlap");
const statusEl = document.querySelector("#status");
const needNameEl = document.querySelector("#need-name");
const responsesEl = document.querySelector("#responses");
const pendingEl = document.querySelector("#pending");

let selected = new Set();
let dragging = false;
let dragMode = true;
let startedName = "";
let busy = false;

const key = (day, slot) => `${day}|${slot}`;
const currentName = () => nameEl.value.trim();
const hasName = () => !!currentName();
const canSelectTimes = () => hasName() && currentName() === startedName;

function setStatus(message) {
  statusEl.textContent = message;
}

function updateNameGate() {
  const ok = canSelectTimes();
  startBtn.disabled = !hasName() || busy;
  saveBtn.disabled = !ok || busy;
  clearBtn.disabled = !ok || busy;
  gridEl.classList.toggle("locked", !ok);
  needNameEl.hidden = ok;
  if (!ok) {
    needNameEl.textContent = startedName && hasName()
      ? "Name changed. Click Start selecting times again."
      : "Enter your name, then click Start selecting times.";
  }
}

function makeGrid(el, overlap = null) {
  el.innerHTML = "";

  const timezone = document.createElement("div");
  timezone.className = "head tz-head";
  timezone.textContent = "AEST";
  el.appendChild(timezone);

  days.forEach((day) => {
    const heading = document.createElement("div");
    heading.className = "head";
    heading.textContent = day;
    el.appendChild(heading);
  });

  slots.forEach((slot) => {
    const time = document.createElement("div");
    time.className = "time";
    time.textContent = formatSlot(slot);
    el.appendChild(time);

    days.forEach((day) => {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.day = day;
      cell.dataset.slot = slot;

      if (overlap) {
        const count = overlap.counts[day][slot];
        const total = overlap.responses;
        const alpha = total ? 0.1 + (0.8 * count) / total : 0.05;
        const label = document.createElement("span");
        label.textContent = `${count}/${total || 0}`;

        cell.classList.add("overlap");
        cell.appendChild(label);
        cell.style.background = `rgba(36, 52, 71, ${alpha})`;
        cell.style.color = count / Math.max(total, 1) > 0.45 ? "white" : "#243447";
        cell.title = (overlap.names[day][slot] || []).join(", ")
          || "No submitted participant available";
      } else if (selected.has(key(day, slot))) {
        cell.classList.add("selected");
      }

      el.appendChild(cell);
    });
  });
}

function selectableCellFromPoint(clientX, clientY) {
  const node = document.elementFromPoint(clientX, clientY);
  const cell = node && node.closest(".cell");
  if (!cell || !gridEl.contains(cell) || cell.classList.contains("overlap")) {
    return null;
  }
  return cell;
}

function apply(cell) {
  if (!canSelectTimes()) return;
  const cellKey = key(cell.dataset.day, cell.dataset.slot);
  if (dragMode) {
    selected.add(cellKey);
  } else {
    selected.delete(cellKey);
  }
  cell.classList.toggle("selected", dragMode);
}

gridEl.addEventListener("pointerdown", (event) => {
  if (!canSelectTimes() || busy || event.button) return;
  const cell = event.target.closest(".cell");
  if (!cell || cell.classList.contains("overlap")) return;
  event.preventDefault();
  dragging = true;
  dragMode = !selected.has(key(cell.dataset.day, cell.dataset.slot));
  apply(cell);
  gridEl.setPointerCapture(event.pointerId);
});

gridEl.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  const cell = selectableCellFromPoint(event.clientX, event.clientY);
  if (cell) apply(cell);
});

function stopDragging() {
  dragging = false;
}

gridEl.addEventListener("pointerup", stopDragging);
gridEl.addEventListener("pointercancel", stopDragging);

function addMinutes(time, mins) {
  const [hour, minute] = time.split(":").map(Number);
  const total = hour * 60 + minute + mins;
  const nextHour = String(Math.floor(total / 60)).padStart(2, "0");
  const nextMinute = String(total % 60).padStart(2, "0");
  return `${nextHour}:${nextMinute}`;
}

function formatSlot(slot) {
  return `${slot} - ${addMinutes(slot, 30)}`;
}

function onNameTyped() {
  const wasSelectable = !gridEl.classList.contains("locked");
  if (!hasName()) {
    startedName = "";
    selected = new Set();
    setStatus("");
  }
  updateNameGate();
  if (wasSelectable !== canSelectTimes()) {
    makeGrid(gridEl);
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function withBusy(fn) {
  if (busy) return;
  busy = true;
  updateNameGate();
  refreshBtn.disabled = true;
  try {
    await fn();
  } finally {
    busy = false;
    updateNameGate();
    refreshBtn.disabled = false;
  }
}

async function startSelecting() {
  const name = currentName();
  if (!name) {
    setStatus("Please enter your name first.");
    nameEl.focus();
    return;
  }

  await withBusy(async () => {
    setStatus("");
    try {
      const response = await fetch("/api/person/" + encodeURIComponent(name));
      const data = await readJson(response);
      if (!response.ok) {
        setStatus(data.error || "Could not load availability.");
        return;
      }
      startedName = name;
      selected = new Set((data.selected || []).map((item) => key(item[0], item[1])));
      switchTab("mine");
      updateNameGate();
      makeGrid(gridEl);
      gridEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch {
      setStatus("Could not reach the server.");
    }
  });
}

async function save() {
  const name = currentName();
  if (!canSelectTimes()) {
    setStatus("Enter your name, then click Start selecting times.");
    nameEl.focus();
    return;
  }

  await withBusy(async () => {
    try {
      const payload = [...selected].map((item) => item.split("|"));
      const response = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, selected: payload }),
      });
      const data = await readJson(response);
      if (!response.ok) {
        setStatus(data.error || "Could not save");
        return;
      }
      setStatus("✓ Availability saved");
      switchTab("team");
    } catch {
      setStatus("Could not reach the server.");
    }
  });
}

async function loadOverlap() {
  try {
    const response = await fetch("/api/overlap");
    const data = await readJson(response);
    if (!response.ok) {
      setStatus(data.error || "Could not load team overlap.");
      return;
    }

    responsesEl.textContent = `Responses: ${data.responses} / ${data.total_people}`;
    pendingEl.textContent = data.pending.length
      ? `Waiting for: ${data.pending.join(", ")}`
      : "Everyone has responded";

    makeGrid(overlapEl, data);
  } catch {
    setStatus("Could not reach the server.");
  }
}

function switchTab(id) {
  document.querySelectorAll(".tab, .tabpane").forEach((el) => {
    el.classList.remove("active");
  });
  document.querySelector(`.tab[data-tab="${id}"]`).classList.add("active");
  document.querySelector("#" + id).classList.add("active");
  if (id === "team") loadOverlap();
}

document.querySelectorAll(".tab").forEach((button) => {
  button.onclick = () => switchTab(button.dataset.tab);
});
nameEl.addEventListener("input", onNameTyped);
nameEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    startSelecting();
  }
});
startBtn.onclick = startSelecting;
saveBtn.onclick = save;
clearBtn.onclick = () => {
  if (!canSelectTimes()) return;
  selected.clear();
  makeGrid(gridEl);
};
refreshBtn.onclick = () => {
  if (busy) return;
  loadOverlap();
};

updateNameGate();
makeGrid(gridEl);
nameEl.focus();
