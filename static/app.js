const days = window.DAYS;
const slots = window.SLOTS;

let selected = new Set();
let dragging = false;
let dragMode = true;
let started = false;

const key = (day, slot) => `${day}|${slot}`;
const nameInput = () => document.querySelector("#name");
const hasName = () => !!nameInput().value.trim();
const canSelectTimes = () => started && hasName();

function updateNameGate() {
  const ok = canSelectTimes();
  document.querySelector("#start").disabled = !hasName();
  document.querySelector("#grid").classList.toggle("locked", !ok);
  document.querySelector("#save").disabled = !ok;
  document.querySelector("#clear").disabled = !ok;
  document.querySelector("#need-name").hidden = ok;
}

function makeGrid(el, overlap = null) {
  el.innerHTML = "";
  el.appendChild(document.createElement("div"));

  days.forEach((day) => {
    const heading = document.createElement("div");
    heading.className = "head";
    heading.textContent = day;
    el.appendChild(heading);
  });

  const selectable = !overlap && canSelectTimes();

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

        cell.classList.add("overlap");
        cell.innerHTML = `<span>${count}/${total || 0}</span>`;
        cell.style.background = `rgba(36, 52, 71, ${alpha})`;
        cell.style.color = count / Math.max(total, 1) > 0.45 ? "white" : "#243447";
        cell.title = (overlap.names[day][slot] || []).join(", ")
          || "No submitted participant available";
      } else {
        if (selected.has(key(day, slot))) {
          cell.classList.add("selected");
        }
        if (selectable) {
          cell.onmousedown = (event) => {
            event.preventDefault();
            dragging = true;
            dragMode = !selected.has(key(day, slot));
            apply(cell);
          };
          cell.onmouseenter = () => {
            if (dragging) apply(cell);
          };
          cell.onclick = () => {
            if (!dragging) toggle(cell);
          };
        }
      }

      el.appendChild(cell);
    });
  });
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

function toggle(cell) {
  if (!canSelectTimes()) return;
  const cellKey = key(cell.dataset.day, cell.dataset.slot);
  if (selected.has(cellKey)) {
    selected.delete(cellKey);
  } else {
    selected.add(cellKey);
  }
  cell.classList.toggle("selected");
}

window.onmouseup = () => setTimeout(() => {
  dragging = false;
}, 0);

function formatTime(time) {
  const [hour, minute] = time.split(":").map(Number);
  const suffix = hour >= 12 ? "pm" : "am";
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${suffix}`;
}

function addMinutes(time, mins) {
  const [hour, minute] = time.split(":").map(Number);
  const total = hour * 60 + minute + mins;
  const nextHour = String(Math.floor(total / 60)).padStart(2, "0");
  const nextMinute = String(total % 60).padStart(2, "0");
  return `${nextHour}:${nextMinute}`;
}

function formatSlot(slot) {
  return `${formatTime(slot)} - ${formatTime(addMinutes(slot, 30))}`;
}

function formatRange(start, end) {
  return `${formatTime(start)} - ${formatTime(end)}`;
}

function onNameTyped() {
  if (!hasName()) {
    started = false;
    selected = new Set();
    document.querySelector("#status").textContent = "";
  } else {
    started = false;
  }
  updateNameGate();
  makeGrid(document.querySelector("#grid"));
}

async function startSelecting() {
  const name = nameInput().value.trim();
  if (!name) {
    document.querySelector("#status").textContent = "Please enter your name first.";
    nameInput().focus();
    return;
  }

  started = true;
  document.querySelector("#status").textContent = "";
  updateNameGate();
  switchTab("mine");

  const response = await fetch("/api/person/" + encodeURIComponent(name));
  const data = await response.json();
  selected = new Set(data.selected.map((item) => key(item[0], item[1])));
  makeGrid(document.querySelector("#grid"));
  document.querySelector("#grid").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function save() {
  const name = nameInput().value.trim();
  if (!canSelectTimes()) {
    document.querySelector("#status").textContent =
      "Enter your name, then click Start selecting times.";
    nameInput().focus();
    return;
  }

  const payload = [...selected].map((item) => item.split("|"));
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, selected: payload }),
  });
  const data = await response.json();

  if (!response.ok) {
    document.querySelector("#status").textContent = data.error || "Could not save";
    return;
  }

  document.querySelector("#status").textContent = "✓ Availability saved";
  switchTab("team");
  loadOverlap();
}

async function loadOverlap() {
  const response = await fetch("/api/overlap");
  const data = await response.json();

  document.querySelector("#responses").textContent =
    `Responses: ${data.responses} / ${data.total_people}`;
  document.querySelector("#pending").textContent = data.pending.length
    ? `Waiting for: ${data.pending.join(", ")}`
    : "Everyone has responded";

  const best = document.querySelector("#best");
  best.innerHTML = "";
  data.best.forEach((option, index) => {
    const item = document.createElement("div");
    item.className = "option";
    item.innerHTML = `
      <div>
        <strong>${index + 1}. ${option.day}, ${formatRange(option.start, option.end)}</strong>
        <small>${option.names.join(", ") || "No common availability"}</small>
      </div>
      <strong>${option.count}/${option.total}</strong>
    `;
    best.appendChild(item);
  });

  makeGrid(document.querySelector("#overlap"), data);
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
nameInput().addEventListener("input", onNameTyped);
nameInput().addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    startSelecting();
  }
});
document.querySelector("#start").onclick = startSelecting;
document.querySelector("#save").onclick = save;
document.querySelector("#clear").onclick = () => {
  if (!canSelectTimes()) return;
  selected.clear();
  makeGrid(document.querySelector("#grid"));
};
document.querySelector("#refresh").onclick = loadOverlap;

updateNameGate();
makeGrid(document.querySelector("#grid"));
nameInput().focus();
