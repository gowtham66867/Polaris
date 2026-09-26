const state = { cases: [], selected: null, detail: null };
const stages = ["arrival", "registration", "triage", "clinical_review", "diagnostics", "treatment", "discharge"];

const api = async (path, options = {}) => {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
};

const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const nice = value => value.replaceAll("_", " ");
const time = value => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

async function load() {
  const [cases, metrics] = await Promise.all([api("/api/cases"), api("/api/metrics")]);
  state.cases = cases;
  renderMetrics(metrics);
  renderCases();
  if (state.selected) await selectCase(state.selected);
}

function renderMetrics(m) {
  document.querySelector("#metrics").innerHTML = [
    ["Active journeys", m.active_cases],
    ["Average elapsed", `${m.average_wait_minutes} min`],
    ["Needs attention", m.over_target],
  ].map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderCases() {
  document.querySelector("#case-list").innerHTML = state.cases.map(item => `
    <button class="case-item ${state.selected === item.id ? "active" : ""}" data-id="${item.id}">
      <div class="case-row"><strong>${escapeHtml(item.display_name)}</strong><span class="tag ${item.over_target ? "late" : ""}">${item.over_target ? "attention" : nice(item.stage)}</span></div>
      <small>${item.elapsed_minutes} min · ${escapeHtml(item.reason.slice(0, 42))}${item.reason.length > 42 ? "…" : ""}</small>
    </button>`).join("");
  document.querySelectorAll(".case-item").forEach(button => button.onclick = () => selectCase(button.dataset.id));
}

async function selectCase(id) {
  state.selected = id;
  state.detail = await api(`/api/cases/${id}`);
  renderCases();
  renderDetail();
}

function renderDetail() {
  const item = state.detail.case;
  const current = stages.indexOf(item.stage);
  const events = [...state.detail.events].reverse();
  document.querySelector("#case-detail").innerHTML = `
    <div class="detail-head">
      <div><span class="case-id">${item.id}</span><h2>${escapeHtml(item.display_name)}</h2><p>${escapeHtml(item.reason)}</p></div>
      <span class="tag ${item.over_target ? "late" : ""}">${item.elapsed_minutes} / ${item.target_minutes} min</span>
    </div>
    <div class="stages">${stages.map((stage, i) => `<div class="stage ${i <= current ? "done" : ""}">${nice(stage)}</div>`).join("")}</div>
    <div class="guide-card">
      <div><h3>Prepare the next best step</h3><p>Hermes + Claude draft a coordination action. A hospital team member decides.</p></div>
      <button id="guide">Ask guidance agent</button>
    </div>
    <div id="guidance"></div>
    <div class="timeline-head"><h3>Shared timeline</h3><button id="barrier" class="secondary">Report barrier</button></div>
    <div class="timeline">${events.map(event => `
      <div class="event"><span class="actor">${escapeHtml(event.actor)}</span><span>${escapeHtml(event.message)}</span><small>${time(event.created_at)}</small></div>`).join("")}</div>`;
  document.querySelector("#guide").onclick = requestGuidance;
  document.querySelector("#barrier").onclick = reportBarrier;
}

async function requestGuidance() {
  const button = document.querySelector("#guide");
  button.disabled = true;
  button.textContent = "Reviewing journey…";
  try {
    const result = await api(`/api/cases/${state.selected}/guide`, { method: "POST" });
    const g = result.guidance;
    const trace = result.steps.map(step => `
      <div class="agent-step ${step.status}">
        <span>${escapeHtml(nice(step.role))}</span>
        <strong>${escapeHtml(step.status)}</strong>
        <small>${step.duration_ms} ms</small>
      </div>`).join("");
    document.querySelector("#guidance").innerHTML = `
      <div class="guidance-result">
        <span class="tag ${g.priority === "emergency" || g.priority === "high" ? "late" : ""}">${g.priority} · ${escapeHtml(g.source)}</span>
        <h3>${escapeHtml(g.summary)}</h3>
        <p><strong>Suggested action:</strong> ${escapeHtml(g.next_action)}</p>
        <p><strong>Owner:</strong> ${escapeHtml(g.owner)} · <strong>Why:</strong> ${escapeHtml(g.rationale)}</p>
        <div class="run-meta"><strong>${escapeHtml(result.run_status)}</strong> · ${escapeHtml(result.run_id)} · ${result.policy_checks.length} policy checks</div>
        <div class="agent-trace">${trace}</div>
        ${result.warning ? `<p><small>${escapeHtml(result.warning)}</small></p>` : ""}
        <div class="decision-row"><button class="primary" id="approve">Approve</button><button class="secondary" id="dismiss">Dismiss</button></div>
      </div>`;
    document.querySelector("#approve").onclick = () => decide(result.event_id, true);
    document.querySelector("#dismiss").onclick = () => decide(result.event_id, false);
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = "Ask guidance agent"; }
}

async function decide(eventId, approved) {
  await api(`/api/cases/${state.selected}/decision`, {
    method: "POST",
    body: JSON.stringify({ guidance_event_id: eventId, actor: "nurse", approved }),
  });
  toast(approved ? "Guidance approved and recorded." : "Guidance dismissed and recorded.");
  await selectCase(state.selected);
}

async function reportBarrier() {
  const message = prompt("What is blocking the patient journey? Do not include unnecessary sensitive data.");
  if (!message) return;
  await api(`/api/cases/${state.selected}/events`, {
    method: "POST",
    body: JSON.stringify({ actor: "nurse", event_type: "barrier_reported", message }),
  });
  await load();
}

function toast(message) {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), 3000);
}

document.querySelector("#refresh").onclick = load;
document.querySelector("#new-case").onclick = () => document.querySelector("#case-dialog").showModal();
document.querySelector("#case-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    const created = await api("/api/cases", { method: "POST", body: JSON.stringify({
      display_name: data.get("display_name"), reason: data.get("reason"), urgency: data.get("urgency"),
      consent_to_coordinate: data.get("consent") === "on", language: data.get("language"), target_minutes: 45,
    }) });
    document.querySelector("#case-dialog").close();
    event.currentTarget.reset();
    await load();
    await selectCase(created.id);
  } catch (error) { toast(error.message); }
});

load().then(() => state.cases[0] && selectCase(state.cases[0].id)).catch(error => toast(error.message));
