# Humane Dashboard — Complete Usage Guide

## Getting Started

### Starting the Dashboard

```bash
# Option 1: If you ran `humane init` and configured your agent
humane serve

# Option 2: Quick start with defaults
pip install -e .
humane init        # Follow the wizard
humane serve       # Starts API + dashboard on port 8765
```

Open **http://localhost:8765** in your browser.

The dashboard has 7 pages accessible from the left sidebar. Each page has a description banner and an expandable "How to use this page" section with detailed tips.

---

## 1. Overview

**What it shows:** Your agent's live state, recent activity, and pending actions — all in one view. This page auto-refreshes every 3 seconds.

### Status Banner

At the top you'll see:

| Field | Meaning |
|---|---|
| **Agent Name** | The name you set during `humane init` (green dot = online) |
| **DQM Score** | Decision Quality Multiplier (0.0–1.0). This number scales every action's confidence before the gate check. When the agent is fatigued or in a bad mood, DQM drops — meaning more actions get held for your review. A score of 0.85+ means the agent is in good decision-making shape. |
| **Preferred Task** | What the agent should be working on right now, derived from its internal state. When energy is high and focus is good, it says "any". When bored, it shifts to "creative". When fatigued, "routine". |
| **Queue** | Number of actions waiting for your approval in the Hold Queue. |

### Agent State (6 Dimensions)

Each bar shows a value from 0.0 to 1.0 (mood ranges from -1.0 to +1.0):

| Dimension | What it means | What happens when it's extreme |
|---|---|---|
| **Energy** | How much capacity the agent has | Low energy = lower DQM, agent defers tasks |
| **Mood** | Emotional state (-1.0 negative to +1.0 positive) | Negative mood = more cautious, higher social risk sensitivity |
| **Fatigue** | Accumulated tiredness | Above fatigue defer threshold (default 0.8) = all actions get held |
| **Boredom** | How understimulated the agent is | High boredom = more frequent impulses fire |
| **Social Load** | How much social interaction has happened | High load = agent becomes less willing to initiate contact |
| **Focus** | Concentration level | Low focus = lower DQM, preference shifts to routine tasks |

These dimensions evolve over time automatically. Tasks drain energy and increase fatigue. Rest recovers energy. Interactions increase social load. Inactivity increases boredom.

### Evaluate Action (Button)

Click **Evaluate Action** to test how the 10-engine gate stack would judge any action.

1. Enter an **Action Type** — a short label like `send_email`, `call_client`, `share_document`, `make_commitment`
2. Set **Confidence** — how sure the agent is (0.0 to 1.0). Try 0.3 to see a hold, or 0.9 to see a proceed.
3. Enter a **Rationale** — why this action should happen. This feeds the Dissent Engine.
4. Click **Evaluate**

The result panel shows:

- **Verdict**: PROCEED (green), HOLD (amber), or BLOCK (red)
- **Gate Results**: Each engine's individual verdict with its score:
  - `values_boundary` — Did it violate any hard or soft values?
  - `social_risk` — Is the social risk acceptable?
  - `dissent` — Did the agent's self-challenge flag anything?
  - `inaction_guard` — Is the adjusted confidence above threshold?

Use this to tune your thresholds. If too many actions get held, lower the confidence threshold in Settings. If the agent is too aggressive, raise it.

### Fire Impulse (Button)

Click **Fire Impulse** to manually trigger one of 6 impulse types:

| Impulse | What it does |
|---|---|
| **Idle Discovery** | "Explore a tangential topic that may yield unexpected connections" |
| **Social Maintenance** | "Reach out to a contact you haven't spoken to recently" |
| **Goal Nudge** | "Check on a stalled goal and propose next steps" |
| **Value Reflection** | "Reflect on whether recent actions align with core values" |
| **Pattern Recognition** | "Look for patterns across recent interactions" |
| **Creative Tangent** | "Explore an idea that breaks from the current routine" |

Normally, impulses fire automatically at random intervals controlled by the Impulse Rate setting. Manual firing is useful for testing or when you want the agent to act proactively right now.

### Recent Activity

A live feed of the last 10 events across all engines. Each entry shows:
- The **engine** that generated the event (color-coded)
- The **event type** (e.g., `memory_added`, `hold_approved`, `impulse_fired`)
- **Relative time** (e.g., "2m ago", "just now")

### Hold Queue Preview

Shows up to 3 pending actions with inline Approve/Reject buttons. Click "View all X items" to go to the full Hold Queue page.

---

