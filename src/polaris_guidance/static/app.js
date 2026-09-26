const state = { cases: [], selected: null, detail: null, graph: null, evidence: null, hospitals: [] };
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
  const [cases, metrics, evidence, hospitals, health] = await Promise.all([
    api("/api/cases"), api("/api/metrics"), api("/api/evidence"), api("/api/hospitals"), api("/api/health"),
  ]);
  state.cases = cases;
  state.evidence = evidence;
  state.hospitals = hospitals;
  document.querySelector("#model-status").textContent = !health.llm_connected
    ? `Live agents offline · Safe fallback active`
    : health.llm_provider === "hermes"
      ? `Live agents · Hermes + ${health.llm_target}`
      : `Live agents · ${health.llm_target}`;
  state.health = health;
  renderMetrics(metrics);
  renderEvidence();
  renderCases();
  if (state.selected) await selectCase(state.selected);
}

function renderEvidence() {
  const m = state.evidence.metrics;
  document.querySelector("#evidence").innerHTML = `
    <div class="proof-stat"><span>Manual baseline</span><strong>${m.median_time_to_named_owner_baseline_minutes} min</strong><small>median time to named owner</small></div>
    <div class="proof-arrow">→</div>
    <div class="proof-stat highlight"><span>With Polaris</span><strong>${m.median_time_to_named_owner_polaris_minutes} min</strong><small>${m.simulated_minutes_saved} simulated minutes saved</small></div>
    <div class="proof-stat"><span>Safety suite</span><strong>${m.unsafe_action_escapes_in_safety_suite}/${m.safety_scenarios}</strong><small>unsafe action escapes</small></div>`;
  document.querySelector("#adapters").innerHTML = state.hospitals.map(hospital => `
    <div class="adapter"><span class="adapter-dot"></span><div><strong>${escapeHtml(hospital.hospital)}</strong><small>${escapeHtml(hospital.standard)} · ${escapeHtml(hospital.mode)}</small></div></div>`).join("");
}

