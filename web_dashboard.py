"""HumanClaw Web Dashboard — lightweight HTTP server for browser preview."""

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from humanclaw.conductor import Conductor
from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import ProposedAction, EntityType, ImpulseType, MemoryType, Verdict

config = HumanClawConfig()
config.db_path = "/tmp/humanclaw_web_demo.db"
conductor = Conductor(config=config, db_path=config.db_path)

# Seed demo data
conductor.relational.add_entity("arjun", EntityType.PROSPECT)
conductor.relational.add_entity("priya", EntityType.CLIENT)
conductor.relational.add_entity("rahul", EntityType.CLOSE_COLLEAGUE)
conductor.relational.log_interaction("arjun", 0.3, "Sent proposal for design work")
conductor.relational.log_interaction("priya", 0.7, "Positive project kickoff call")
conductor.relational.log_interaction("rahul", 0.5, "Regular sync")
conductor.goal_engine.register_goal("Close DesignStudio deal", expected_value=0.8, milestones_total=5)
conductor.goal_engine.register_goal("Launch Q2 marketing campaign", expected_value=0.6, milestones_total=8)
conductor.memory_decay.add_memory(MemoryType.EPISODIC, "Sent proposal to Arjun at DesignStudio, awaiting response")


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HUMANCLAW</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Space+Grotesk:wght@400;500;700&display=swap');

  :root {
    --bg: #0a0a0a;
    --surface: #111111;
    --surface-2: #1a1a1a;
    --border: #2a2a2a;
    --amber: #d4a017;
    --amber-dim: #8b6914;
    --amber-glow: rgba(212, 160, 23, 0.15);
    --green: #22c55e;
    --red: #ef4444;
    --blue: #3b82f6;
    --text: #e5e5e5;
    --text-dim: #666666;
    --text-muted: #444444;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    line-height: 1.5;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ═══ HEADER ═══ */
  .header {
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .logo {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 18px;
    color: var(--amber);
    letter-spacing: 2px;
    text-transform: uppercase;
  }
  .logo-sub {
    font-size: 11px;
    color: var(--text-dim);
    letter-spacing: 0;
    text-transform: none;
    font-weight: 400;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 24px;
  }
  .status-dot {
    width: 8px; height: 8px;
    background: var(--green);
    border-radius: 50%;
    display: inline-block;
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ═══ GRID ═══ */
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto auto;
    gap: 1px;
    background: var(--border);
    min-height: calc(100vh - 56px);
  }

  /* ═══ PANELS ═══ */
  .panel {
    background: var(--surface);
    padding: 20px 24px;
  }
  .panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--amber);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }

  /* ═══ STATE BARS ═══ */
  .state-row {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
    gap: 12px;
  }
  .state-label {
    width: 100px;
    color: var(--text-dim);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    text-align: right;
  }
  .state-bar-track {
    flex: 1;
    height: 18px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    position: relative;
    overflow: hidden;
  }
  .state-bar-fill {
    height: 100%;
    transition: width 0.6s ease;
    position: relative;
  }
  .state-bar-fill::after {
    content: '';
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    background: rgba(255,255,255,0.3);
  }
  .bar-amber { background: linear-gradient(90deg, var(--amber-dim), var(--amber)); }
  .bar-green { background: linear-gradient(90deg, #166534, var(--green)); }
  .bar-red { background: linear-gradient(90deg, #991b1b, var(--red)); }
  .bar-blue { background: linear-gradient(90deg, #1e3a5f, var(--blue)); }
  .state-value {
    width: 50px;
    text-align: right;
    font-weight: 500;
    font-size: 12px;
  }
  .state-meta {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 24px;
    font-size: 11px;
    color: var(--text-dim);
  }
  .meta-val { color: var(--text); font-weight: 500; }

  /* ═══ HOLD QUEUE ═══ */
  .queue-item {
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 12px 16px;
    margin-bottom: 8px;
    position: relative;
  }
  .queue-item::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
  }
  .queue-item.hold::before { background: var(--amber); }
  .queue-item.hard::before { background: var(--red); }
  .queue-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .queue-type {
    font-weight: 500;
    font-size: 12px;
  }
  .queue-source {
    font-size: 10px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 2px 6px;
    border: 1px solid var(--border);
  }
  .queue-reason {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 4px;
  }
  .queue-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .btn {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    padding: 4px 12px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-dim);
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 1px;
    transition: all 0.2s;
  }
  .btn:hover { border-color: var(--amber); color: var(--amber); }
  .btn-approve:hover { border-color: var(--green); color: var(--green); }
  .btn-reject:hover { border-color: var(--red); color: var(--red); }
  .queue-empty {
    color: var(--text-muted);
    font-size: 11px;
    padding: 20px 0;
    text-align: center;
  }

  /* ═══ GATE STACK ═══ */
  .gate-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--surface-2);
  }
  .gate-row:last-child { border-bottom: none; }
  .gate-icon {
    width: 20px; height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
  }
  .gate-name {
    width: 140px;
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .gate-score {
    width: 50px;
    font-size: 12px;
    font-weight: 500;
    text-align: right;
  }
  .gate-status {
    font-size: 10px;
    padding: 2px 8px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .gate-pass { color: var(--green); }
  .gate-hold { color: var(--amber); }
  .gate-block { color: var(--red); }

  /* ═══ FIRE BUTTON ═══ */
  .fire-section {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }
  .fire-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .btn-fire {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 8px 16px;
    border: 1px solid var(--amber-dim);
    background: var(--amber-glow);
    color: var(--amber);
    cursor: pointer;
    letter-spacing: 1px;
    transition: all 0.2s;
  }
  .btn-fire:hover {
    background: var(--amber);
    color: var(--bg);
    border-color: var(--amber);
  }
  .btn-fire:active { transform: scale(0.97); }

  /* ═══ EVENT LOG ═══ */
  .event-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 4px 0;
    font-size: 11px;
  }
  .event-time { color: var(--text-muted); width: 60px; }
  .event-icon { width: 14px; color: var(--amber); }
  .event-engine { color: var(--text-dim); width: 120px; }
  .event-type { color: var(--text); }

  /* ═══ ENGINE STATUS ═══ */
  .engine-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 0;
  }
  .engine-num {
    color: var(--amber);
    width: 24px;
    font-weight: 500;
    text-align: right;
  }
  .engine-name {
    flex: 1;
    font-size: 12px;
  }
  .engine-status {
    font-size: 10px;
    color: var(--green);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  /* ═══ RESPONSIVE ═══ */
  @media (max-width: 900px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }

  /* ═══ SCANLINE EFFECT ═══ */
  .panel::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,0,0,0.03) 2px,
      rgba(0,0,0,0.03) 4px
    );
    pointer-events: none;
  }
  .panel { position: relative; overflow: hidden; }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div>
      <div class="logo">HUMANCLAW</div>
      <div class="logo-sub">human behavioral middleware</div>
    </div>
  </div>
  <div class="header-right">
    <span style="color:var(--text-dim)">agent: <span style="color:var(--text)">humanclaw-agent</span></span>
    <span><span class="status-dot"></span> <span style="color:var(--text-dim); font-size:11px">10 engines active</span></span>
    <span id="clock" style="color:var(--text-muted)"></span>
  </div>