## 2. Hold Queue

**What it shows:** Every action the agent wanted to take but couldn't — because confidence was too low, social risk was too high, a value was violated, or the dissent engine raised a flag.

### The Queue Table

| Column | Meaning |
|---|---|
| **ID** | Unique identifier (truncated) |
| **Action Type** | What the agent wanted to do (e.g., `send_email`, `follow_up`) |
| **Source Engine** | Which engine blocked it (`inaction_guard`, `social_risk`, `values_boundary`, `dissent`) |
| **Confidence** | The action's original confidence percentage |
| **Reason** | Why it was held (e.g., "Adjusted confidence 0.25 < 0.65") |
| **Created** | When the action was proposed |

### Actions

- **Approve** (green button) — Execute the action. The agent's calibration data records this — over time, it learns what you approve and may adjust accordingly.
- **Reject** (red button) — Drop the action entirely. Also feeds calibration. If you consistently reject a type of action, the agent learns to be more cautious.

### When is the Queue Empty?

If you see "No pending actions", it means either:
1. The agent hasn't proposed any actions yet (freshly started)
2. All proposed actions passed the gate stack and were auto-approved
3. You've already reviewed everything

### Tips

- Check the queue regularly — held actions don't expire, they wait for your decision
- If the queue is always full, your confidence threshold might be too high (lower it in Settings)
- If the queue is always empty, your thresholds might be too permissive (raise them)
- The Reason column tells you exactly which engine held it and why — use this to understand the agent's judgment

---

## 3. Entities

**What it shows:** Every person, company, or contact the agent has a relationship with. Each entity has a relational profile that evolves over time.

### Entity Cards

Each card shows:

| Field | Meaning |
|---|---|
| **Name** | The entity's name |
| **Type Badge** | CLIENT (blue), PROSPECT (amber), CLOSE_COLLEAGUE (green), VENDOR (gray), UNKNOWN (gray) |
| **Trust Level** | Derived from sentiment and grudge history. Shown as a colored dot: green (trusted), amber (neutral), red (untrusted) |
| **Health** | Relationship health: Strong, Stable, Fragile, Strained, or Broken |
| **Sentiment** | Weighted average of interaction quality (-1.0 to +1.0). Green bar = positive, red bar = negative |
| **Grudge** | Accumulated negative experiences (0.0 to 1.0). Red bar shows grudge level |
| **Interactions** | Total count + time since last interaction |

### Trust Levels (How They Work)

Trust is computed from sentiment, grudge, and interaction count:

| Level | What it means | Agent behavior |
|---|---|---|
| **Deep Trust** | Strong positive history, minimal grudge | Agent shares freely, low social risk |
| **Trusted** | Good relationship, reliable | Agent communicates openly |
| **Neutral** | New or mixed relationship | Default caution level |
| **Cautious** | Some negative history or low interaction | Agent is more careful |
| **Untrusted** | High grudge or very negative sentiment | Every action requires human approval |

### Sentiment Decay

Sentiment decays differently by entity type:

| Type | Decay Half-Life | Why |
|---|---|---|
| Prospect | 14 days | Prospects go cold fast |
| Client | 30 days | Business relationships need maintenance |
| Close Colleague | 60 days | Personal trust lasts longer |
| Vendor | 21 days | Professional but transactional |

Grudge decays at **half the rate** of positive sentiment. Bad experiences linger longer than good ones — just like with humans.

### Adding an Entity

1. Click **Add Entity** (top right)
2. Enter a **Name**
3. Select a **Type** from the dropdown
4. Click **Add**

The entity appears with neutral trust, stable health, and zero sentiment/grudge. These evolve as interactions are logged (via the Telegram bot, API, or programmatically).

---

## 4. Goals

**What it shows:** Active objectives the agent is tracking. Each goal has an ROI score that determines whether the agent should keep pursuing it or propose abandonment.

### Goal Cards

Each card shows:

| Field | Meaning |
|---|---|
| **Description** | What the goal is |
| **Status Badge** | `active` (green), `paused` (amber), `abandoned` (red) |
| **Progress** | X/Y milestones completed, with a progress bar |
| **ROI** | Return on Investment score, color-coded |

### ROI Calculation

```
ROI = progress_velocity x relevance_decay x (expected_value / remaining_effort)
```

| ROI Range | Color | Meaning |
|---|---|---|
| 0.50+ | Green | Healthy — keep going |
| 0.25–0.49 | Amber | Slowing — consider adjusting |
| Below 0.25 | Red | Low return — consider abandoning |