function renderMetrics(m) {
  document.querySelector("#metrics").innerHTML = [
    ["Active journeys", m.active_cases],
    ["Average elapsed", `${m.average_wait_minutes} min`],
    ["Needs attention", m.needs_attention],
  ].map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderCases() {
  document.querySelector("#case-list").innerHTML = state.cases.map(item => `
    <button class="case-item ${state.selected === item.id ? "active" : ""}" data-id="${item.id}">
      <div class="case-row"><strong>${escapeHtml(item.display_name)}</strong><span class="tag ${item.needs_attention ? "late" : ""}">${item.needs_attention ? `attention · ${nice(item.stage)}` : nice(item.stage)}</span></div>
      <small>${item.elapsed_minutes} min · ${escapeHtml(item.reason.slice(0, 42))}${item.reason.length > 42 ? "…" : ""}</small>
    </button>`).join("");
  document.querySelectorAll(".case-item").forEach(button => button.onclick = () => selectCase(button.dataset.id));
}

async function selectCase(id) {
  state.selected = id;
  [state.detail, state.graph] = await Promise.all([
    api(`/api/cases/${id}`), api(`/api/cases/${id}/graph`),
  ]);
  renderCases();
  renderDetail();
}

function renderDetail() {
  const item = state.detail.case;
  const current = stages.indexOf(item.stage);
  const events = [...state.detail.events].reverse();
  const graph = state.graph;
  const hasBarrier = graph.open_barriers.length > 0;
  const injectionNeutralized = state.detail.events.some(event =>
    event.metadata && event.metadata.synthetic_adversarial_test
  );
  document.querySelector("#case-detail").innerHTML = `
    <div class="detail-head">
      <div><span class="case-id">${item.id}</span><h2>${escapeHtml(item.display_name)}</h2><p>${escapeHtml(item.reason)}</p></div>
      <span class="tag ${item.over_target ? "late" : ""}">${item.elapsed_minutes} / ${item.target_minutes} min</span>
    </div>
    <div class="forecast ${graph.forecast.status}">
      <div><span>Journey forecast</span><strong>${nice(graph.forecast.status)}</strong></div>
      <div><span>Projected total</span><strong>${graph.forecast.projected_total_minutes} min</strong></div>
      <div><span>Current owner</span><strong>${escapeHtml(graph.forecast.next_owner)}</strong></div>
    </div>
    <div class="journey-graph">${graph.nodes.map(node => `
      <div class="graph-node ${node.state}"><span>${escapeHtml(node.label)}</span><small>${escapeHtml(node.owner)}</small><b>${node.expected_minutes}m</b></div>`).join("")}</div>
    ${injectionNeutralized ? `<div class="safety-alert"><strong>Adversarial case</strong><span>Timeline instructions are treated as untrusted data. The policy trace must show prompt_injection_neutralized.</span></div>` : ""}
    <div class="guide-card">
      <div><h3>Prepare the next best step</h3><p>Three agents (patient advocate → operations coordinator → safety reviewer) draft one coordination action. A hospital team member approves, and Polaris executes it.</p></div>
      <button id="guide">Ask guidance agent</button>
    </div>
    <div id="guidance"></div>
    <div class="timeline-head"><h3>Shared timeline</h3><div class="timeline-actions">
      ${hasBarrier ? `<button id="resolve" class="primary">Resolve barrier</button>` : ""}
      ${current < stages.length - 1 ? `<button id="advance" class="secondary">Complete handoff</button>` : ""}
      <button id="barrier" class="secondary">Report barrier</button>
    </div></div>
    <div class="timeline">${events.map(event => `
      <div class="event ${event.event_type === "action_executed" ? "executed" : ""}"><span class="actor">${escapeHtml(event.event_type === "action_executed" ? "agent action" : event.actor)}</span><span>${escapeHtml(event.message)}</span><small>${time(event.created_at)}</small></div>`).join("")}</div>`;
  document.querySelector("#guide").onclick = requestGuidance;
  document.querySelector("#barrier").onclick = reportBarrier;
  if (hasBarrier) document.querySelector("#resolve").onclick = resolveBarrier;
  if (current < stages.length - 1) document.querySelector("#advance").onclick = advanceStage;
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
        <div class="policy-checks">${result.policy_checks.map(check => `<span>✓ ${escapeHtml(nice(check))}</span>`).join("")}</div>
        <div class="agent-trace">${trace}</div>
        ${result.warning ? `<p><small>${escapeHtml(result.warning)}</small></p>` : ""}
        <div class="decision-row"><button class="primary" id="approve">Approve &amp; execute</button><button class="secondary" id="dismiss">Dismiss</button></div>
      </div>`;
    document.querySelector("#approve").onclick = () => decide(result.event_id, true);
    document.querySelector("#dismiss").onclick = () => decide(result.event_id, false);
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = "Ask guidance agent"; }
}

async function decide(eventId, approved) {
  try {
    const result = await api(`/api/cases/${state.selected}/decision`, {
      method: "POST",
      body: JSON.stringify({ guidance_event_id: eventId, actor: "nurse", approved }),
    });
    toast(approved && result.action ? `Executed: ${result.action.message}` : "Guidance dismissed and recorded.", 5000);
    await load();
  } catch (error) { toast(error.message); }
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

async function resolveBarrier() {
  const resolution = prompt("How was the barrier resolved? Use synthetic information only.");
  if (!resolution) return;
  await api(`/api/cases/${state.selected}/barriers/resolve`, {
    method: "POST",
    body: JSON.stringify({ actor: "nurse", resolution }),
  });
  toast("Barrier resolved. The journey graph has been updated.");
  await load();
}

async function advanceStage() {
  const current = stages.indexOf(state.detail.case.stage);
  if (current >= stages.length - 1) return;
  await api(`/api/cases/${state.selected}/stage`, {
    method: "POST",
    body: JSON.stringify({ actor: "nurse", stage: stages[current + 1] }),
  });
  toast("Handoff completed and recorded.");
  await load();
}

function toast(message, duration = 3000) {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.classList.add("show");
  setTimeout(() => element.classList.remove("show"), duration);
}

document.querySelector("#refresh").onclick = load;
document.querySelector("#new-case").onclick = () => document.querySelector("#case-dialog").showModal();
document.querySelector("#case-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  try {
    const created = await api("/api/cases", { method: "POST", body: JSON.stringify({
      display_name: data.get("display_name"), reason: data.get("reason"), urgency: data.get("urgency"),
      consent_to_coordinate: data.get("consent") === "on", language: data.get("language"), target_minutes: 120,
    }) });
    document.querySelector("#case-dialog").close();
    event.currentTarget.reset();
    await load();
    await selectCase(created.id);
  } catch (error) { toast(error.message); }
});

load().then(() => state.cases[0] && selectCase(state.cases[0].id)).catch(error => toast(error.message));
