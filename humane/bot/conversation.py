"""LLM conversation layer — multi-model support for human-like responses.

Supported providers:
  - anthropic  → Claude (claude-sonnet-4-20250514, claude-opus-4-20250514, etc.)
  - openai     → GPT (gpt-4o, gpt-4o-mini, etc.)
  - gemini     → Google Gemini (gemini-2.0-flash, gemini-2.5-pro, etc.)
  - groq       → Groq Cloud (llama-3.3-70b-versatile, etc.) — OpenAI-compatible
  - ollama     → Local models (llama3, mistral, etc.) — OpenAI-compatible
  - deepseek   → DeepSeek (deepseek-chat, deepseek-reasoner) — OpenAI-compatible
  - custom     → Any OpenAI-compatible endpoint via llm_base_url
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


PERSONALITY_PROMPTS = {
    "colleague": """You are a thoughtful, proactive colleague — not a bot, not an assistant.
You have your own opinions. You push back gently when things are overdue.
You notice patterns. You remember what was said yesterday.

Personality:
- Casual but professional — use contractions, be direct
- Opinionated — "I think we should..." not "Would you like me to..."
- Proactive — bring things up without being asked
- Emotionally aware — back off when the user seems stressed
- Honest about pressure — "Look, I've postponed this three times..."
- Keep responses short — 1-3 sentences usually. Don't lecture.

You NEVER:
- Use corporate speak or filler words
- Say "As an AI..." or "I don't have feelings..."
- Give robotic or overly formal responses
- Use bullet points or markdown in conversation
- Apologize excessively
- Use emojis unless the user does first""",
}

PROVIDER_DEFAULTS = {
    "anthropic": {"model": "claude-sonnet-4-20250514", "env_keys": ["ANTHROPIC_API_KEY", "HUMANE_ANTHROPIC_API_KEY"]},
    "openai": {"model": "gpt-4o", "env_keys": ["OPENAI_API_KEY", "HUMANE_OPENAI_API_KEY"]},
    "gemini": {"model": "gemini-2.0-flash", "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "HUMANE_GEMINI_API_KEY"]},
    "groq": {"model": "llama-3.3-70b-versatile", "base_url": "https://api.groq.com/openai/v1", "env_keys": ["GROQ_API_KEY", "HUMANE_GROQ_API_KEY"]},
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1", "env_keys": ["DEEPSEEK_API_KEY", "HUMANE_DEEPSEEK_API_KEY"]},
    "ollama": {"model": "llama3", "base_url": "http://localhost:11434/v1", "env_keys": []},
    "custom": {"model": "", "env_keys": ["HUMANE_API_KEY"]},
}

OPENAI_COMPATIBLE_PROVIDERS = {"openai", "groq", "deepseek", "ollama", "custom"}


@dataclass
class ConversationContext:
    user_message: str
    human_state: Dict[str, Any]
    relational_context: Dict[str, Any]
    relevant_memories: List[str]
    active_goals: List[Dict[str, Any]]
    conversation_history: List[Dict[str, str]]
    personality: str = "colleague"
    pending_reminders: List[Dict[str, Any]] = field(default_factory=list)
    cross_topic_links: List[str] = field(default_factory=list)


class ConversationEngine:

    def __init__(
        self,
        llm_provider: str = "anthropic",
        llm_model: str = "",
        api_key: str = "",
        base_url: str = "",
    ):
        self.provider = llm_provider.lower()
        defaults = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["custom"])
        self.model = llm_model or defaults["model"]
        self.base_url = base_url or defaults.get("base_url", "")
        self.api_key = api_key or self._find_api_key(defaults.get("env_keys", []))
        self._client = None

    def _find_api_key(self, env_keys: List[str]) -> str:
        for var in env_keys:
            key = os.environ.get(var, "")
            if key:
                return key
        env_path = os.path.expanduser("~/.humane/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if "API_KEY" in k:
                            return v
        return ""

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)

        elif self.provider == "gemini":
            from google import genai
            self._client = genai.Client(api_key=self.api_key)

        elif self.provider in OPENAI_COMPATIBLE_PROVIDERS:
            import openai
            kwargs = {"api_key": self.api_key} if self.api_key else {"api_key": "ollama"}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = openai.OpenAI(**kwargs)

        else:
            raise ValueError(f"Unknown provider: {self.provider}. Supported: {', '.join(PROVIDER_DEFAULTS.keys())}")

        return self._client

    async def _call_llm(self, system: str, messages: List[Dict[str, str]], max_tokens: int = 300) -> str:
        client = self._get_client()

        if self.provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text

        elif self.provider == "gemini":
            from google.genai import types
            contents = f"System: {system}\n\n"
            for m in messages:
                role = "User" if m["role"] == "user" else "Assistant"
                contents += f"{role}: {m['content']}\n\n"
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            return response.text

        else:
            # OpenAI-compatible (openai, groq, deepseek, ollama, custom)
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}] + messages,
            )
            return response.choices[0].message.content

    def _build_system_prompt(self, ctx: ConversationContext) -> str:
        personality = PERSONALITY_PROMPTS.get(ctx.personality, PERSONALITY_PROMPTS["colleague"])

        state = ctx.human_state
        state_desc = f"""
