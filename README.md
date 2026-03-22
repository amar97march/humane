# Humane

**Human behavioral middleware for AI agents.**

Humane is an AI companion that behaves like a thoughtful human colleague. Unlike regular chatbots that just respond to commands, Humane:
- **Remembers** things you told it and follows up
- **Initiates** conversations on its own ("Hey, you haven't called Arjun in 12 days")
- **Judges** its own actions before taking them (10 internal engines evaluate every decision)
- **Learns** your patterns and adapts over time
- **Has values** it won't violate, even under pressure

---

## Getting Started (3 minutes)

```bash
pip install -e ".[all]"
humane init              # Answer 3 questions: agent name, LLM API key, Telegram token
humane serve             # Starts everything
```

You now have:
- **Web dashboard** at `http://localhost:8765`
- **Telegram bot** — open Telegram, message your bot
- **REST API** — every feature accessible programmatically

### Docker (Alternative)

```bash
docker-compose up -d    # Runs everything in a container
```

Set environment variables: `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`.

---

## The Two Interfaces

### 1. Telegram/WhatsApp Bot

Talk to it naturally. It remembers, follows up, reminds you, and acts on its own.

```
You: "Remind me to call Arjun tomorrow"
Bot: "Got it, I'll check in tomorrow about calling Arjun."

[Next day]
Bot: "Hey — you wanted to call Arjun today. Still planning to?"
You: "Not now"
Bot: "No problem, I'll circle back later."

[4 hours later]
Bot: "Quick check — still not a good time for the Arjun call?"
```

The bot also:
- Cross-references topics ("Speaking of design, what about that DesignStudio proposal?")
- Backs off when you're stressed (detects short replies, negative tone)
- Surfaces forgotten tasks when you seem relaxed
- Sends a morning digest with stalling goals, neglected contacts, and pending actions

### 2. Web Dashboard

Manage everything visually at `localhost:8765`. Monitor state, approve actions, configure engines, view analytics.

---

## Dashboard Pages

### 1. Dashboard (Overview)

Your agent's 6 internal dimensions displayed as colored bars.

| Dimension | What it means | Effect on behavior |
|-----------|--------------|-------------------|
| Energy | Capacity to act | Low = defers tasks, lower decision quality |
| Mood | Emotional state (-1 to +1) | Negative = more cautious, higher social risk |
| Fatigue | Tiredness | Above 0.8 = ALL actions get held for review |
| Boredom | Understimulation | High = agent initiates more conversations |
| Social Load | Interaction saturation | High = agent avoids starting new contacts |
| Focus | Concentration | Low = prefers routine tasks over complex ones |

**What you can do**:
- **Evaluate Action** — Test any hypothetical action. Type "send_proposal", set confidence to 0.7, and see if the 10 engines would approve or block it.
- **Fire Impulse** — Make the agent act proactively right now (normally automatic).
- **Customize** — Drag widgets to reorder, hide sections you don't need.

**Example**: You notice DQM is 0.62 (low). Check the state bars — Fatigue is 0.85. That's why the agent is holding everything. Lower the Fatigue Defer Threshold in Settings, or approve urgent actions manually from the Hold Queue.

---

### 2. Entities (People & Contacts)

Every person the agent interacts with builds a relational profile.

| Field | What it means |
|-------|--------------|
| Trust | Untrusted → Cautious → Neutral → Trusted → Deep Trust |
| Sentiment | Weighted average of interaction quality (-1 to +1) |
| Grudge | Accumulated negative experiences (decays slowly) |
| Health | Strong / Stable / Fragile / Strained / Broken |

**What you can do**:
- **Add Entity** — Register a new contact (client, prospect, colleague, vendor)
- **View Timeline** — Click any entity to see full interaction history
- **Graph View** — Toggle to see a force-directed relationship network

**How sentiment decay works**:
- Prospects decay in 14 days (they go cold fast)
- Clients in 30 days
- Close colleagues in 60 days
- Grudges decay at half the rate — bad experiences linger, just like with humans

**Example**: You add "Arjun" as a prospect. After positive calls, trust moves toward "Trusted". Two weeks with no follow-up, sentiment decays. The agent notices and reminds you. If Arjun ghosts you, grudge builds up and the agent increases social risk on outgoing messages — protecting you from seeming desperate.

---

### 3. Goals (Objectives & ROI)

Active objectives with ROI tracking and milestone progress.

| ROI Color | Meaning | Action |
|-----------|---------|--------|
| Green (0.50+) | Healthy, keep going | Continue |
| Amber (0.25-0.49) | Slowing down | Check blockers |
| Red (below 0.25) | Low return | Consider abandoning |