</div>

<div class="grid">

  <!-- PANEL 1: HUMANSTATE -->
  <div class="panel">
    <div class="panel-title">HumanState</div>
    <div id="state-bars"></div>
    <div class="state-meta">
      <span>DQ_MULT: <span class="meta-val" id="dqm">—</span></span>
      <span>PREFERRED: <span class="meta-val" id="pref">—</span></span>
    </div>
  </div>

  <!-- PANEL 2: HOLD QUEUE -->
  <div class="panel">
    <div class="panel-title">Hold Queue</div>
    <div id="hold-queue"></div>
  </div>

  <!-- PANEL 3: GATE STACK + FIRE -->
  <div class="panel">
    <div class="panel-title">Gate Stack Result</div>
    <div id="gate-results">
      <div class="queue-empty">Fire an action to see gate results</div>
    </div>
    <div class="fire-section">
      <div class="panel-title" style="margin-top:0">Actions</div>
      <div class="fire-row">
        <button class="btn-fire" onclick="fireDemo()">&#9889; FIRE DEMO IMPULSE</button>
        <button class="btn-fire" onclick="fireAction('send_followup', 0.9)">SEND (HIGH CONF)</button>
        <button class="btn-fire" onclick="fireAction('send_followup', 0.3)">SEND (LOW CONF)</button>
        <button class="btn-fire" onclick="fireAction('publish_post', 0.7)">PUBLISH POST</button>
      </div>
    </div>

    <div class="panel-title" style="margin-top:16px">Engines</div>
    <div id="engines"></div>
  </div>

  <!-- PANEL 4: EVENT LOG -->
  <div class="panel">
    <div class="panel-title">Event Log</div>
    <div id="event-log"></div>
  </div>

