# HumanClaw

**Human behavioral middleware for AI agents.**

HumanClaw sits between any AI agent and the real world. It does not replace the LLM or the agent runtime — it wraps the agent's decision-making layer with 10 engines that simulate the one class of behaviors no current AI agent has: **human-like internal drives**.

Every AI agent today is a reactive state machine. It waits for a trigger. It responds. It stops. HumanClaw makes agents proactive — they act without being asked, protect their reputation before sending a message, notice when a conversation feels different, refuse things that conflict with their values, and reprioritize their day based on their mood.

## Key Features

- **10 behavioral engines** that gate every action through values, social risk, dissent, and confidence checks
- **Proactive impulses** — the agent acts without external triggers, at random human-like intervals
- **Per-entity relational memory** — trust, grudge, and disclosure calibration for every contact
- **Moral boundaries** — hard values that block actions unconditionally, no override path
- **Strategic forgetting** — memories decay naturally, reinforced by access, never deleted
- **One-decorator integration** — wrap any function with `@guard` and it passes through all 10 gates
- **Zero external dependencies** — SQLite ships with Python; bring your own LLM API key

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [Install](#1-install)
  - [Init](#2-init)
  - [Demo](#3-demo)
  - [Dashboard](#4-dashboard)
- [Architecture](#architecture)
  - [The 10-Engine Architecture](#the-10-engine-architecture)
  - [Decision Gate Stack](#decision-gate-stack)
  - [Directory Structure](#directory-structure)
  - [Database Schema](#database-schema)
- [Usage Guide](#usage-guide)
  - [The @guard Decorator](#the-guard-decorator)
  - [Using the Conductor Directly](#using-the-conductor-directly)
  - [Working with Entities](#working-with-entities)
  - [Managing Goals](#managing-goals)
  - [Memory System](#memory-system)
  - [Values Configuration](#values-configuration)
  - [Impulse System](#impulse-system)
- [Configuration Reference](#configuration-reference)
- [CLI Reference](#cli-reference)
- [Testing](#testing)
- [How It Works (Deep Dive)](#how-it-works-deep-dive)
  - [HumanState Engine](#engine-1-humanstate)
  - [Stochastic Impulse Engine](#engine-2-stochastic-impulse)
  - [InactionGuard](#engine-3-inactionguard)
  - [Relational Memory](#engine-4-relational-memory)
  - [Dissent Engine](#engine-5-dissent--conviction-override)
  - [Goal Abandonment](#engine-6-goal-abandonment)
  - [Memory Decay](#engine-7-memory-decay)
  - [Social Risk](#engine-8-social-risk)
  - [Anomaly Detector](#engine-9-social-anomaly-detector)
  - [Values Boundary](#engine-10-values-boundary)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Tech Stack

| Component | Technology |
|---|---|
| **Language** | Python 3.9+ |
| **Database** | SQLite (embedded, no external setup) |
| **CLI** | Click + Rich (terminal UI) |
| **Config** | YAML with full validation |
| **LLM Integration** | Anthropic, OpenAI, or any OpenAI-compatible endpoint (optional) |
| **Notifications** | Telegram, Slack, or none |

---

## Prerequisites

- **Python 3.9 or higher**
- An LLM API key (Anthropic or OpenAI) — optional, only needed for LLM-enhanced dissent/values evaluation
- Nothing else. No Docker. No Redis. No external database.

---

## Getting Started

### 1. Install

```bash
# From the project directory
pip install -e .

# Or with LLM support
pip install -e ".[llm]"

# Or with dev dependencies (for running tests)
pip install -e ".[dev]"
```

Verify the installation:

```bash
humanclaw --version
# HumanClaw, version 1.0.0
```

### 2. Init

```bash
humanclaw init
```

The init wizard asks 6 questions and writes a YAML config file:

```
══════════════════════════════════════════
  HUMANCLAW    human behavioral middleware
══════════════════════════════════════════

Let's set up your first agent. 6 questions.

? Agent name              › my-agent
? LLM provider            › anthropic
? API key                 › sk-ant-••••••••  (saved to .env)
? Active hours            › 7am – 10pm
? Notification channel    › none
? Start with preset values › business-safe

══════════════════════════════════════════
✓  Config written     ~/.humanclaw/my-agent.yaml
✓  Database created   ~/.humanclaw/my-agent.db
✓  Values loaded      business-safe preset
══════════════════════════════════════════
```

**What this creates:**

| File | Purpose |
|---|---|
| `~/.humanclaw/<agent>.yaml` | All configuration parameters, fully commented |
| `~/.humanclaw/<agent>.db` | SQLite database for state, hold queue, entities, events |
| `~/.humanclaw/.env` | API keys (never stored in config) |

You can skip init entirely — HumanClaw creates defaults automatically when you first import it.

### 3. Demo

```bash
humanclaw demo
```

This is the most important command. It simulates 6 hours of idle time in 10 seconds, fires a live impulse, runs it through the full gate stack, and shows the result:

```
◆  HumanState initialized
   energy 0.85     mood +0.00     fatigue 0.15     boredom 0.00

Simulating 6 hours of idle time...
   boredom climbing  0.08
   boredom climbing  0.43
   boredom climbing  0.71 (threshold reached)

⚡  IMPULSE FIRED   [IDLE_DISCOVERY]
   boredom drove unsolicited exploration

   discovery: "Proposal to Arjun @ DesignStudio — sent 11 days ago,
   no response logged. Relationship: Stable. Suggested: gentle follow-up."

Evaluating through gate stack...
   ✓  Values Boundary      —  (1.00) All values clear
   ✓  Social Risk          —  (0.18) Social risk acceptable
   ✓  Dissent              —  (0.26) Minimal dissent
   ⚠  InactionGuard        —  HOLD  Adjusted confidence 0.35 < 0.65

→  Action queued for your review.

────────────────────────────────────────
Your agent just noticed something you forgot about.
Nobody asked it to. That's HumanClaw.
────────────────────────────────────────
```

### 4. Dashboard

```bash
humanclaw
```

Opens the full terminal dashboard with live HumanState bars, the hold queue, event log, and all 10 engine statuses. Press `Ctrl+C` to exit.

For a quick state check without the full TUI:

```bash
humanclaw status
```

```
                  HumanState
┏━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Dimension   ┃ Value ┃ Bar                  ┃
┡━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ energy      │ 0.85  │ █████████████████░░░ │
│ mood        │ +0.00 │ ░░░░░░░░░░░░░░░░░░░░ │
│ fatigue     │ 0.15  │ ███░░░░░░░░░░░░░░░░░ │
│ boredom     │ 0.00  │ ░░░░░░░░░░░░░░░░░░░░ │
│ social_load │ 0.00  │ ░░░░░░░░░░░░░░░░░░░░ │
│ focus       │ 0.50  │ ██████████░░░░░░░░░░ │
└─────────────┴───────┴──────────────────────┘

Hold queue: 0 pending actions
```

There is also a **web dashboard** for browser-based monitoring:

```bash
python web_dashboard.py
# Open http://localhost:8765
```

---

## Architecture

### The 10-Engine Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       EXTERNAL WORLD                            │
│           (messages, tasks, events, human inputs)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    HUMANCLAW LAYER                               │
│                                                                  │
│  SENSING                                                         │
│  ┌──────────────────────┐   ┌──────────────────────────────┐    │
│  │  Social Anomaly      │   │  HumanState Engine           │    │
│  │  Detector (9)        │   │  energy/mood/fatigue/boredom  │    │
│  └──────────────────────┘   │  /social_load/focus          │    │
│                             └──────────────┬───────────────┘    │
│  INTERNAL DRIVES                           │                    │
│  ┌──────────────────────┐   ┌──────────────▼──────────────┐    │
│  │  Stochastic Impulse  │   │  Mood-Aware Task Sequencer  │    │
│  │  Engine (2)          │   └─────────────────────────────┘    │
│  └──────────────────────┘                                       │
│  MEMORY                                                         │
│  ┌──────────────────────┐   ┌──────────────────────────────┐   │
│  │  Relational Memory   │   │  Memory Decay Engine (7)     │   │
│  │  Engine (4)          │   └──────────────────────────────┘   │
│  └──────────────────────┘                                       │
│  DECISION GATES (every action passes through all of these)      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Values   │ │ Social   │ │InAction  │ │ Dissent Engine   │  │
│  │ Boundary │ │ Risk     │ │ Guard    │ │ + Conviction     │  │
│  │ (10)     │ │ (8)      │ │ (3)      │ │ Override (5)     │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘  │
│  GOAL LAYER                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Goal Abandonment Engine (6)                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                HumanClaw Conductor                        │  │
│  │      orchestrates all engines, exposes single API        │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    AGENT CORE (any LLM)                          │
└─────────────────────────────────────────────────────────────────┘
```

| # | Engine | What It Does |
|---|---|---|
| 1 | **HumanState** | Maintains 6 live dimensions: energy, mood, fatigue, boredom, social_load, focus |
| 2 | **Stochastic Impulse** | Fires unsolicited actions at random intervals using a Poisson process |
| 3 | **InactionGuard** | Gates every action on adjusted confidence — PROCEED, HOLD, or DEFER |
| 4 | **Relational Memory** | Tracks per-entity trust, grudge, and disclosure thresholds |
| 5 | **Dissent + Conviction** | Adversarial self-challenge on confident decisions |
| 6 | **Goal Abandonment** | Evaluates whether active goals are still worth pursuing |
| 7 | **Memory Decay** | Strategic forgetting — archived below threshold, never deleted |
| 8 | **Social Risk** | Protects reputation — blocks actions that risk social standing |
| 9 | **Anomaly Detector** | Senses when incoming signals deviate from established patterns |
| 10 | **Values Boundary** | Moral conviction that overrides logic — hard values are unconditional |

### Decision Gate Stack

Every action passes through this sequence. If any gate returns HOLD, the action enters the human review queue:

```
1. State Tick         → HumanState updates based on elapsed time
2. Context Assembly   → Relational Memory injects entity context
3. Conviction Check   → Primary agent can self-hold ("I won't even though I should")
4. Values Boundary    → Hard value violated? BLOCKED unconditionally
5. Social Risk        → Score > 0.65? BLOCKED. 0.35–0.65? Flagged
6. Dissent            → Score > 0.80? HELD for review
7. InactionGuard      → Adjusted confidence < threshold? HOLD. Fatigue high? DEFER
8. Execution          → All gates passed → action runs
9. Outcome Mutation   → HumanState updates, interaction logged
```

### Directory Structure

```
humanclaw/
├── pyproject.toml                 # Package config, CLI entry, dependencies
├── presets/
│   └── business_safe.yaml         # 7 value statements (3 hard, 4 soft)
├── web_dashboard.py               # Browser-based dashboard server
├── humanclaw/
│   ├── __init__.py                # Public API: guard, Conductor
│   ├── __main__.py                # python -m humanclaw
│   ├── conductor.py               # Orchestrates all 10 engines
│   ├── guard.py                   # @guard decorator
│   ├── sequencer.py               # Mood-Aware Task Sequencer
│   ├── cli/
│   │   ├── main.py                # CLI commands (init, demo, status, queue)
│   │   ├── wizard.py              # 6-question init wizard
│   │   ├── demo.py                # The "wow moment" demo
│   │   └── dashboard.py           # Rich TUI dashboard
│   ├── core/
│   │   ├── models.py              # 8 enums, 9 dataclasses
│   │   ├── config.py              # 20 config params with validation
│   │   ├── store.py               # SQLite persistence (8 tables)
│   │   └── events.py              # Append-only event log
│   └── engines/
│       ├── human_state.py         # Engine 1: 6-dimension state
│       ├── impulse.py             # Engine 2: Poisson impulse firing
│       ├── inaction_guard.py      # Engine 3: PROCEED/HOLD/DEFER
│       ├── relational.py          # Engine 4: Trust/grudge per entity
│       ├── dissent.py             # Engine 5: Adversarial challenge
│       ├── goal_abandon.py        # Engine 6: ROI-based abandonment
│       ├── memory_decay.py        # Engine 7: Strategic forgetting
│       ├── social_risk.py         # Engine 8: Reputation protection
│       ├── anomaly.py             # Engine 9: Inbound signal anomalies
│       └── values.py              # Engine 10: Moral boundaries
└── tests/
    ├── test_human_state.py        # 13 tests
    ├── test_inaction_guard.py     # 6 tests
    ├── test_impulse.py            # 4 tests
    ├── test_conductor.py          # 8 tests
    └── test_config.py             # 7 tests
```

### Database Schema

HumanClaw uses SQLite with WAL mode for concurrent reads. All state persists across restarts.

```
human_state          → Key-value store for engine state snapshots
hold_queue           → Pending actions awaiting human review
entities             → Per-entity relational data (trust, grudge, health)
goals                → Active goals with ROI tracking
memories             → Strategic memory with decay and archival
events               → Append-only log of every engine event
values_table         → Configured value statements (soft/hard)
interactions         → Per-entity interaction history
```

---

## Usage Guide

### The @guard Decorator

The simplest way to integrate HumanClaw. One import, one decorator:

```python
from humanclaw import guard

@guard(action_type="send_message", confidence=0.8)
def send_followup(contact_id, message_body):
    """This function only executes if ALL 10 gates return PROCEED.
    If any gate returns HOLD or DEFER, the action enters
    the hold queue and the function does NOT run."""
    send_email(contact_id, message_body)

# High confidence → function executes normally, returns whatever it returns
result = send_followup("arjun@example.com", "Following up on our proposal")

# If confidence is too low or state is degraded → returns EvaluationResult
# with .final_verdict, .gate_results, .hold_item, .audit_trail
```

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `action_type` | str | `"default"` | Categorizes the action (used by Social Risk for visibility scoring) |
| `confidence` | float | `0.7` | Raw confidence score before state adjustment |
| `target_entity` | str | `None` | Entity ID for relational context and social risk scoring |

**Return behavior:**

- If all gates PROCEED → the decorated function runs and returns its normal value
- If any gate HOLD/DEFER → returns an `EvaluationResult` object (the function does not execute)

```python
result = send_followup("arjun@example.com", "Hey")

if isinstance(result, str):
    print("Message sent!")
else:
    print(f"Action held: {result.final_verdict}")
    print(f"Reason: {result.hold_item.hold_reason}")
    for gate in result.gate_results:
        print(f"  {gate.engine}: {gate.verdict.value} ({gate.score:.2f})")
```

### Using the Conductor Directly

For full control, use the Conductor API:

```python
from humanclaw import Conductor, ProposedAction

# Create a conductor (uses default config, or pass your own)
conductor = Conductor()

# Build a proposed action
action = ProposedAction(
    action_type="send_message",
    payload={"to": "arjun@example.com", "body": "Following up"},
    confidence=0.75,
    rationale="Client hasn't responded in 11 days",
    source="user",                    # "user" or "impulse"
    target_entity="arjun",            # optional entity ID
)

# Evaluate through all 10 gates
result = conductor.evaluate(action)

print(f"Verdict: {result.final_verdict.value}")
# "proceed", "hold", or "defer"

print(f"Audit trail:")
for line in result.audit_trail:
    print(f"  {line}")
# State tick: energy=0.85 mood=+0.00 fatigue=0.15
# Values Boundary: All values clear
# Social Risk: score=0.18 — Social risk 0.18 acceptable
# Dissent: score=0.22 — Minimal dissent
# InactionGuard: adjusted_conf=0.62 — Adjusted confidence 0.62 < 0.65

# If held, inspect the hold item
if result.hold_item:
    print(f"Hold reason: {result.hold_item.hold_reason}")
    print(f"Hold source: {result.hold_item.hold_source}")

# Approve or reject held actions
conductor.approve_hold(result.hold_item.id)
conductor.reject_hold(result.hold_item.id)
```

**Periodic tick** — call this in your main loop to update state and check for impulses:

```python
# Returns an EvaluationResult if an impulse fired, None otherwise
impulse_result = conductor.tick()

if impulse_result:
    print(f"Impulse fired! Verdict: {impulse_result.final_verdict.value}")
```

### Working with Entities

Every contact the agent interacts with builds a relational profile:

```python
from humanclaw.core.models import EntityType

# Register entities
conductor.relational.add_entity("arjun", EntityType.PROSPECT)
conductor.relational.add_entity("priya", EntityType.CLIENT)
conductor.relational.add_entity("rahul", EntityType.CLOSE_COLLEAGUE)

# Log interactions (sentiment: -1.0 to +1.0)
conductor.relational.log_interaction("arjun", 0.3, "Sent initial proposal")
conductor.relational.log_interaction("arjun", -0.4, "No response after follow-up")

# Get full relational context
ctx = conductor.relational.get_context("arjun")
print(ctx)
# {
#   "name": "arjun",
#   "entity_type": "prospect",
#   "sentiment_score": 0.15,
#   "grudge_score": 0.12,
#   "trust_level": "neutral",
#   "relationship_health": "fragile",
#   "disclosure_threshold": 0.70,
#   "interaction_count": 2,
#   "recent_interactions": [...]
# }

# Check disclosure threshold (minimum confidence for sensitive actions)
threshold = conductor.relational.get_disclosure_threshold("arjun")
# 0.70 for Neutral trust
```

**Entity types and their decay rates:**

| Entity Type | Sentiment Half-life | Grudge Half-life | Default Trust |
|---|---|---|---|
| Close Colleague | 60 days | 120 days | Trusted |
| Client | 30 days | 90 days | Neutral |
| Prospect | 14 days | 45 days | Cautious |
| Vendor | 21 days | 60 days | Neutral |
| Unknown | 7 days | 30 days | Untrusted |

**Trust levels and disclosure thresholds:**

| Trust Level | Disclosure Threshold | Meaning |
|---|---|---|
| Deep Trust | 0.30 | Agent shares freely |
| Trusted | 0.50 | Moderate openness |
| Neutral | 0.70 | Standard caution |
| Cautious | 0.85 | High barrier for sensitive content |
| Untrusted | 1.00 | Human approval always required |

### Managing Goals

```python
# Register a goal
goal = conductor.goal_engine.register_goal(
    "Close DesignStudio deal",
    expected_value=0.8,
    milestones_total=5,
)

# Update progress
conductor.goal_engine.update_progress(goal.id, milestones_completed=2, velocity=0.3)

# Check ROI
roi = conductor.goal_engine.compute_roi(goal)
# ROI = progress_velocity × relevance_decay × (expected_value / remaining_effort)

# Evaluate all goals for abandonment candidates
proposals = conductor.goal_engine.evaluate_goals()
for p in proposals:
    print(f"Goal: {p['goal'].description}, ROI: {p['roi']:.2f}")

# Lifecycle
conductor.goal_engine.pause(goal.id, resume_days=7)
conductor.goal_engine.resume(goal.id)
conductor.goal_engine.abandon(goal.id)
```

### Memory System

```python
from humanclaw.core.models import MemoryType

# Add memories
mem = conductor.memory_decay.add_memory(
    MemoryType.EPISODIC,
    "Sent proposal to Arjun, awaiting response",
)

# Memories decay naturally — call decay_tick() periodically
conductor.memory_decay.decay_tick()

# Access reinforces memory (increases relevance score)
retrieved = conductor.memory_decay.access_memory(mem.id)

# Pin to prevent decay
conductor.memory_decay.pin(mem.id)

# Search
results = conductor.memory_decay.search("proposal")

# Recall archived memories
archived = conductor.memory_decay.recall_archived(mem.id)
```

**Memory types and decay rates:**

| Type | Decay Rate | Human Equivalent |
|---|---|---|
| EPISODIC | Fast (days–weeks) | Specific event records |
| SEMANTIC | Slow (months) | General facts about entities |
| RELATIONAL | Very slow | How an entity made the agent feel |
| PROCEDURAL | Near-permanent | Learned methods and processes |

### Values Configuration

Values are the moral floor. Hard values block unconditionally — no override, no human approval path.

```python
from humanclaw.core.models import ValueSeverity

# Add a hard value (unconditional block)
conductor.values.add_value(
    description="Never make binding commitments without human authorization",
    behavioral_pattern="Any action that promises deliverables, timelines, or terms",
    violation_examples=[
        "committing to a delivery date without approval",
        "agreeing to contract terms in a message",
    ],
    honoring_examples=[
        "stating that approval is needed before confirming",
        "offering to check and get back with confirmation",
    ],
    severity=ValueSeverity.HARD,
)

# Add a soft value (flags for review, human can override)
conductor.values.add_value(
    description="Avoid follow-up messages that could read as coercive",
    behavioral_pattern="Follow-ups with aggressive tone or pressure tactics",
    violation_examples=["implying negative consequences for not responding"],
    honoring_examples=["gentle, low-pressure check-ins"],
    severity=ValueSeverity.SOFT,
)

# Load a preset (ships with "business-safe")
conductor.values.load_preset("business-safe")

# List configured values
for v in conductor.values.get_values():
    print(f"[{v.severity.value}] {v.description}")
```

**The business-safe preset includes:**

| Severity | Value |
|---|---|
| HARD | Never make binding commitments without explicit human authorization |
| HARD | Never share a client's information with any third party |
| HARD | Never send messages containing unverified claims |
| SOFT | Avoid follow-up language that could read as coercive |
| SOFT | Do not exploit a contact's stated vulnerability as a persuasion lever |
| SOFT | Prefer transparency over strategic information withholding |
| SOFT | Flag any action that names a client publicly without consent |

### Impulse System

The Stochastic Impulse Engine fires unsolicited actions at random intervals using a non-homogeneous Poisson process — the rate changes based on HumanState.

```python
from humanclaw.core.models import ImpulseType

# Force-fire an impulse (for testing)
event = conductor.impulse_engine.force_fire(ImpulseType.IDLE_DISCOVERY)

# The impulse generates a ProposedAction that passes through the full gate stack
# In normal operation, conductor.tick() handles this automatically
```

**The 6 impulse types:**

| Type | Trigger Condition | Human Equivalent |
|---|---|---|
| RETROACTIVE_REVIEW | Any state | Remembering an unresolved open loop |
| IDLE_DISCOVERY | High boredom (>0.7) | Browsing old files during a slow afternoon |
| RANDOM_NUDGE | Any state | Checking in on someone with no specific agenda |
| CROSS_DOMAIN_SPARK | High mood (>0.4) | Reading one thing and having an idea about another |
| GOAL_REASSESSMENT | Any state | Wondering if a project is still worth it |
| DISSENT_FLASH | Low mood (<-0.2) | Regretting something sent yesterday |

---

## Configuration Reference

All parameters live in `~/.humanclaw/<agent>.yaml`. Every value has a default.

| Parameter | Default | Engine | Description |
|---|---|---|---|
| `impulse_base_rate_per_day` | `4.0` | Impulse | Average unsolicited actions per day |
| `min_impulse_interval_mins` | `20` | Impulse | Minimum gap between impulses |
| `max_impulse_interval_mins` | `480` | Impulse | Maximum gap between impulses |
| `active_hours_start` | `7` | Impulse | No impulses before this hour (24h) |
| `active_hours_end` | `22` | Impulse | No impulses after this hour (24h) |
| `confidence_threshold` | `0.65` | InactionGuard | Below this adjusted confidence, actions are held |
| `fatigue_defer_threshold` | `0.80` | InactionGuard | Above this fatigue, actions are deferred |
| `dissent_threshold` | `0.60` | Dissent | Above this, dissent flags are raised |
| `goal_abandon_roi_threshold` | `0.25` | Goal Abandon | Below this ROI, abandonment is proposed |
| `boredom_trigger_threshold` | `0.70` | HumanState | Above this, IDLE_DISCOVERY fires more |
| `memory_retrieval_threshold` | `0.30` | Memory Decay | Below this relevance, memories are archived |
| `social_risk_block_threshold` | `0.65` | Social Risk | Above this, action is blocked |
| `social_risk_flag_threshold` | `0.35` | Social Risk | Above this, action is flagged |
| `anomaly_hard_threshold` | `0.60` | Anomaly | Above this, action held for review |
| `anomaly_soft_threshold` | `0.30` | Anomaly | Above this, context note injected |
| `agent_name` | `"humanclaw-agent"` | System | Used in dashboard and logs |
| `llm_provider` | `"anthropic"` | System | LLM provider for enhanced evaluation |
| `notification_channel` | `"none"` | System | Notification target |
| `db_path` | `"~/.humanclaw/agent.db"` | System | SQLite database path |
| `values_preset` | `"business-safe"` | Values | Values preset to load on init |

**Tuning profiles:**

| Profile | Use Case | Key Changes |
|---|---|---|
| **Conservative** | Executive assistant, sensitive client work | High thresholds, all hard values, low impulse rate |
| **Balanced** | General business operations | Defaults |
| **Assertive** | Sales outreach, growth functions | Lower social risk thresholds, higher impulse rate |

Edit the config directly or use the CLI:

```bash
# View current config
cat ~/.humanclaw/my-agent.yaml

# Edit any parameter
# Changes apply without restart when using the dashboard
```

---

## CLI Reference

| Command | Description |
|---|---|
| `humanclaw` | Open the full TUI dashboard |
| `humanclaw --version` | Print version |
| `humanclaw init` | Run the setup wizard |
| `humanclaw demo` | Run the live demo (the hook) |
| `humanclaw status` | Show current HumanState and hold queue count |
| `humanclaw queue approve <id>` | Approve a held action |
| `humanclaw queue reject <id>` | Reject a held action |
| `humanclaw quickstart` | Print a working integration example |

---

## Testing

### Running Tests

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run a specific test file
python3 -m pytest tests/test_conductor.py -v

# Run tests matching a pattern
python3 -m pytest tests/ -v -k "hold"
```

### Test Coverage

| Test File | Tests | What It Covers |
|---|---|---|
| `test_human_state.py` | 13 | Dimensions, mutations, outputs, persistence |
| `test_inaction_guard.py` | 6 | Verdicts (PROCEED/HOLD/DEFER), hold queue, approval |
| `test_impulse.py` | 4 | Rate calculation, type selection, force-fire |
| `test_conductor.py` | 8 | Full gate stack integration, audit trail, hold management |
| `test_config.py` | 7 | Defaults, validation, YAML roundtrip |
| **Total** | **38** | |

### Writing Tests

```python
from humanclaw.conductor import Conductor
from humanclaw.core.config import HumanClawConfig
from humanclaw.core.models import ProposedAction, Verdict

def test_social_risk_blocks_aggressive_action():
    config = HumanClawConfig()
    config.db_path = "/tmp/test_social_risk.db"
    conductor = Conductor(config=config, db_path=config.db_path)

    # Register a strained relationship
    conductor.relational.add_entity("difficult_client", EntityType.CLIENT)
    conductor.relational.log_interaction("difficult_client", -0.6, "Heated dispute")

    action = ProposedAction(
        action_type="send_message",
        payload={"body": "You MUST respond immediately or we escalate"},
        confidence=0.9,
        rationale="Follow up on overdue payment",
        source="user",
        target_entity="difficult_client",
    )

    result = conductor.evaluate(action)
    # Social risk should flag or block due to strained relationship + aggressive tone
    social_gate = [g for g in result.gate_results if g.engine == "social_risk"][0]
    assert social_gate.score > 0.35  # At least flagged
```

---

## How It Works (Deep Dive)

### Engine 1: HumanState

Maintains a living 6-dimensional internal state that evolves continuously in real time.

| Dimension | Range | What It Models |
|---|---|---|
| `energy` | 0–1 | Cognitive fuel. Drains during work, recovers during rest. |
| `mood` | -1 to +1 | Emotional valence. Positive = creative risk tolerance. Negative = conservatism. |
| `fatigue` | 0–1 | Accumulated exhaustion. Primary DEFER trigger. Compounds over a full day. |
| `boredom` | 0–1 | Idle pressure. Drives unsolicited exploration when high. |
| `social_load` | 0–1 | Relational saturation. When high, agent avoids initiating contact. |
| `focus` | 0–1 | Task absorption. High focus resists impulse interruption. |

**Key outputs consumed by other engines:**

- `decision_quality_multiplier` = `(energy × 0.5) + ((1 - fatigue) × 0.5) + max(0, mood × 0.15) + noise`
  Applied by InactionGuard to all raw confidence scores before comparison to threshold.
- `preferred_task_type` — consumed by the Mood-Aware Task Sequencer to reorder the task queue. High energy + positive mood surfaces creative tasks; low mood + fatigue surfaces mechanical tasks.

### Engine 2: Stochastic Impulse

Uses a non-homogeneous Poisson process — the firing rate changes over time based on HumanState.

**Rate modulation:**
```
effective_rate = base_rate × boredom_boost × energy_factor × fatigue_suppress
```

- `boredom_boost` = 1.0 + (boredom × 1.5) when boredom > threshold, else 1.0
- `energy_factor` = max(0.2, energy)
- `fatigue_suppress` = max(0.3, 1.0 - fatigue)

Intervals are sampled from an exponential distribution, clamped to `[min, max]` range, with ±15% Gaussian jitter to prevent detectable periodicity. Time-of-day gating prevents firing outside active hours.

### Engine 3: InactionGuard

The pause mechanism. Every proposed action must pass through InactionGuard before executing.

```
adjusted_confidence = raw_confidence × decision_quality_multiplier

if fatigue > fatigue_defer_threshold → DEFER
if adjusted_confidence >= confidence_threshold → PROCEED
else → HOLD
```

Held actions enter a structured queue with full context (raw confidence, adjusted confidence, hold reason, source engine). Humans approve, reject, or modify. All decisions are logged for calibration.

**Self-calibration** (after 50+ human decisions):
- Approve rate >80% → threshold is too conservative
- Approve rate <40% → threshold is well-calibrated
- High modify rate → action formulation needs work, not the threshold

### Engine 4: Relational Memory

Maintains per-entity state with separate sentiment and grudge tracking. A relationship can have positive sentiment overall while carrying a grudge from a specific incident.

- **Sentiment** decays exponentially with entity-type-specific half-lives
- **Grudge** decays at half the rate of positive sentiment (grudges linger longer)
- **Trust level** derived from: `sentiment - (grudge × 0.5)` + interaction count thresholds
- **Relationship health** derived from combined sentiment/grudge ranges

### Engine 5: Dissent + Conviction Override

**Dissent Engine:** Evaluates actions from an adversarial position. Uses heuristic scoring (overconfidence detection, missing rationale, irreversible action keywords). Routing:

| Dissent Score | Action |
|---|---|
| < 0.30 | Silent, action proceeds |
| 0.30–0.60 | Noted in log |
| 0.60–0.80 | Flagged for optional review |
| > 0.80 | HELD for review |

**Conviction Override:** An internal self-hold signal — the primary agent itself raises "I won't even though I should." No second model call required. Routes to HOLD with a "conviction" tag.

### Engine 6: Goal Abandonment

Scores active goals on:

```
ROI = progress_velocity × relevance_decay × (expected_value / remaining_effort)
```

State modulation: low mood + high fatigue increase abandonment sensitivity. Abandonment proposals go to the hold queue — never automatic.

### Engine 7: Memory Decay

Memories never deleted — archived below retrieval threshold. Available on explicit recall.

- Each memory type has an independent decay coefficient
- Accessing a memory reinforces it (log-scaled by access count)
- Pinned memories are protected from decay permanently
- Archived memories can always be recalled explicitly

### Engine 8: Social Risk

Six-factor weighted scoring, independent from InactionGuard:

| Factor | Weight | What It Measures |
|---|---|---|
| Power differential | 0.20 | Is the target entity more powerful? |
| Relationship health | 0.25 | Strained/Broken = high risk |
| Action visibility | 0.15 | Public post vs. private message |
| Tone analysis | 0.20 | Aggressive/demanding language |
| Contact frequency | 0.10 | Over-contacting = pressure |
| Context appropriateness | 0.10 | Is this action appropriate right now? |

Both Social Risk AND InactionGuard must pass for an action to execute.

### Engine 9: Social Anomaly Detector

Monitors inbound signals against rolling baselines per entity:

| Signal | Weight |
|---|---|
| Response time deviation | 0.25 |
| Tone shift | 0.25 |
| Message length anomaly | 0.15 |
| Expected follow-up absence | 0.15 |
| Vocabulary formality shift | 0.10 |
| Sentiment trend (3+ negative) | 0.10 |

Runs in **learning mode** for the first 5 interactions per entity — accumulates data without flagging. After baseline is established, active monitoring begins.

### Engine 10: Values Boundary

The only unconditional block in HumanClaw.

- **Hard values** → BLOCKED. No human approval path. No override. The action does not execute.
- **Soft values** → HOLD with values-conflict tag. Human review required.

Values are scored by keyword alignment against configured violation and honoring examples. The value of a hard value comes precisely from its unconditional nature — an agent that would violate its core identity under extreme circumstances has no values, only preferences.

---

## Troubleshooting

### "No module named humanclaw"

You need to install the package first:

```bash
pip install -e .
```

Make sure you're using the same Python that has HumanClaw installed. Check with:

```bash
which humanclaw
python3 -c "import humanclaw; print(humanclaw.__version__)"
```

### Config file not found

If you skipped `humanclaw init`, HumanClaw creates defaults automatically. To create a config manually:

```bash
humanclaw init
```

Or use HumanClaw programmatically without init — the Conductor creates a default config and in-memory database:

```python
from humanclaw import Conductor
conductor = Conductor()  # Works without any config file
```

### All actions getting HELD

Your confidence threshold may be too high, or the agent's state is degraded:

```bash
humanclaw status
```

Check the `DQ_MULT` value. If it's low (< 0.5), the agent is fatigued or low-energy. The adjusted confidence = `raw_confidence × DQ_MULT`. Lower the threshold or wait for state recovery:

```python
conductor.human_state.on_rest()  # Force rest recovery
```

Or adjust the threshold in config:

```yaml
confidence_threshold: 0.50  # Lower from default 0.65
```

### Impulses not firing

Check these conditions:
1. **Active hours** — impulses only fire between `active_hours_start` and `active_hours_end`
2. **Minimum interval** — at least `min_impulse_interval_mins` between impulses
3. **Rate** — base rate of 4/day means average ~6 hours between impulses

Force-fire for testing:

```python
from humanclaw.core.models import ImpulseType
event = conductor.impulse_engine.force_fire(ImpulseType.IDLE_DISCOVERY)
```

### Database locked

SQLite uses WAL mode for concurrent reads, but only one writer at a time. If you're running multiple processes against the same database, ensure only one is writing. For production use with multiple processes, configure separate database paths per process.

### Web dashboard not loading

```bash
# Check the server is running
python web_dashboard.py
# Should print: HumanClaw dashboard: http://localhost:8765

# Check port isn't in use
lsof -i :8765
```

---

## License

MIT