**ROI formula**: `velocity × relevance × (expected_value / remaining_effort)`

**What you can do**:
- **Add Goal** — Set description, expected value, milestones
- **Use Template** — Pick from 6 pre-built templates (Sales Pipeline, Project Launch, Hiring, Content Campaign, Client Onboarding, Personal Growth)
- **Pause** — Temporarily suspend (no abandonment proposals)
- **Abandon** — Mark as no longer worth pursuing

**Example**: You create "Close DesignStudio deal" with 5 milestones. After sending the proposal (1/5 done), ROI climbs to 0.35. Two weeks pass with no response — ROI drops to 0.12. The agent says: "DesignStudio deal has stalled. Want to abandon or push through?" You click Pause while waiting for their response.

---

### 4. Memories (Knowledge Base)

Everything the agent knows, with relevance scores that decay over time.

| Memory Type | Decay Speed | Example |
|-------------|------------|---------|
| Episodic | Fast (days) | "Had a call with Arjun on March 15" |
| Semantic | Slow (weeks) | "Arjun's company does design work" |
| Relational | Very slow (months) | "Arjun is reliable but slow to respond" |
| Procedural | Near-permanent | "Always include case studies in proposals" |

**What you can do**:
- **Add Memory** — Store any fact, event, or pattern
- **Pin** — Protect from decay permanently (for critical info like NDA dates)
- **Search** — Find specific memories by content
- **View Archived** — See forgotten memories (still exist, just not auto-surfaced)

**How decay works**: Each memory starts at relevance 1.0. Over time it drops. Every time the agent retrieves a memory, relevance jumps back up (reinforcement). Below the threshold (default 0.3), it gets archived — still there, just not surfaced automatically.

**Example**: You store "Priya's company uses React Native". If the agent never references it, relevance decays to 0.25 and it gets archived. But when a mobile development conversation happens and the agent retrieves it, relevance jumps back up.

---

### 5. Values (Moral Boundaries)

The agent's ethical rules — the most powerful control mechanism.

| Type | What happens on violation | Can you override? |
|------|--------------------------|-------------------|
| **Hard** | Action BLOCKED immediately | No. Never. |
| **Soft** | Action HELD for your review | Yes, you can approve |

**Pre-loaded values** (business-safe preset):
- **Hard**: No unauthorized financial commitments
- **Hard**: No sharing client confidential data
- **Hard**: No false claims about products
- **Soft**: Avoid contacting outside business hours
- **Soft**: Prefer formal tone with new clients

**What you can do**:
- **Add Value** — Define a boundary with violation and honoring examples
- **Choose severity** — Hard for absolute rules, Soft for guidelines

**Example**: You add "Never share client revenue data" as Hard, with violation examples "forwarding client P&L to a competitor, sharing revenue in a public forum." Now if the agent tries to draft an email containing revenue figures to a non-client, the Values Boundary Engine blocks it — no approval path, no override. The action never happens.

---

### 6. Settings (Configuration)

All tunable parameters. Changes apply immediately — no restart needed.

| Setting | Default | What changing it does |
|---------|---------|---------------------|
| Confidence Threshold | 0.65 | Lower = more actions auto-approve. Higher = more held for review |
| Impulse Rate | 4/day | Higher = agent initiates more. Lower = quieter agent |
| Active Hours | 7am-10pm | Agent only fires impulses during these hours |
| Fatigue Defer | 0.80 | When fatigue exceeds this, ALL actions are deferred |
| Social Risk Block | 0.80 | Actions with social risk above this are blocked |

**Also on this page**:
- **API Security** — Enable auth, generate API keys, set rate limits
- **Data Retention** — Auto-delete old conversations/events after X days
- **Feedback & Tuning** — Export training data, auto-tune thresholds from your patterns
- **Plugins** — Toggle custom engines on/off
- **GDPR** — Export all data, right to erasure per entity

**Tuning profiles**:
- **Conservative** (legal, finance): Confidence 0.8, Social Risk Block 0.6, Impulse Rate 2/day
- **Balanced** (default): Confidence 0.65, Social Risk Block 0.8, Impulse Rate 4/day
- **Assertive** (sales, outreach): Confidence 0.5, Social Risk Block 0.9, Impulse Rate 8/day

**Example**: Your hold queue is always full. Go to Confidence Threshold (0.65), lower it to 0.50. Click Save. Immediately, more actions auto-approve. The agent keeps messaging at midnight — set Active Hours Start to 9, End to 18. Done.

---

### 7. Agents (Multi-Agent)

Run multiple independent agents from one dashboard.