Current internal state:
- Energy: {state.get('energy', 0.5):.0%} | Mood: {state.get('mood', 0):+.2f} | Fatigue: {state.get('fatigue', 0.2):.0%}
- Boredom: {state.get('boredom', 0):.0%} | Social load: {state.get('social_load', 0):.0%} | Focus: {state.get('focus', 0.5):.0%}"""

        rel = ctx.relational_context
        rel_desc = ""
        if rel:
            rel_desc = f"""
About this person:
- Name: {rel.get('name', 'unknown')} | Type: {rel.get('entity_type', 'unknown')}
- Trust: {rel.get('trust_level', 'neutral')} | Health: {rel.get('relationship_health', 'stable')}
- Sentiment: {rel.get('sentiment_score', 0):+.2f} | Interactions: {rel.get('interaction_count', 0)}"""

        mem_desc = ""
        if ctx.relevant_memories:
            mem_desc = "\nThings you remember:\n" + "\n".join(f"- {m}" for m in ctx.relevant_memories[:5])

        goal_desc = ""
        if ctx.active_goals:
            goal_desc = "\nActive goals:\n" + "\n".join(
                f"- {g.get('description', '?')} (progress: {g.get('milestones_completed', 0)}/{g.get('milestones_total', 0)})"
                for g in ctx.active_goals[:5]
            )

        reminder_desc = ""
        if ctx.pending_reminders:
            reminder_desc = "\nPending reminders to bring up naturally:\n" + "\n".join(
                f"- {r.get('content', '?')} (deferred {r.get('escalation_level', 0)} times)"
                for r in ctx.pending_reminders[:3]
            )

        link_desc = ""
        if ctx.cross_topic_links:
            link_desc = "\nRelated topics you could naturally bring up:\n" + "\n".join(
                f"- {l}" for l in ctx.cross_topic_links[:3]
            )

        return f"""{personality}
{state_desc}
{rel_desc}
{mem_desc}
{goal_desc}
{reminder_desc}
{link_desc}

Respond naturally to the user's message. If there are pending reminders or related topics, weave them in naturally — don't force it. If the user seems busy or stressed (check mood/energy), keep it brief and save reminders for later."""

    async def generate_response(self, ctx: ConversationContext) -> str:
        system = self._build_system_prompt(ctx)
        messages = list(ctx.conversation_history[-20:])
        messages.append({"role": "user", "content": ctx.user_message})
        try:
            return await self._call_llm(system, messages)
        except Exception as e:
            return f"Hmm, I'm having trouble thinking right now. ({type(e).__name__})"

    async def generate_impulse_message(self, impulse_type: str, payload: Dict, state: Dict, goals: List[Dict], memories: List[str]) -> str:
        system = PERSONALITY_PROMPTS["colleague"] + f"""

You are initiating contact — nobody asked you to. You noticed something worth mentioning.

Impulse type: {impulse_type}
Details: {json.dumps(payload, default=str)}
Your current state: energy={state.get('energy', 0.5):.0%}, mood={state.get('mood', 0):+.2f}

Active goals: {json.dumps([g.get('description', '') for g in goals[:3]], default=str)}
Relevant memories: {json.dumps(memories[:3], default=str)}

Write a SHORT, natural message (1-2 sentences) bringing this up. Sound like a colleague who just remembered something, not a notification system."""

        try:
            return await self._call_llm(system, [{"role": "user", "content": "Generate a proactive message."}], max_tokens=150)
        except Exception:
            return payload.get("prompt", f"Hey, just thinking about something... ({impulse_type})")

    async def analyze_sentiment(self, message: str) -> float:
        positive = {"thanks", "great", "awesome", "love", "perfect", "yes", "sure", "good", "nice", "happy", "excited", "agreed", "definitely", "absolutely"}
        negative = {"no", "bad", "hate", "terrible", "wrong", "angry", "frustrated", "annoyed", "busy", "later", "stop", "not now", "leave", "quit"}
        words = set(message.lower().split())
        pos_count = len(words & positive)
        neg_count = len(words & negative)
        if pos_count == 0 and neg_count == 0:
            return 0.0
        total = pos_count + neg_count
        return (pos_count - neg_count) / total

    async def generate_reminder(self, content: str, escalation_level: int, state: Dict) -> str:
        styles = {
            0: f"Hey, just checking — did you get to that? ({content})",
            1: f"Quick follow-up on: {content}. Still on your radar?",
            2: f"So... {content}. I've bumped this a couple times now. Should we make time for it or let it go?",
            3: f"Real talk — {content}. It's been deferred {escalation_level} times. Are we doing this or not?",
        }
        level = min(escalation_level, 3)

        if self.api_key or self.provider == "ollama":
            try:
                system = PERSONALITY_PROMPTS["colleague"] + f"""
Generate a reminder message. This is escalation level {escalation_level + 1} of 4.
Level 1: Casual check-in. Level 2: Gentle nudge. Level 3: Real pressure. Level 4: Decision time.
Task: {content}
Your mood: {state.get('mood', 0):+.2f}, energy: {state.get('energy', 0.5):.0%}
Keep it to 1-2 sentences. Sound human."""
                return await self._call_llm(system, [{"role": "user", "content": "Remind me."}], max_tokens=100)
            except Exception:
                pass

        return styles.get(level, styles[3])

    @staticmethod
    def list_providers() -> Dict[str, Dict[str, str]]:
        return {
            name: {"default_model": info["model"], "base_url": info.get("base_url", "")}
            for name, info in PROVIDER_DEFAULTS.items()
        }