</div>

<script>
const API = '';

async function fetchJSON(path) {
  const r = await fetch(API + path);
  return r.json();
}

function barClass(dim) {
  if (dim === 'mood') return 'bar-blue';
  if (dim === 'fatigue' || dim === 'social_load') return 'bar-red';
  return 'bar-amber';
}

function renderStateBars(state) {
  const el = document.getElementById('state-bars');
  const dims = ['energy','mood','fatigue','boredom','social_load','focus'];
  el.innerHTML = dims.map(d => {
    const v = state[d];
    const pct = d === 'mood' ? Math.abs(v) * 100 : v * 100;
    const valStr = d === 'mood' ? (v >= 0 ? '+' : '') + v.toFixed(2) : v.toFixed(2);
    const cls = barClass(d);
    return `<div class="state-row">
      <span class="state-label">${d.replace('_',' ')}</span>
      <div class="state-bar-track">
        <div class="state-bar-fill ${cls}" style="width:${pct}%"></div>
      </div>
      <span class="state-value">${valStr}</span>
    </div>`;
  }).join('');
}

function renderQueue(queue) {
  const el = document.getElementById('hold-queue');
  if (!queue.length) {
    el.innerHTML = '<div class="queue-empty">no pending actions</div>';
    return;
  }
  el.innerHTML = queue.slice(0, 6).map(item => {
    const isHard = item.hold_reason.includes('HARD');
    return `<div class="queue-item ${isHard ? 'hard' : 'hold'}">
      <div class="queue-header">
        <span class="queue-type">${item.action_type}</span>
        <span class="queue-source">${item.hold_source}</span>
      </div>
      <div class="queue-reason">${item.hold_reason}</div>
      <div style="font-size:10px;color:var(--text-muted);margin-top:2px">conf: ${item.adjusted_confidence.toFixed(2)}</div>
      <div class="queue-actions">
        <button class="btn btn-approve" onclick="approveHold('${item.id}')">approve</button>
        <button class="btn btn-reject" onclick="rejectHold('${item.id}')">reject</button>
      </div>
    </div>`;
  }).join('');
}

function renderGateResults(results) {
  const el = document.getElementById('gate-results');
  if (!results || !results.length) return;
  el.innerHTML = results.map(gr => {
    const isPass = gr.verdict === 'proceed';
    const isHold = gr.verdict === 'hold';
    const icon = isPass ? '&#10003;' : isHold ? '&#9888;' : '&#10007;';
    const cls = isPass ? 'gate-pass' : isHold ? 'gate-hold' : 'gate-block';
    return `<div class="gate-row">
      <span class="gate-icon ${cls}">${icon}</span>
      <span class="gate-name">${gr.engine.replace(/_/g,' ')}</span>
      <span class="gate-score">${gr.score.toFixed(2)}</span>
      <span class="gate-status ${cls}">${gr.verdict}</span>
    </div>`;
  }).join('');
}

function renderEngines() {
  const engines = [
    [1,'HumanState'],[2,'Stochastic Impulse'],[3,'InactionGuard'],
    [4,'Relational Memory'],[5,'Dissent'],[6,'Goal Abandonment'],
    [7,'Memory Decay'],[8,'Social Risk'],[9,'Anomaly Detector'],
    [10,'Values Boundary']
  ];
  document.getElementById('engines').innerHTML = engines.map(([n,name]) =>
    `<div class="engine-row">
      <span class="engine-num">${n}</span>
      <span class="engine-name">${name}</span>
      <span class="engine-status">active</span>
    </div>`
  ).join('');
}

function renderEvents(events) {
  const el = document.getElementById('event-log');
  if (!events.length) {
    el.innerHTML = '<div class="queue-empty">no events yet</div>';
    return;
  }
  el.innerHTML = events.slice(0, 15).map(ev => {
    const d = new Date(ev.created_at * 1000);
    const t = d.toTimeString().slice(0,8);
    const icon = ev.event_type.includes('impulse') ? '&#9889;' :
                 ev.event_type.includes('proceed') ? '&#9670;' :
                 ev.event_type.includes('held') ? '&#9888;' : '&middot;';
    return `<div class="event-row">
      <span class="event-time">${t}</span>
      <span class="event-icon">${icon}</span>
      <span class="event-engine">[${ev.engine}]</span>
      <span class="event-type">${ev.event_type}</span>
    </div>`;
  }).join('');
}