**What you can do**:
- **Create Agent** — Each gets its own personality, database, goals, values
- **Switch** — Route all dashboard actions through a specific agent
- **Share** — Copy entities or goals between agents
- **Message** — Agents can send task handoffs to each other

**Example**: You run a design agency. Create "Sales Bot" (personality: assertive, high impulse rate) and "Support Bot" (personality: empathetic, high confidence threshold). A prospect becomes a client — share the entity from Sales Bot to Support Bot. Sales Bot sends a message: "Arjun just signed — needs onboarding." Support Bot picks it up and starts the onboarding goal.

---

## Additional Features

### Keyboard Shortcuts

Press `?` to see all shortcuts:

| Shortcut | Action |
|----------|--------|
| `g` then `o` | Go to Overview |
| `g` then `e` | Go to Entities |
| `g` then `g` | Go to Goals |
| `g` then `m` | Go to Memories |
| `g` then `v` | Go to Values |
| `g` then `s` | Go to Settings |
| `Space` | Approve first item in queue |
| `x` | Reject first item in queue |
| `n` | Open add form on current page |
| `Escape` | Close any modal |
| `?` | Show shortcuts help |

### Dark Mode

Click the sun/moon toggle in the sidebar footer. Preference saved to localStorage.

### Notifications

Bell icon in the header shows unread events (held actions, impulses, anomalies). Auto-polls every 10 seconds. Mark all read or clear from the dropdown.

### Daily Digest

Every morning at your configured hour, the bot sends a summary via Telegram/WhatsApp:
- Stalling goals (ROI < 0.3)
- Neglected contacts (no interaction in 14+ days)
- Pending approvals in the hold queue
- Sentiment alerts (entities trending negative)
- Agent state summary (energy, mood, fatigue)

### Predictive Insights

Auto-generated alerts on the Overview page:
- "Priya's sentiment is trending down — consider a check-in"
- "DesignStudio goal has stalled for 5 days"
- "Fatigue is 0.85 — rest recommended"
- "Arjun is approaching Trusted trust level"

### Smart Schedule

The Overview page shows "Best time to contact" suggestions based on historical interaction patterns — which day of the week and hour produces the best responses.

### Conversation Categories

Chat messages are auto-tagged: Sales, Support, Personal, Operations, Finance, Hiring. Filter by category in the Chat History tab.

### A/B Personality Testing

Run two personality variants simultaneously. The system randomly assigns variant A or B to each conversation and tracks: response sentiment, approval rate, and user satisfaction. Includes statistical significance testing (z-test).

### Conversation Simulator

"What would happen if I said X?" — enter a hypothetical message and see: predicted sentiment, state impact, gate verdict, and generated response. Compare mode lets you test 2-3 messages side by side.

### Goal Templates

6 pre-built templates with milestones:
- **Sales Pipeline**: Initial contact → Discovery → Proposal → Negotiation → Close
- **Project Launch**: Requirements → Design → Build → Test → Deploy → Review
- **Hiring**: Write JD → Source → Screen → Interview → Offer → Onboard
- **Content Campaign**: Strategy → Create → Review → Publish → Promote → Analyze
- **Client Onboarding**: Kickoff → Setup → Training → First deliverable → 30-day check
- **Personal Growth**: Define path → Course → Practice → Apply → Review

### Plugin System

Create custom engines that slot into the gate stack. Drop a `.py` file in `~/.humane/plugins/`:

```python
from humane.plugins import HumanePlugin
from humane.core.models import GateResult, Verdict

class MyPlugin(HumanePlugin):
    name = "rate-limiter"
    version = "1.0"

    def evaluate(self, action, context):
        # Your custom logic here
        return GateResult(engine=self.name, verdict=Verdict.PROCEED, score=0.0, reason="OK")
```

### Voice Input

Send voice notes on Telegram. The bot transcribes via OpenAI Whisper and processes as text. Supports: ogg, mp3, wav, m4a, webm.

### Webhooks

Register URLs to receive real-time notifications:

```bash
curl -X POST localhost:8765/api/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-server.com/hook", "events": ["hold_created", "goal_abandoned"]}'
```

Available events: `hold_created`, `hold_approved`, `hold_rejected`, `impulse_fired`, `goal_registered`, `goal_abandoned`, `memory_added`, `entity_added`, `value_violated`, `anomaly_detected`.

### Import/Export

- **Export**: Download a full JSON backup of your agent's config, entities, goals, memories, and values
- **Import**: Restore from backup (replace or merge mode), or share configs between machines
- Sensitive data (API keys, tokens) is excluded from exports

### GDPR Compliance