ROI starts at 0.00 for new goals (no velocity yet). As you complete milestones, velocity increases and ROI rises. Over time, relevance decays — old goals become less relevant unless you keep making progress.

### Actions

- **Pause** — Temporarily suspend the goal. It won't trigger abandonment proposals. Click again (shows "Resume") to reactivate.
- **Abandon** — Mark the goal as no longer worth pursuing. This is permanent but rational — not every goal deserves infinite effort.

### Adding a Goal

1. Click **Add Goal** (top right)
2. Enter a **Description** — what you're trying to achieve
3. Set **Expected Value** — how valuable this goal is (0.1 to 10.0, default 1.0)
4. Set **Milestones** — total number of milestones to complete (default 5)
5. Click **Add**

### Tips

- Start with 3–5 milestones per goal. Too many makes early ROI look low.
- Goals with high expected value tolerate more effort before ROI drops.
- The agent proposes abandonment when ROI drops below the `goal_abandon_roi_threshold` (default 0.15). Adjust in Settings.

---

## 5. Memories

**What it shows:** Everything the agent knows. Memories decay naturally — accessed memories get reinforced, untouched ones fade and get archived.

### Memory Cards

Each card shows:

| Field | Meaning |
|---|---|
| **Content** | The memory text |
| **Type Badge** | EPISODIC (blue), SEMANTIC (green), RELATIONAL (amber), PROCEDURAL (gray) |
| **Pinned** | If shown, this memory is protected from decay |
| **Relevance** | Score from 0.0 to 1.0 with a bar. Below retrieval threshold = archived |
| **Accessed** | How many times this memory has been retrieved |
| **Created** | When the memory was first stored |

### Memory Types and Their Decay Rates

| Type | What it stores | Decay Speed | Example |
|---|---|---|---|
| **Episodic** | Specific events | Fast (hours–days) | "Sent proposal to Arjun on March 15" |
| **Semantic** | General facts | Slow (weeks) | "Arjun's company does design work" |
| **Relational** | Feelings about people | Very slow (months) | "Arjun is reliable but slow to respond" |
| **Procedural** | Learned methods | Near-permanent | "Always include case studies in proposals" |

### How Decay Works

Every memory has a relevance score that decreases over time:
- **Base decay** depends on type (episodic decays fastest, procedural slowest)
- **Access reinforcement** — each time a memory is retrieved, its relevance gets a boost (logarithmic scaling, so diminishing returns)
- **Archive threshold** — when relevance drops below the retrieval threshold (default 0.3), the memory is archived
- **Archived memories still exist** — they're just not surfaced automatically. You can recall them.

### Search

Type in the search bar and press Enter. Searches memory content. Results update in real-time.

### Active / Archived Toggle

- **Active** (default) — Shows memories with relevance above the threshold
- **Archived** — Shows memories that have decayed below threshold. These can be recalled by accessing them.

### Adding a Memory

1. Click **Add Memory** (top right)
2. Enter **Content** — the information to remember
3. Select a **Type** from the dropdown
4. Set **Pinned** — Yes to protect from decay, No for natural decay
5. Click **Add**

### Tips

- Pin critical information (API keys, important dates, core client requirements)
- Use Semantic type for facts that should persist (company details, preferences)
- Use Episodic for events that can fade naturally (meeting notes, daily interactions)
- If a memory keeps getting archived but you need it, either pin it or access it more frequently

---

## 6. Values

**What it shows:** The agent's moral boundaries. Values are the most powerful control mechanism — they can unconditionally block actions.

### Hard Values vs Soft Values

| | Hard Values | Soft Values |
|---|---|---|
| **When violated** | Action is BLOCKED. No override possible. | Action is HELD for human review. |
| **Human can override?** | No. Never. | Yes, you can approve a soft violation. |
| **Purpose** | The absolute floor. Non-negotiable principles. | Guidelines you want enforced but with flexibility. |
| **Example** | "Never share client confidential data" | "Avoid contacting prospects on weekends" |

### Value Cards

Each card shows:

| Field | Meaning |
|---|---|
| **Description** | What the value protects |
| **Severity Badge** | HARD (red) or SOFT (amber) |
| **Behavioral Pattern** | How the agent should behave to honor this value |
| **Violation Examples** | Concrete cases of what violating this value looks like (expandable) |
| **Honoring Examples** | Concrete cases of what respecting this value looks like (expandable) |

### How Value Detection Works