async function refresh() {
  try {
    const data = await fetchJSON('/api/state');
    renderStateBars(data.state);
    document.getElementById('dqm').textContent = data.dqm.toFixed(2);
    document.getElementById('pref').textContent = data.preferred;
    renderQueue(data.queue);
    renderEvents(data.events);
  } catch(e) { console.error(e); }
}

async function fireDemo() {
  const data = await fetchJSON('/api/demo');
  renderGateResults(data.gate_results);
  setTimeout(refresh, 300);
}

async function fireAction(type, conf) {
  const data = await fetchJSON(`/api/evaluate?type=${type}&conf=${conf}`);
  renderGateResults(data.gate_results);
  setTimeout(refresh, 300);
}

async function approveHold(id) {
  await fetchJSON(`/api/approve?id=${id}`);
  setTimeout(refresh, 300);
}

async function rejectHold(id) {
  await fetchJSON(`/api/reject?id=${id}`);
  setTimeout(refresh, 300);
}

function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
}

renderEngines();
refresh();
setInterval(refresh, 3000);
setInterval(updateClock, 1000);
updateClock();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())

        elif self.path == '/api/state':
            conductor.human_state.tick()
            state = conductor.get_state_snapshot()
            queue = conductor.get_hold_queue()
            events = conductor.event_log.recent(limit=15)
            data = {
                "state": state,
                "dqm": conductor.human_state.decision_quality_multiplier,
                "preferred": conductor.human_state.preferred_task_type.value,
                "queue": [{
                    "id": h.id,
                    "action_type": h.action.action_type,
                    "hold_source": h.hold_source,
                    "hold_reason": h.hold_reason,
                    "adjusted_confidence": h.adjusted_confidence,
                } for h in queue],
                "events": events,
            }
            self._json(data)

        elif self.path == '/api/demo':
            conductor.human_state.boredom = 0.75
            conductor.human_state.energy = max(0.4, conductor.human_state.energy - 0.1)
            action = ProposedAction(
                action_type="send_followup",
                payload={
                    "discovery": "Proposal to Arjun — sent 11 days ago, no response",
                    "suggested": "gentle follow-up",
                },
                confidence=0.61,
                rationale="Idle discovery: unresolved open loop from 11 days ago",
                source="impulse",
                target_entity="arjun",
            )
            result = conductor.evaluate(action)
            self._json({
                "verdict": result.final_verdict.value,
                "gate_results": [{
                    "engine": gr.engine,
                    "verdict": gr.verdict.value,
                    "score": gr.score,
                    "reason": gr.reason,
                } for gr in result.gate_results],
                "audit": result.audit_trail,
            })

        elif self.path.startswith('/api/evaluate'):
            params = {}
            if '?' in self.path:
                qs = self.path.split('?')[1]
                for p in qs.split('&'):
                    k, v = p.split('=')
                    params[k] = v
            action = ProposedAction(
                action_type=params.get('type', 'test'),
                payload={"message": "test action"},
                confidence=float(params.get('conf', '0.7')),
                rationale="User-triggered test action",
                source="user",
            )
            result = conductor.evaluate(action)
            self._json({
                "verdict": result.final_verdict.value,
                "gate_results": [{
                    "engine": gr.engine,
                    "verdict": gr.verdict.value,
                    "score": gr.score,
                    "reason": gr.reason,
                } for gr in result.gate_results],
            })

        elif self.path.startswith('/api/approve'):
            hold_id = self.path.split('id=')[1] if 'id=' in self.path else ''
            conductor.approve_hold(hold_id)
            self._json({"ok": True})

        elif self.path.startswith('/api/reject'):
            hold_id = self.path.split('id=')[1] if 'id=' in self.path else ''
            conductor.reject_hold(hold_id)
            self._json({"ok": True})

        else:
            self.send_error(404)

    def _json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 8765), Handler)
    print("HumanClaw dashboard: http://localhost:8765")
    server.serve_forever()