- **Export All Data** — One-click ZIP download with JSON + CSV files + README
- **Export Entity Data** — Download all data for a specific person
- **Right to Erasure** — Delete all data related to an entity across all tables

### Encryption at Rest

Enable `encrypt_data_at_rest` in config. Uses AES-256-GCM for conversation content and memory content. API keys in config files are encrypted with `ENC::` prefix.

```bash
humane encrypt-config   # Encrypt sensitive fields in config YAML
humane rotate-key       # Generate new encryption key, re-encrypt everything
```

### API Security

- **API Keys**: Generate `hm_` prefixed keys with SHA-256 hashing
- **Rate Limiting**: Sliding window, configurable requests per minute
- **Auth Middleware**: `Authorization: Bearer hm_xxxxx` on all `/api/*` routes

### API Documentation

Interactive Swagger UI at `http://localhost:8765/api/docs` — 70+ endpoints across 31 tags.

### Python SDK

```python
from humane.sdk import HumaneClient

client = HumaneClient("http://localhost:8765")
client.add_entity("Arjun", "prospect")
client.add_goal("Close deal", expected_value=0.8, milestones=5)
result = client.evaluate("send_email", confidence=0.7)
print(result["verdict"])  # "proceed" or "hold"
```

Async version also available:

```python
from humane.sdk.async_client import AsyncHumaneClient

async with AsyncHumaneClient("http://localhost:8765") as client:
    state = await client.get_state()
```

### Multi-Model LLM Support

Configure any of these providers in Settings:

| Provider | Models |
|----------|--------|
| Anthropic | claude-sonnet-4-20250514, claude-opus-4-20250514 |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| Google Gemini | gemini-2.0-flash, gemini-1.5-pro |
| Groq | llama-3.3-70b, mixtral-8x7b |
| Ollama (local) | Any model running locally |
| DeepSeek | deepseek-chat |
| Custom | Any OpenAI-compatible API |

Automatic fallback: if the primary provider fails, the system tries the next configured provider.

### Mobile App

React Native (Expo) app in the `mobile/` directory. WebView wrapper with bottom tab navigation (Dashboard, Queue, Chat, Settings), pull-to-refresh, and native settings screen.

---

## Quick Reference

| I want to... | Go to... |
|-------------|----------|
| See why the agent held an action | Dashboard → check DQM and state bars |
| Approve/reject a held action | Dashboard → Hold Queue section |
| Track a new contact | Entities → + Add Entity |
| Set a business objective | Goals → + Add Goal (or Use Template) |
| Store important information | Memories → + Add Memory (pin if critical) |
| Set an ethical boundary | Values → + Add Value |
| Make the agent less cautious | Settings → lower Confidence Threshold |
| Make the agent more proactive | Settings → raise Impulse Rate |
| Stop late-night messages | Settings → set Active Hours |
| See relationship network | Entities → Graph View toggle |
| Check what the agent would do | Dashboard → Evaluate Action |
| Get a morning summary | Automatic (Daily Digest via Telegram) |
| Back up my agent | Import/Export → Export |
| Delete someone's data | Settings → GDPR → Right to Erasure |
| Test two personalities | A/B Tests → Create Test |
| Simulate a conversation | Simulate tab → enter message |
| Connect external tools | Webhooks → register URL |
| Use from code | `pip install humane-sdk` or REST API |
| Run in Docker | `docker-compose up -d` |

---

## The 10 Engines

Every action the agent takes passes through these 10 engines:

1. **Human State** — Tracks energy, mood, fatigue, boredom, focus, social load
2. **Stochastic Impulse** — Fires proactive actions at random intervals
3. **Inaction Guard** — Checks confidence threshold, defers when fatigued
4. **Relational Memory** — Tracks trust, sentiment, grudges per entity
5. **Dissent Engine** — Agent challenges its own decisions
6. **Goal Abandonment** — Computes ROI, proposes dropping stalled goals
7. **Memory Decay** — Manages knowledge with natural forgetting
8. **Social Risk** — Predicts reputation damage before sending messages
9. **Anomaly Detector** — Notices unusual patterns in contacts' behavior
10. **Values Boundary** — Enforces hard/soft moral boundaries

---

## CLI Commands

```bash
humane init                    # Setup wizard
humane serve                   # Start bot + API + dashboard
humane demo                    # Run a 6-hour simulation
humane status                  # Show current agent state
humane export [--output file]  # Export agent data
humane import <file> [--mode]  # Import agent data
humane encrypt-config          # Encrypt sensitive config fields
humane rotate-key              # Rotate encryption key
humane agents list             # List all agents
humane agents create <name>    # Create a new agent
humane agents delete <name>    # Delete an agent
```

---

## License

MIT