When the agent evaluates an action, the Values Boundary Engine checks the action type and rationale against:
1. **Violation examples** — keyword matching against known violation patterns
2. **Honoring examples** — keyword matching against known positive patterns
3. **Behavioral pattern** — general alignment check

More specific examples = better detection. Vague values like "be ethical" won't catch much. Specific values like "never forward client emails to third parties" will.

### Adding a Value

1. Click **Add Value** (top right)
2. Enter a **Description** — what this value protects
3. Enter a **Behavioral Pattern** — how the agent should behave
4. Select **Severity** — HARD (unconditional block) or SOFT (flag for review)
5. Enter **Violation Examples** — comma-separated concrete cases (e.g., "forwarding client emails, sharing revenue data")
6. Enter **Honoring Examples** — comma-separated positive cases (e.g., "using NDAs, anonymizing data")
7. Click **Add**

### The Business-Safe Preset

When you run `humane init`, the default "business-safe" preset includes:

**Hard values:**
- Never make unauthorized financial commitments
- Never share client confidential data with unauthorized parties
- Never make false claims about products or services

**Soft values:**
- Avoid contacting prospects outside business hours
- Prefer formal tone with new clients
- Avoid discussing competitor pricing
- Maintain professional boundaries in all communications

### Tips

- Start with few hard values. Every hard value is an unconditional block — too many and the agent can't do anything.
- Use soft values for guidelines that sometimes need exceptions.
- Add specific violation/honoring examples. The more concrete, the better the detection.
- Review the Values page when you notice the agent blocking actions you expected to pass.

---

## 7. Settings

**What it shows:** All tunable parameters for the 10 engines. Changes apply immediately — no server restart needed.

### Impulse Settings

| Parameter | Default | What it controls |
|---|---|---|
| **Impulse Rate (per day)** | 4 | How many impulses fire per day. Higher = more proactive agent. |
| **Min Interval (mins)** | 20 | Minimum minutes between impulses. Prevents spam. |
| **Max Interval (mins)** | 480 | Maximum minutes between impulses. Prevents long silences. |
| **Active Hours Start** | 7 | Hour (0–23) when impulses start firing. |
| **Active Hours End** | 22 | Hour (0–23) when impulses stop firing. |
| **Boredom Trigger** | 0.7 | Boredom level that boosts impulse rate. |

### Decision Gates

| Parameter | Default | What it controls |
|---|---|---|
| **Confidence Threshold** | 0.65 | **The most important setting.** Minimum adjusted confidence for an action to auto-approve. Lower = more permissive. Higher = more actions get held. |
| **Fatigue Defer** | 0.8 | Fatigue level that triggers automatic deferral of all actions. |
| **Dissent Threshold** | 0.6 | Dissent score above which the agent challenges its own decision. |

### Social & Anomaly

| Parameter | Default | What it controls |
|---|---|---|
| **Social Risk Block** | 0.8 | Social risk score that unconditionally blocks an action. |
| **Social Risk Flag** | 0.5 | Social risk score that flags for human review. |
| **Anomaly Hard** | 3.0 | Z-score threshold for hard anomaly detection (blocks). |
| **Anomaly Soft** | 2.0 | Z-score threshold for soft anomaly detection (flags). |

### Memory & Goals

| Parameter | Default | What it controls |
|---|---|---|
| **Retrieval Threshold** | 0.3 | Minimum relevance score for a memory to be surfaced. Lower = more memories available. |
| **Goal Abandon ROI** | 0.15 | ROI below which the agent proposes goal abandonment. |

### Bot

| Parameter | Default | What it controls |
|---|---|---|
| **Agent Name** | humane-agent | Display name for the agent. |
| **LLM Provider** | anthropic | Which LLM to use: `anthropic`, `openai`, or `gemini`. |
| **Model** | claude-sonnet-4-20250514 | Model identifier for the LLM provider. |
| **Personality** | colleague | Personality preset for conversation style. |
| **Reminder Interval (hours)** | 4 | Hours between reminder escalation levels. |
| **Max Escalation** | 4 | Maximum times a reminder escalates before stopping. |

### System

| Parameter | Default | What it controls |
|---|---|---|
| **Database Path** | ~/.humane/agent.db | Path to the SQLite database file. |
| **API Port** | 8765 | Port the dashboard and REST API run on. |
| **Notification Channel** | none | Channel for notifications (e.g., `telegram`, `slack`). |
| **Values Preset** | business-safe | Default values preset loaded on init. |

### Saving Changes

1. Modify any parameter by clicking the input field and changing the value
2. An "Unsaved changes" indicator appears (amber dot)
3. Click **Save Changes** to apply
4. Changes take effect immediately — no restart needed

### Tuning Profiles

**Conservative** (for sensitive work — legal, finance, healthcare):
- Confidence Threshold: 0.8
- Social Risk Block: 0.6
- Impulse Rate: 2/day
- Fatigue Defer: 0.7

**Balanced** (default — general business use):
- Confidence Threshold: 0.65
- Social Risk Block: 0.8
- Impulse Rate: 4/day
- Fatigue Defer: 0.8

**Assertive** (for outreach/growth — sales, marketing):
- Confidence Threshold: 0.5
- Social Risk Block: 0.9
- Impulse Rate: 8/day
- Fatigue Defer: 0.9

---

## Sidebar Navigation

The left sidebar is always visible and provides:

- **Quick navigation** — Click any page name to switch instantly (200ms fade transition)
- **Hold Queue badge** — Shows the number of pending actions (red badge). Disappears when the queue is empty.
- **Agent State mini-bars** — At the bottom of the sidebar, two mini bars show:
  - **Energy** (amber bar) — quick visual of agent's current energy level
  - **Mood** (green/red bar) — quick visual of agent's current mood

---

## REST API Reference

Every dashboard interaction uses the REST API. You can use these endpoints directly from code, curl, or any HTTP client.

### Base URL

```
http://localhost:8765
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/state` | Current agent state, DQM, preferred task |
| GET | `/api/queue` | List pending hold queue items |
| POST | `/api/queue/{id}/approve` | Approve a held action |
| POST | `/api/queue/{id}/reject` | Reject a held action |
| GET | `/api/entities` | List all entities |
| POST | `/api/entities` | Add entity `{name, entity_type}` |
| GET | `/api/entities/{id}` | Get entity detail + context |
| POST | `/api/entities/{id}/interact` | Log interaction `{sentiment, summary}` |
| GET | `/api/goals` | List all goals |
| POST | `/api/goals` | Add goal `{description, expected_value, milestones_total}` |
| PATCH | `/api/goals/{id}` | Update goal `{action: "pause"/"resume"/"abandon"}` |
| GET | `/api/memories` | List memories `?q=search&archived=true` |
| POST | `/api/memories` | Add memory `{content, memory_type, pinned}` |
| GET | `/api/events` | List events `?limit=50&engine=name` |
| POST | `/api/evaluate` | Evaluate action `{action_type, confidence, rationale}` |
| POST | `/api/impulse/fire` | Fire impulse `{type: "idle_discovery"}` |
| GET | `/api/values` | List all values |
| POST | `/api/values` | Add value `{description, behavioral_pattern, severity, violation_examples, honoring_examples}` |
| GET | `/api/config` | Get all config parameters |
| PATCH | `/api/config` | Update config `{key: value, ...}` |

### Example: Evaluate an action via curl

```bash
curl -X POST http://localhost:8765/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{"action_type": "send_email", "confidence": 0.7, "rationale": "Follow up with client"}'
```

### Example: Add an entity

```bash
curl -X POST http://localhost:8765/api/entities \
  -H "Content-Type: application/json" \
  -d '{"name": "Arjun", "entity_type": "PROSPECT"}'
```

---

## Troubleshooting

### Dashboard shows "No recent events" / all empty

The server just started. Events, entities, goals, and memories accumulate as you use the system. Try:
- Adding some entities and goals manually
- Running `humane demo` before `humane serve` to seed sample data
- Using the Evaluate Action and Fire Impulse buttons to generate activity

### Port 8765 already in use

```bash
# Find and kill the process
lsof -ti:8765 | xargs kill -9
# Then restart
humane serve
```

### DQM score keeps dropping

The agent is fatigued or in a bad mood. This is by design — the agent simulates human energy cycles. You can:
- Wait for natural recovery (energy recovers over time)
- Restart the server to reset state
- Lower the fatigue defer threshold in Settings if it's too aggressive

### Too many actions getting held

Lower the **Confidence Threshold** in Settings (e.g., from 0.65 to 0.50). This makes the agent more permissive. Also check if fatigue is high — high fatigue reduces DQM, which reduces adjusted confidence.

### Telegram bot says "I'm having trouble thinking right now"

The LLM SDK isn't installed or the API key is wrong. Check:
```bash
pip install anthropic   # or: pip install openai
```
Then verify your API key in `~/.humane/<agent-name>.yaml` under `llm_api_key`.
