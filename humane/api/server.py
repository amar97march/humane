"""Humane API Server — REST API + Web Dashboard on a single port."""

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from aiohttp import web

from humane.conductor import Conductor
from humane.core.config import HumaneConfig
from humane.core.models import (
    EntityType, ImpulseType, MemoryType, ProposedAction, ValueSeverity, Verdict,
)
from humane.bot.voice import VoiceProcessor
from humane.digest import DailyDigest
from humane.gdpr import GDPRExporter
from humane.openapi import generate_openapi_spec
from humane.webhooks import WebhookManager, VALID_EVENT_TYPES
from humane.multi import AgentRegistry
from humane.smart_schedule import SmartScheduler
from humane.insights import PredictiveInsights
from humane.retention import RetentionManager
from humane.auth import APIKeyManager, RateLimiter
from humane.goal_templates import list_templates, instantiate_template
from humane.ab_testing import ABTestManager
from humane.feedback_loop import FeedbackCollector, ThresholdOptimizer
from humane.agent_comms import AgentCommunicator, VALID_MESSAGE_TYPES
from humane.branching import ConversationBranch

logger = logging.getLogger("humane.api")


class APIServer:
    def __init__(
        self,
        conductor: Conductor,
        config: HumaneConfig,
        registry: Optional[AgentRegistry] = None,
    ):
        self.conductor = conductor
        self.config = config
        self.registry = registry
        self.app = web.Application()

        # Auth & rate limiting
        self.key_manager = APIKeyManager(conductor.store)
        self.rate_limiter = RateLimiter(
            max_requests=config.api_rate_limit,
            window_seconds=config.api_rate_window,
        )

        # Wire up webhook manager and attach to event log
        self.webhook_manager = WebhookManager(
            store=conductor.store,
            event_log=conductor.event_log,
        )
        conductor.event_log.set_webhook_manager(self.webhook_manager)

        # A/B testing manager
        self.ab_manager = ABTestManager(conductor.store)

        # Agent-to-agent communication
        self.agent_comms: Optional[AgentCommunicator] = None
        if registry:
            self.agent_comms = AgentCommunicator(registry, conductor.store)

        self._whatsapp_bot = None  # Set via set_whatsapp_bot() if configured
        self.voice = VoiceProcessor(config)
        self._setup_routes()

    # ------------------------------------------------------------------
    # Helpers for multi-agent resolution
    # ------------------------------------------------------------------
    def _resolve_conductor(self, request: web.Request) -> Conductor:
        """Return the Conductor for the requested agent_id query param, or the default."""
        agent_id = request.query.get("agent_id")
        if agent_id and self.registry:
            return self.registry.get_conductor(agent_id)
        return self.conductor

    def _resolve_config(self, request: web.Request) -> HumaneConfig:
        agent_id = request.query.get("agent_id")
        if agent_id and self.registry:
            return self.registry.get_config(agent_id)
        return self.config

    def _setup_routes(self):
        # Web dashboard
        self.app.router.add_get("/", self._serve_dashboard)

        # ----- Multi-agent management -----
        self.app.router.add_get("/api/agents", self._list_agents)
        self.app.router.add_post("/api/agents", self._create_agent)
        self.app.router.add_get("/api/agents/{id}/state", self._get_agent_state)
        self.app.router.add_delete("/api/agents/{id}", self._delete_agent)

        # ----- Agent communication -----
        self.app.router.add_get("/api/agents/{id}/inbox", self._agent_inbox)
        self.app.router.add_post("/api/agents/{id}/send", self._agent_send)
        self.app.router.add_post("/api/agents/broadcast", self._agent_broadcast)
        self.app.router.add_post("/api/agents/{id}/share-entity", self._agent_share_entity)
        self.app.router.add_post("/api/agents/{id}/share-goal", self._agent_share_goal)

        # State
        self.app.router.add_get("/api/state", self._get_state)

        # Hold queue
        self.app.router.add_get("/api/queue", self._get_queue)
        self.app.router.add_post("/api/queue/{id}/approve", self._approve_hold)
        self.app.router.add_post("/api/queue/{id}/reject", self._reject_hold)

        # Entities
        self.app.router.add_get("/api/entities", self._list_entities)
        self.app.router.add_post("/api/entities", self._add_entity)
        self.app.router.add_get("/api/entities/{id}", self._get_entity)
        self.app.router.add_post("/api/entities/{id}/interact", self._log_interaction)
        self.app.router.add_get("/api/entities/{id}/timeline", self._get_entity_timeline)

        # Goals
        self.app.router.add_get("/api/goals", self._list_goals)
        self.app.router.add_post("/api/goals", self._add_goal)
        self.app.router.add_patch("/api/goals/{id}", self._update_goal)

        # Goal Templates
        self.app.router.add_get("/api/goal-templates", self._list_goal_templates)
        self.app.router.add_post("/api/goal-templates/instantiate", self._instantiate_goal_template)

        # Memories
        self.app.router.add_get("/api/memories", self._list_memories)
        self.app.router.add_post("/api/memories", self._add_memory)

        # Events
        self.app.router.add_get("/api/events", self._list_events)

        # Evaluate
        self.app.router.add_post("/api/evaluate", self._evaluate_action)

        # Impulse
        self.app.router.add_post("/api/impulse/fire", self._fire_impulse)

        # Config
        self.app.router.add_get("/api/config", self._get_config)
        self.app.router.add_patch("/api/config", self._update_config)

        # Values
        self.app.router.add_get("/api/values", self._list_values)
        self.app.router.add_post("/api/values", self._add_value)

        # Webhooks
        self.app.router.add_get("/api/webhooks", self._list_webhooks)
        self.app.router.add_post("/api/webhooks", self._register_webhook)
        self.app.router.add_delete("/api/webhooks/{id}", self._unregister_webhook)
        self.app.router.add_post("/api/webhooks/test", self._test_webhook)

        # Import / Export
        self.app.router.add_get("/api/export", self._export_bundle)
        self.app.router.add_get("/api/export/download", self._export_download)
        self.app.router.add_post("/api/import", self._import_bundle)

        # Conversations
        self.app.router.add_get("/api/conversations", self._list_conversations)
        self.app.router.add_get("/api/conversations/stats", self._conversation_stats)
        self.app.router.add_get("/api/conversations/categories", self._conversation_categories)
        self.app.router.add_delete("/api/conversations", self._clear_conversations)

        # Models / Providers
        self.app.router.add_get("/api/models", self._list_models)

        # Analytics
        self.app.router.add_get("/api/analytics/state-history", self._analytics_state_history)
        self.app.router.add_get("/api/analytics/engine-stats", self._analytics_engine_stats)
        self.app.router.add_get("/api/analytics/entity-interactions", self._analytics_entity_interactions)
        self.app.router.add_get("/api/analytics/approval-rate", self._analytics_approval_rate)
        self.app.router.add_get("/api/analytics/impulse-stats", self._analytics_impulse_stats)

        # WhatsApp webhook (handlers delegated to WhatsAppBot if configured)
        self.app.router.add_get("/webhook/whatsapp", self._whatsapp_verify)
        self.app.router.add_post("/webhook/whatsapp", self._whatsapp_incoming)

        # Plugins
        self.app.router.add_get("/api/plugins", self._list_plugins)
        self.app.router.add_post("/api/plugins/reload", self._reload_plugins)
        self.app.router.add_post("/api/plugins/{name}/toggle", self._toggle_plugin)

        # Voice
        self.app.router.add_post("/api/voice/transcribe", self._voice_transcribe)

        # Digest
        self.app.router.add_get("/api/digest", self._get_digest)
        self.app.router.add_get("/api/digest/preview", self._get_digest_preview)

        # Smart Schedule
        self.app.router.add_get("/api/schedule", self._get_schedule_all)
        self.app.router.add_get("/api/schedule/{entity_id}", self._get_schedule_entity)

        # Insights
        self.app.router.add_get("/api/insights", self._get_insights)

        # A/B Testing
        self.app.router.add_get("/api/ab-tests", self._list_ab_tests)
        self.app.router.add_post("/api/ab-tests", self._create_ab_test)
        self.app.router.add_get("/api/ab-tests/{id}/results", self._get_ab_test_results)
        self.app.router.add_post("/api/ab-tests/{id}/end", self._end_ab_test)

        # Audit
        self.app.router.add_get("/api/audit", self._get_audit)

        # Auth / API Keys
        self.app.router.add_post("/api/auth/keys", self._generate_api_key)
        self.app.router.add_get("/api/auth/keys", self._list_api_keys)
        self.app.router.add_delete("/api/auth/keys/{id}", self._revoke_api_key)

        # Data Retention
        self.app.router.add_get("/api/retention", self._get_retention)
        self.app.router.add_post("/api/retention/preview", self._retention_preview)
        self.app.router.add_post("/api/retention/apply", self._retention_apply)

        # GDPR
        self.app.router.add_get("/api/gdpr/export", self._gdpr_export)
        self.app.router.add_get("/api/gdpr/export/download", self._gdpr_export_download)
        self.app.router.add_get("/api/gdpr/export/{entity_id}", self._gdpr_export_entity)
        self.app.router.add_delete("/api/gdpr/erase/{entity_id}", self._gdpr_erase)

        # API Documentation
        self.app.router.add_get("/api/docs", self._serve_api_docs)
        self.app.router.add_get("/api/openapi.json", self._serve_openapi_spec)

        # Feedback & Tuning
        self.app.router.add_get("/api/feedback/stats", self._feedback_stats)
        self.app.router.add_get("/api/feedback/export", self._feedback_export)
        self.app.router.add_get("/api/feedback/recommendations", self._feedback_recommendations)
        self.app.router.add_post("/api/feedback/auto-tune", self._feedback_auto_tune)


        # Simulation / Branching
        self.app.router.add_post("/api/simulate", self._simulate_message)
        self.app.router.add_post("/api/simulate/compare", self._simulate_compare)
        # CORS middleware
        self.app.middlewares.append(self._cors_middleware)
        self.app.middlewares.append(self._auth_middleware)

    @web.middleware
    async def _cors_middleware(self, request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as ex:
                response = ex
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @web.middleware
    async def _auth_middleware(self, request, handler):
        """Enforce API key auth and rate limiting on /api/* routes."""
        path = request.path

        # Skip non-API routes, OPTIONS, dashboard, and docs
        if (
            not path.startswith("/api/")
            or request.method == "OPTIONS"
            or path == "/api/docs"
        ):
            response = await handler(request)
            return response

        # --- Rate limiting (always applied, keyed by client IP or API key) ---
        api_key = self._extract_api_key(request)
        client_id = api_key or request.remote or "unknown"
        allowed, remaining, reset_at = self.rate_limiter.check(client_id)
        rl_headers = self.rate_limiter.headers(allowed, remaining, reset_at)

        if not allowed:
            resp = self._json_response(
                {"error": "Rate limit exceeded", "retry_after": int(reset_at - time.time())},
                status=429,
            )
            resp.headers.update(rl_headers)
            return resp

        # --- Auth check (only when enabled) ---
        if self.config.api_auth_enabled:
            # Allow auth key management endpoints without auth so the
            # dashboard can bootstrap the first key
            if not path.startswith("/api/auth/"):
                if not api_key or not self.key_manager.validate_key(api_key):
                    resp = self._json_response(
                        {"error": "Invalid or missing API key"},
                        status=401,
                    )
                    resp.headers.update(rl_headers)
                    return resp

        response = await handler(request)
        response.headers.update(rl_headers)
        return response

    @staticmethod
    def _extract_api_key(request: web.Request) -> Optional[str]:
        """Extract API key from Authorization header or query param."""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return request.query.get("api_key") or None

    def _json_response(self, data, status=200):
        return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, default=str))

    # ------------------------------------------------------------------
    # Auth / API Key endpoints
    # ------------------------------------------------------------------
    async def _generate_api_key(self, request):
        full_key = self.key_manager.generate_key()
        return self._json_response({"key": full_key}, status=201)

    async def _list_api_keys(self, request):
        keys = self.key_manager.list_keys()
        return self._json_response({"keys": keys})

    async def _revoke_api_key(self, request):
        key_id = request.match_info["id"]
        self.key_manager.revoke_key(key_id)
        return self._json_response({"ok": True, "id": key_id})

    # ------------------------------------------------------------------
    # Multi-agent endpoints
    # ------------------------------------------------------------------
    async def _list_agents(self, request):
        if not self.registry:
            return self._json_response({"agents": [], "multi_agent": False})
        agents = self.registry.list_agents()
        return self._json_response({"agents": agents, "multi_agent": True})

    async def _create_agent(self, request):
        if not self.registry:
            return self._json_response(
                {"error": "Multi-agent mode not enabled"}, status=400
            )
        data = await request.json()
        name = data.get("name", "").strip()
        if not name:
            return self._json_response({"error": "name is required"}, status=400)

        overrides: dict = {}
        if "personality" in data:
            overrides["bot_personality"] = data["personality"]
        if "llm_provider" in data:
            overrides["llm_provider"] = data["llm_provider"]

        try:
            agent_id = self.registry.create_agent(name, config_overrides=overrides)
        except ValueError as e:
            return self._json_response({"error": str(e)}, status=409)

        return self._json_response({"id": agent_id, "name": name}, status=201)

    async def _get_agent_state(self, request):
        if not self.registry:
            return self._json_response(
                {"error": "Multi-agent mode not enabled"}, status=400
            )
        agent_id = request.match_info["id"]
        try:
            agent = self.registry.get_agent(agent_id)
        except KeyError:
            return self._json_response({"error": "Agent not found"}, status=404)

        cond: Conductor = agent["conductor"]
        cond.human_state.tick()
        state = cond.get_state_snapshot()
        return self._json_response({
            "id": agent["id"],
            "name": agent["name"],
            "state": state,
            "dqm": cond.human_state.decision_quality_multiplier,
            "preferred_task_type": cond.human_state.preferred_task_type.value,
        })

    async def _delete_agent(self, request):
        if not self.registry:
            return self._json_response(
                {"error": "Multi-agent mode not enabled"}, status=400
            )
        agent_id = request.match_info["id"]
        try:
            self.registry.delete_agent(agent_id)
        except KeyError:
            return self._json_response({"error": "Agent not found"}, status=404)
        return self._json_response({"ok": True, "deleted": agent_id})

    # ------------------------------------------------------------------
    # Agent communication endpoints
    # ------------------------------------------------------------------
    async def _agent_inbox(self, request):
        """GET /api/agents/{id}/inbox"""
        if not self.agent_comms:
            return self._json_response({"error": "Multi-agent mode not enabled"}, status=400)
        agent_id = request.match_info["id"]
        # Optional: mark a message as read via query param
        mark_read = request.query.get("mark_read")
        if mark_read:
            self.agent_comms.mark_read(mark_read)
            return self._json_response({"ok": True})
        unread_only = request.query.get("unread_only", "true").lower() in ("true", "1", "yes")
        try:
            messages = self.agent_comms.get_inbox(agent_id, unread_only=unread_only)
        except KeyError:
            return self._json_response({"error": "Agent not found"}, status=404)
        return self._json_response({"messages": [m.to_dict() for m in messages]})

    async def _agent_send(self, request):
        """POST /api/agents/{id}/send"""
        if not self.agent_comms:
            return self._json_response({"error": "Multi-agent mode not enabled"}, status=400)
        from_id = request.match_info["id"]
        data = await request.json()
        to_id = data.get("to_agent_id", "").strip()
        msg_type = data.get("type", "").strip()
        content = data.get("content", "").strip()
        if not to_id or not msg_type or not content:
            return self._json_response(
                {"error": "to_agent_id, type, and content are required"}, status=400
            )
        try:
            msg_id = self.agent_comms.send(from_id, to_id, msg_type, content, data.get("metadata"))
        except ValueError as e:
            return self._json_response({"error": str(e)}, status=400)
        except KeyError as e:
            return self._json_response({"error": str(e)}, status=404)
        return self._json_response({"ok": True, "message_id": msg_id}, status=201)

    async def _agent_broadcast(self, request):
        """POST /api/agents/broadcast"""
        if not self.agent_comms:
            return self._json_response({"error": "Multi-agent mode not enabled"}, status=400)
        data = await request.json()
        from_id = data.get("from_agent_id", "").strip()
        msg_type = data.get("type", "").strip()
        content = data.get("content", "").strip()
        if not from_id or not msg_type or not content:
            return self._json_response(
                {"error": "from_agent_id, type, and content are required"}, status=400
            )
        try:
            ids = self.agent_comms.broadcast(from_id, msg_type, content, data.get("metadata"))
        except (ValueError, KeyError) as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True, "message_ids": ids}, status=201)

    async def _agent_share_entity(self, request):
        """POST /api/agents/{id}/share-entity"""
        if not self.agent_comms:
            return self._json_response({"error": "Multi-agent mode not enabled"}, status=400)
        from_id = request.match_info["id"]
        data = await request.json()
        to_id = data.get("to_agent_id", "").strip()
        entity_id = data.get("entity_id", "").strip()
        if not to_id or not entity_id:
            return self._json_response(
                {"error": "to_agent_id and entity_id are required"}, status=400
            )
        try:
            self.agent_comms.share_entity(from_id, to_id, entity_id)
        except KeyError as e:
            return self._json_response({"error": str(e)}, status=404)
        return self._json_response({"ok": True})

    async def _agent_share_goal(self, request):
        """POST /api/agents/{id}/share-goal"""
        if not self.agent_comms:
            return self._json_response({"error": "Multi-agent mode not enabled"}, status=400)
        from_id = request.match_info["id"]
        data = await request.json()
        to_id = data.get("to_agent_id", "").strip()
        goal_id = data.get("goal_id", "").strip()
        if not to_id or not goal_id:
            return self._json_response(
                {"error": "to_agent_id and goal_id are required"}, status=400
            )
        try:
            self.agent_comms.share_goal(from_id, to_id, goal_id)
        except KeyError as e:
            return self._json_response({"error": str(e)}, status=404)
        return self._json_response({"ok": True})

    # --- Dashboard ---
    async def _serve_dashboard(self, request):
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="Dashboard not found", status=404)

    # --- State ---
    async def _get_state(self, request):
        conductor = self._resolve_conductor(request)
        config = self._resolve_config(request)
        conductor.human_state.tick()
        state = conductor.get_state_snapshot()
        return self._json_response({
            "state": state,
            "dqm": conductor.human_state.decision_quality_multiplier,
            "preferred_task_type": conductor.human_state.preferred_task_type.value,
            "agent_name": config.agent_name,
        })

    # --- Hold Queue ---
    async def _get_queue(self, request):
        conductor = self._resolve_conductor(request)
        queue = conductor.get_hold_queue()
        return self._json_response({
            "items": [{
                "id": h.id,
                "action_type": h.action.action_type,
                "payload": h.action.payload,
                "confidence": h.action.confidence,
                "adjusted_confidence": h.adjusted_confidence,
                "hold_reason": h.hold_reason,
                "hold_source": h.hold_source,
                "created_at": h.created_at,
            } for h in queue],
            "count": len(queue),
        })

    async def _approve_hold(self, request):
        conductor = self._resolve_conductor(request)
        hold_id = request.match_info["id"]
        try:
            conductor.approve_hold(hold_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True, "action": "approved", "id": hold_id})

    async def _reject_hold(self, request):
        conductor = self._resolve_conductor(request)
        hold_id = request.match_info["id"]
        try:
            conductor.reject_hold(hold_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True, "action": "rejected", "id": hold_id})

    # --- Entities ---
    async def _list_entities(self, request):
        conductor = self._resolve_conductor(request)
        entities = conductor.relational.list_entities()
        return self._json_response({
            "entities": [{
                "entity_id": e.entity_id,
                "name": e.name,
                "entity_type": e.entity_type.value,
                "sentiment_score": round(e.sentiment_score, 3),
                "grudge_score": round(e.grudge_score, 3),
                "trust_level": e.trust_level.value,
                "relationship_health": e.relationship_health.value,
                "disclosure_threshold": e.disclosure_threshold,
                "interaction_count": e.interaction_count,
                "last_interaction_at": e.last_interaction_at,
            } for e in entities],
        })

    async def _add_entity(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        name = data.get("name", "")
        if not name.strip():
            return self._json_response({"error": "name is required"}, status=400)
        entity_type_str = data.get("entity_type", "unknown")
        try:
            entity_type = EntityType(entity_type_str)
        except ValueError:
            entity_type = EntityType.UNKNOWN
        entity = conductor.relational.add_entity(name, entity_type)
        return self._json_response({"entity_id": entity.entity_id, "name": entity.name}, status=201)

    async def _get_entity(self, request):
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["id"]
        ctx = conductor.relational.get_context(entity_id)
        if not ctx:
            return self._json_response({"error": "Entity not found"}, status=404)
        return self._json_response(ctx)

    async def _log_interaction(self, request):
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["id"]
        data = await request.json()
        sentiment = float(data.get("sentiment", 0.0))
        summary = data.get("summary", "")
        conductor.relational.log_interaction(entity_id, sentiment, summary)
        return self._json_response({"ok": True})

    async def _get_entity_timeline(self, request):
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["id"]
        limit = int(request.query.get("limit", "100"))
        entity = conductor.store.get_entity(entity_id)
        if not entity:
            return self._json_response({"error": "Entity not found"}, status=404)

        timeline = conductor.store.get_entity_timeline(entity_id, limit=limit)

        # Compute stats from interactions in the timeline
        interactions = [e for e in timeline if e["type"] == "interaction"]
        total_interactions = len(interactions)
        sentiments = [e["sentiment"] for e in interactions if e.get("sentiment") is not None]
        avg_sentiment = round(sum(sentiments) / len(sentiments), 4) if sentiments else 0.0
        first_interaction = interactions[0]["timestamp"] if interactions else None
        last_interaction = interactions[-1]["timestamp"] if interactions else None

        # Build trust evolution from interactions (track trust_level at each interaction timestamp)
        trust_evolution = []
        conn = conductor.store.conn
        trust_rows = conn.execute(
            """SELECT created_at, data_json FROM events
               WHERE engine = 'relational' AND data_json LIKE ?
               ORDER BY created_at ASC""",
            (f"%{entity_id}%",),
        ).fetchall()
        for row in trust_rows:
            data = json.loads(row["data_json"])
            if "trust_level" in data:
                trust_evolution.append({
                    "timestamp": row["created_at"],
                    "trust_level": data["trust_level"],
                })
        # If no trust events found, use the current entity trust level
        if not trust_evolution:
            trust_evolution.append({
                "timestamp": entity.last_interaction_at or entity.created_at,
                "trust_level": entity.trust_level.value,
            })

        return self._json_response({
            "entity_id": entity.entity_id,
            "entity_name": entity.name,
            "timeline": timeline,
            "stats": {
                "total_interactions": total_interactions,
                "avg_sentiment": avg_sentiment,
                "trust_evolution": trust_evolution,
                "first_interaction": first_interaction,
                "last_interaction": last_interaction,
            },
        })

    # --- Goals ---
    async def _list_goals(self, request):
        conductor = self._resolve_conductor(request)
        status_filter = request.query.get("status")
        if status_filter == "active":
            goals = conductor.goal_engine.active_goals()
        else:
            # Get all goals from the engine (in-memory)
            all_goals = list(conductor.goal_engine._goals.values())
            if status_filter:
                goals = [g for g in all_goals if g.status == status_filter]
            else:
                goals = all_goals
        return self._json_response({
            "goals": [{
                "id": g.id,
                "description": g.description,
                "expected_value": g.expected_value,
                "remaining_effort": g.remaining_effort,
                "progress_velocity": g.progress_velocity,
                "milestones_total": g.milestones_total,
                "milestones_completed": g.milestones_completed,
                "roi": conductor.goal_engine.compute_roi(g),
                "status": g.status,
                "created_at": g.created_at,
            } for g in goals],
        })

    async def _add_goal(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        description = data.get("description", "")
        if not description.strip():
            return self._json_response({"error": "description is required"}, status=400)
        goal = conductor.goal_engine.register_goal(
            description=description,
            expected_value=float(data.get("expected_value", 1.0)),
            milestones_total=int(data.get("milestones_total", 0)),
        )
        return self._json_response({"id": goal.id, "description": goal.description}, status=201)

    async def _update_goal(self, request):
        conductor = self._resolve_conductor(request)
        goal_id = request.match_info["id"]
        data = await request.json()
        try:
            if "milestones_completed" in data or "velocity" in data:
                conductor.goal_engine.update_progress(
                    goal_id,
                    milestones_completed=data.get("milestones_completed"),
                    velocity=data.get("velocity"),
                )
            if data.get("action") == "abandon":
                conductor.goal_engine.abandon(goal_id)
            elif data.get("action") == "pause":
                conductor.goal_engine.pause(goal_id, data.get("resume_days", 7))
            elif data.get("action") == "resume":
                conductor.goal_engine.resume(goal_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True})

    # --- Goal Templates ---
    async def _list_goal_templates(self, request):
        return self._json_response({"templates": list_templates()})

    async def _instantiate_goal_template(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        template_name = data.get("template", "")
        variables = data.get("variables", {})
        try:
            params = instantiate_template(template_name, variables)
        except KeyError as e:
            return self._json_response({"error": str(e)}, status=400)
        goal = conductor.goal_engine.register_goal(
            description=params["description"],
            expected_value=params["expected_value"],
            milestones_total=params["milestones_total"],
        )
        return self._json_response(
            {"id": goal.id, "description": goal.description}, status=201
        )

    # --- Memories ---
    async def _list_memories(self, request):
        conductor = self._resolve_conductor(request)
        query = request.query.get("q", "")
        include_archived = request.query.get("archived") == "true"
        if query:
            memories = conductor.memory_decay.search(query, include_archived=include_archived)
        elif include_archived:
            memories = conductor.memory_decay.archived_memories()
        else:
            memories = conductor.memory_decay.active_memories()
        return self._json_response({
            "memories": [{
                "id": m.id,
                "memory_type": m.memory_type.value,
                "content": m.content,
                "relevance_score": round(m.relevance_score, 3),
                "access_count": m.access_count,
                "pinned": m.pinned,
                "archived": m.archived,
                "created_at": m.created_at,
            } for m in memories],
        })

    async def _add_memory(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        content = data.get("content", "")
        if not content.strip():
            return self._json_response({"error": "content is required"}, status=400)
        memory_type_str = data.get("memory_type", "episodic")
        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.EPISODIC
        mem = conductor.memory_decay.add_memory(
            memory_type=memory_type,
            content=content,
            pinned=data.get("pinned", False),
        )
        return self._json_response({"id": mem.id}, status=201)

    # --- Events ---
    async def _list_events(self, request):
        conductor = self._resolve_conductor(request)
        limit = int(request.query.get("limit", "50"))
        engine = request.query.get("engine")
        events = conductor.event_log.recent(limit=limit, engine=engine)
        return self._json_response({"events": events})

    # --- Evaluate ---
    async def _evaluate_action(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        action = ProposedAction(
            action_type=data.get("action_type", "test"),
            payload=data.get("payload", {}),
            confidence=float(data.get("confidence", 0.7)),
            rationale=data.get("rationale", "API evaluation"),
            source=data.get("source", "api"),
            target_entity=data.get("target_entity"),
        )
        result = conductor.evaluate(action)
        return self._json_response({
            "verdict": result.final_verdict.value,
            "gate_results": [{
                "engine": gr.engine,
                "verdict": gr.verdict.value,
                "score": gr.score,
                "reason": gr.reason,
            } for gr in result.gate_results],
            "audit_trail": result.audit_trail,
            "hold_item": {
                "id": result.hold_item.id,
                "hold_reason": result.hold_item.hold_reason,
            } if result.hold_item else None,
        })

    # --- Impulse ---
    async def _fire_impulse(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        impulse_type_str = data.get("type", "idle_discovery")
        try:
            impulse_type = ImpulseType(impulse_type_str)
        except ValueError:
            return self._json_response({"error": f"Invalid impulse type: {impulse_type_str}"}, status=400)
        event = conductor.impulse_engine.force_fire(impulse_type)
        return self._json_response({
            "id": event.id,
            "type": event.impulse_type.value,
            "payload": event.payload,
            "state_snapshot": event.state_snapshot,
        })

    # --- Config ---
    async def _get_config(self, request):
        config = self._resolve_config(request)
        from dataclasses import asdict
        return self._json_response(asdict(config))

    async def _update_config(self, request):
        config = self._resolve_config(request)
        data = await request.json()
        from dataclasses import fields as dc_fields
        valid = {f.name for f in dc_fields(HumaneConfig)}
        updated = []
        for key, value in data.items():
            if key in valid:
                setattr(config, key, value)
                updated.append(key)
        if not updated:
            return self._json_response({"error": "No valid config fields provided"}, status=400)
        return self._json_response({"ok": True, "updated": updated})

    # --- Models / Providers ---
    async def _list_models(self, request):
        from humane.bot.conversation import ConversationEngine, PROVIDER_DEFAULTS
        all_status = ConversationEngine.validate_all_providers()
        active_provider = self.config.llm_provider
        providers = []
        for name, status in all_status.items():
            defaults = PROVIDER_DEFAULTS.get(name, {})
            providers.append({
                "provider": name,
                "default_model": defaults.get("model", ""),
                "base_url": defaults.get("base_url", ""),
                "sdk_installed": status["sdk_installed"],
                "sdk_package": status["sdk_package"],
                "api_key_set": status["api_key_set"],
                "ready": status["ready"],
                "active": name == active_provider,
                "error": status["error"],
            })
        return self._json_response({
            "active_provider": active_provider,
            "active_model": self.config.llm_model,
            "providers": providers,
        })

    # --- Values ---
    async def _list_values(self, request):
        conductor = self._resolve_conductor(request)
        values = conductor.values.get_values()
        return self._json_response({
            "values": [{
                "id": v.id,
                "description": v.description,
                "behavioral_pattern": v.behavioral_pattern,
                "violation_examples": v.violation_examples,
                "honoring_examples": v.honoring_examples,
                "severity": v.severity.value,
            } for v in values],
        })

    async def _add_value(self, request):
        conductor = self._resolve_conductor(request)
        data = await request.json()
        description = data.get("description", "")
        if not description.strip():
            return self._json_response({"error": "description is required"}, status=400)
        severity = ValueSeverity.HARD if data.get("severity", "").upper() == "HARD" else ValueSeverity.SOFT
        stmt = conductor.values.add_value(
            description=description,
            behavioral_pattern=data.get("behavioral_pattern", ""),
            violation_examples=data.get("violation_examples", []),
            honoring_examples=data.get("honoring_examples", []),
            severity=severity,
        )
        return self._json_response({"id": stmt.id}, status=201)

    # --- Webhooks ---
    async def _list_webhooks(self, request):
        webhooks = self.webhook_manager.list_webhooks()
        # Strip secrets from response
        safe = []
        for wh in webhooks:
            entry = dict(wh)
            entry["has_secret"] = entry.pop("secret") is not None
            safe.append(entry)
        return self._json_response({"webhooks": safe})

    async def _register_webhook(self, request):
        data = await request.json()
        url = data.get("url", "")
        events = data.get("events", [])
        secret = data.get("secret")
        try:
            webhook_id = self.webhook_manager.register(url, events, secret)
        except ValueError as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"id": webhook_id, "url": url, "events": events}, status=201)

    async def _unregister_webhook(self, request):
        webhook_id = request.match_info["id"]
        self.webhook_manager.unregister(webhook_id)
        return self._json_response({"ok": True, "id": webhook_id})

    async def _test_webhook(self, request):
        data = await request.json()
        url = data.get("url", "")
        secret = data.get("secret")
        if not url.strip():
            return self._json_response({"error": "url is required"}, status=400)
        result = await self.webhook_manager.test_webhook(url, secret)
        return self._json_response(result)

    # --- Conversations ---
    async def _list_conversations(self, request):
        conductor = self._resolve_conductor(request)
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))
        chat_id = request.query.get("chat_id")
        category = request.query.get("category")
        try:
            conn = conductor.store.conn

            # Build dynamic WHERE clause
            conditions: list = []
            params: list = []
            if chat_id is not None:
                conditions.append("chat_id = ?")
                params.append(int(chat_id))
            if category is not None:
                conditions.append("category = ?")
                params.append(category)

            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            rows = conn.execute(
                f"SELECT * FROM conversations{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            total_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM conversations{where}",
                params,
            ).fetchone()

            conversations = [
                {
                    "id": row["id"],
                    "chat_id": row["chat_id"],
                    "user_id": row["user_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "sentiment": row["sentiment"],
                    "category": row["category"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            return self._json_response({
                "conversations": conversations,
                "total": total_row["cnt"],
                "limit": limit,
                "offset": offset,
            })
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _conversation_categories(self, request):
        """Return {category: count} distribution across all conversations."""
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            rows = conn.execute(
                "SELECT COALESCE(category, 'general') as cat, COUNT(*) as cnt FROM conversations GROUP BY cat"
            ).fetchall()
            distribution = {row["cat"]: row["cnt"] for row in rows}
            return self._json_response({"categories": distribution})
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _conversation_stats(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn

            # Total count
            total_row = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()
            total_count = total_row["cnt"]

            # Average sentiment
            avg_row = conn.execute("SELECT AVG(sentiment) as avg_s FROM conversations").fetchone()
            avg_sentiment = round(avg_row["avg_s"], 4) if avg_row["avg_s"] is not None else 0.0

            # Messages by role
            role_rows = conn.execute(
                "SELECT role, COUNT(*) as cnt FROM conversations GROUP BY role"
            ).fetchall()
            messages_by_role = {row["role"]: row["cnt"] for row in role_rows}

            # Daily counts for the last 30 days
            thirty_days_ago = time.time() - (30 * 86400)
            daily_rows = conn.execute(
                """SELECT date(created_at, 'unixepoch') as day, COUNT(*) as cnt
                   FROM conversations
                   WHERE created_at >= ?
                   GROUP BY day
                   ORDER BY day""",
                (thirty_days_ago,),
            ).fetchall()
            daily_counts = [{"date": row["day"], "count": row["cnt"]} for row in daily_rows]

            # Messages per day average
            if daily_counts:
                avg_per_day = round(total_count / max(len(daily_counts), 1), 2)
            else:
                avg_per_day = 0.0

            return self._json_response({
                "total_count": total_count,
                "avg_sentiment": avg_sentiment,
                "avg_messages_per_day": avg_per_day,
                "messages_by_role": messages_by_role,
                "daily_counts": daily_counts,
            })
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _clear_conversations(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            before = request.query.get("before")
            if before is not None:
                before_ts = float(before)
                with conn:
                    result = conn.execute(
                        "DELETE FROM conversations WHERE created_at < ?",
                        (before_ts,),
                    )
                deleted = result.rowcount
            else:
                with conn:
                    result = conn.execute("DELETE FROM conversations")
                deleted = result.rowcount
            return self._json_response({"ok": True, "deleted": deleted})
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    # --- Analytics ---
    async def _analytics_state_history(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            hours = int(request.query.get("hours", "24"))
            cutoff = time.time() - (hours * 3600)
            rows = conn.execute(
                """SELECT created_at, data_json FROM events
                   WHERE engine = 'human_state' AND created_at >= ?
                   ORDER BY created_at ASC""",
                (cutoff,),
            ).fetchall()
            snapshots = []
            for row in rows:
                data = json.loads(row["data_json"])
                snapshots.append({
                    "timestamp": row["created_at"],
                    "energy": data.get("energy"),
                    "mood": data.get("mood"),
                    "fatigue": data.get("fatigue"),
                    "boredom": data.get("boredom"),
                    "social_load": data.get("social_load"),
                    "focus": data.get("focus"),
                })
            return self._json_response({"snapshots": snapshots, "hours": hours})
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _analytics_engine_stats(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            rows = conn.execute(
                """SELECT engine, data_json FROM events
                   WHERE event_type = 'gate_evaluation'"""
            ).fetchall()
            stats: dict = {}
            for row in rows:
                engine = row["engine"]
                data = json.loads(row["data_json"])
                verdict = data.get("verdict", "unknown")
                if engine not in stats:
                    stats[engine] = {"proceed": 0, "hold": 0, "defer": 0, "total": 0}
                if verdict in stats[engine]:
                    stats[engine][verdict] += 1
                stats[engine]["total"] += 1
            return self._json_response(stats)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _analytics_entity_interactions(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            rows = conn.execute(
                """SELECT entity_id,
                          COUNT(*) as interaction_count,
                          AVG(sentiment) as avg_sentiment,
                          MAX(created_at) as last_interaction_at
                   FROM interactions
                   GROUP BY entity_id"""
            ).fetchall()
            entities = []
            for row in rows:
                # Look up entity name
                entity_row = conn.execute(
                    "SELECT name FROM entities WHERE entity_id = ?",
                    (row["entity_id"],),
                ).fetchone()
                entities.append({
                    "entity_id": row["entity_id"],
                    "name": entity_row["name"] if entity_row else None,
                    "interaction_count": row["interaction_count"],
                    "avg_sentiment": round(row["avg_sentiment"], 4) if row["avg_sentiment"] is not None else 0.0,
                    "last_interaction_at": row["last_interaction_at"],
                })
            return self._json_response({"entities": entities})
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _analytics_approval_rate(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            rows = conn.execute(
                """SELECT engine, event_type FROM events
                   WHERE event_type IN ('hold_approved', 'hold_rejected')"""
            ).fetchall()
            total = 0
            approved = 0
            rejected = 0
            by_engine: dict = {}
            for row in rows:
                engine = row["engine"]
                is_approved = row["event_type"] == "hold_approved"
                total += 1
                if is_approved:
                    approved += 1
                else:
                    rejected += 1
                if engine not in by_engine:
                    by_engine[engine] = {"approved": 0, "rejected": 0, "rate": 0.0}
                if is_approved:
                    by_engine[engine]["approved"] += 1
                else:
                    by_engine[engine]["rejected"] += 1
            approval_rate = round(approved / total, 4) if total > 0 else 0.0
            for eng in by_engine.values():
                eng_total = eng["approved"] + eng["rejected"]
                eng["rate"] = round(eng["approved"] / eng_total, 4) if eng_total > 0 else 0.0
            return self._json_response({
                "total": total,
                "approved": approved,
                "rejected": rejected,
                "approval_rate": approval_rate,
                "by_engine": by_engine,
            })
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)

    async def _analytics_impulse_stats(self, request):
        conductor = self._resolve_conductor(request)
        try:
            conn = conductor.store.conn
            rows = conn.execute(
                """SELECT event_type, COUNT(*) as cnt,
                          MIN(created_at) as first_at, MAX(created_at) as last_at
                   FROM events
                   WHERE engine = 'impulse'
                   GROUP BY event_type"""
            ).fetchall()
            total = 0
            by_type: dict = {}
            first_ts = None
            last_ts = None
            for row in rows:
                count = row["cnt"]
                total += count
                by_type[row["event_type"]] = count
                if first_ts is None or row["first_at"] < first_ts:
                    first_ts = row["first_at"]
                if last_ts is None or row["last_at"] > last_ts:
                    last_ts = row["last_at"]
            if first_ts and last_ts and last_ts > first_ts:
                days_span = max((last_ts - first_ts) / 86400, 1.0)
                avg_per_day = round(total / days_span, 2)
            else:
                avg_per_day = float(total)
            return self._json_response({
                "total": total,
                "by_type": by_type,
                "avg_per_day": avg_per_day,
            })
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)


    # --- Import / Export ---
    async def _export_bundle(self, request):
        from humane.io import export_bundle
        bundle = export_bundle(self.conductor, self.config)
        return self._json_response(bundle)

    async def _export_download(self, request):
        from humane.io import export_bundle
        import datetime
        bundle = export_bundle(self.conductor, self.config)
        date_str = datetime.date.today().isoformat()
        filename = f"humane-export-{date_str}.json"
        body = json.dumps(bundle, default=str, indent=2)
        return web.Response(
            body=body,
            content_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    async def _import_bundle(self, request):
        from humane.io import import_bundle
        try:
            bundle = await request.json()
        except Exception:
            return self._json_response({"error": "Invalid JSON body"}, status=400)
        mode = request.query.get("mode", "merge")
        if mode not in ("replace", "merge"):
            return self._json_response({"error": "mode must be 'replace' or 'merge'"}, status=400)
        result = import_bundle(self.conductor, self.config, bundle, merge_mode=mode)
        if result["errors"]:
            return self._json_response(result, status=207)
        return self._json_response(result)

    # ------------------------------------------------------------------
    # WhatsApp webhook endpoints
    # ------------------------------------------------------------------

    def set_whatsapp_bot(self, whatsapp_bot):
        """Attach a WhatsAppBot instance to handle webhook requests."""
        self._whatsapp_bot = whatsapp_bot

    async def _whatsapp_verify(self, request):
        """GET /webhook/whatsapp — Meta webhook verification challenge."""
        if self._whatsapp_bot:
            return await self._whatsapp_bot.handle_verify(request)
        return web.Response(status=404, text="WhatsApp bot not configured")

    async def _whatsapp_incoming(self, request):
        """POST /webhook/whatsapp — Incoming WhatsApp messages."""
        if self._whatsapp_bot:
            return await self._whatsapp_bot.handle_incoming(request)
        return web.Response(status=404, text="WhatsApp bot not configured")

    # --- Voice ---
    async def _voice_transcribe(self, request):
        """POST /api/voice/transcribe — Transcribe audio file to text."""
        if not self.config.voice_enabled:
            return self._json_response({"error": "Voice transcription is disabled"}, status=400)

        try:
            reader = await request.multipart()
            audio_bytes = None
            audio_format = "ogg"

            async for part in reader:
                if part.name == "file":
                    # Detect format from content type or filename
                    content_type = part.headers.get("Content-Type", "")
                    filename = part.filename or ""
                    if "mp3" in content_type or "mpeg" in content_type or filename.endswith(".mp3"):
                        audio_format = "mp3"
                    elif "wav" in content_type or filename.endswith(".wav"):
                        audio_format = "wav"
                    elif "m4a" in content_type or "mp4" in content_type or filename.endswith(".m4a"):
                        audio_format = "m4a"
                    elif "webm" in content_type or filename.endswith(".webm"):
                        audio_format = "webm"
                    else:
                        audio_format = "ogg"
                    audio_bytes = await part.read()
                elif part.name == "format":
                    audio_format = (await part.text()).strip()

            if not audio_bytes:
                return self._json_response({"error": "No audio file provided. Send multipart form with 'file' field."}, status=400)

            text = await self.voice.transcribe(audio_bytes, format=audio_format)
            return self._json_response({"text": text})

        except ValueError as e:
            return self._json_response({"error": str(e)}, status=400)
        except RuntimeError as e:
            return self._json_response({"error": str(e)}, status=500)
        except Exception as e:
            logger.error("Voice transcription error: %s", e, exc_info=True)
            return self._json_response({"error": "Transcription failed"}, status=500)

    # --- Digest ---
    async def _get_digest(self, request):
        """GET /api/digest — Returns the digest JSON."""
        conductor = self._resolve_conductor(request)
        config = self._resolve_config(request)
        digest = DailyDigest(conductor, config)
        return self._json_response(digest.generate())

    async def _get_digest_preview(self, request):
        """GET /api/digest/preview — Returns formatted HTML preview."""
        conductor = self._resolve_conductor(request)
        config = self._resolve_config(request)
        digest = DailyDigest(conductor, config)
        html = digest.format_html()
        return web.Response(text=html, content_type="text/html")

    # --- Smart Schedule ---
    async def _get_schedule_all(self, request):
        """GET /api/schedule — Returns smart schedule for all entities."""
        conductor = self._resolve_conductor(request)
        scheduler = SmartScheduler(conductor.store)
        schedule = scheduler.get_schedule_for_all()
        return self._json_response({"schedule": schedule})

    async def _get_schedule_entity(self, request):
        """GET /api/schedule/{entity_id} — Detailed schedule analysis for one entity."""
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["entity_id"]
        scheduler = SmartScheduler(conductor.store)
        analysis = scheduler.analyze_response_patterns(entity_id)
        if "error" in analysis:
            return self._json_response(analysis, status=404)
        return self._json_response(analysis)

    async def _get_insights(self, request):
        """GET /api/insights — Returns predictive insights from all engines."""
        conductor = self._resolve_conductor(request)
        engine = PredictiveInsights(conductor)
        insights = engine.generate_insights()
        return self._json_response({"insights": insights, "count": len(insights)})

    # --- Audit ---
    async def _get_audit(self, request):
        """GET /api/audit — Returns detailed audit trail from events table.

        Query params:
          ?engine=       — filter by engine name
          ?event_type=   — filter by event type
          ?from=         — start timestamp (epoch seconds or ISO string)
          ?to=           — end timestamp (epoch seconds or ISO string)
          ?limit=100     — max rows (default 100)
          ?offset=0      — pagination offset
        """
        conductor = self._resolve_conductor(request)
        conn = conductor.store.conn

        limit = int(request.query.get("limit", "100"))
        offset = int(request.query.get("offset", "0"))
        engine_filter = request.query.get("engine")
        event_type_filter = request.query.get("event_type")
        from_ts = request.query.get("from")
        to_ts = request.query.get("to")

        conditions: list = []
        params: list = []

        if engine_filter:
            conditions.append("engine = ?")
            params.append(engine_filter)
        if event_type_filter:
            conditions.append("event_type = ?")
            params.append(event_type_filter)
        if from_ts:
            try:
                ts = float(from_ts)
            except ValueError:
                from datetime import datetime as _dt
                ts = _dt.fromisoformat(from_ts).timestamp()
            conditions.append("created_at >= ?")
            params.append(ts)
        if to_ts:
            try:
                ts = float(to_ts)
            except ValueError:
                from datetime import datetime as _dt
                ts = _dt.fromisoformat(to_ts).timestamp()
            conditions.append("created_at <= ?")
            params.append(ts)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM events{where}", params
        ).fetchone()
        total = count_row["cnt"]

        rows = conn.execute(
            f"SELECT * FROM events{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

        events = []
        for row in rows:
            data = json.loads(row["data_json"])
            verdict = data.get("verdict") or data.get("final_verdict")
            events.append({
                "id": row["id"],
                "event_type": row["event_type"],
                "engine": row["engine"],
                "data": data,
                "verdict": verdict,
                "created_at": row["created_at"],
            })

        engines = [r["engine"] for r in conn.execute(
            "SELECT DISTINCT engine FROM events ORDER BY engine"
        ).fetchall()]
        event_types = [r["event_type"] for r in conn.execute(
            "SELECT DISTINCT event_type FROM events ORDER BY event_type"
        ).fetchall()]

        return self._json_response({
            "events": events,
            "total": total,
            "limit": limit,
            "offset": offset,
            "filters": {
                "engines": engines,
                "event_types": event_types,
            },
        })

    # ------------------------------------------------------------------
    # Plugin endpoints
    # ------------------------------------------------------------------
    async def _list_plugins(self, request):
        """GET /api/plugins — List all loaded plugins."""
        conductor = self._resolve_conductor(request)
        plugins = conductor.plugin_manager.list_plugins()
        return self._json_response({"plugins": plugins})

    async def _reload_plugins(self, request):
        """POST /api/plugins/reload — Re-scan plugins directory and load new plugins."""
        conductor = self._resolve_conductor(request)
        pm = conductor.plugin_manager
        # Unload all existing plugins first
        for info in list(pm.list_plugins()):
            try:
                pm.unload(info["name"])
            except KeyError:
                pass
        count = pm.discover_and_load_all()
        plugins = pm.list_plugins()
        return self._json_response({
            "ok": True,
            "loaded": count,
            "plugins": plugins,
        })

    async def _toggle_plugin(self, request):
        """POST /api/plugins/{name}/toggle — Enable/disable a plugin."""
        conductor = self._resolve_conductor(request)
        name = request.match_info["name"]
        try:
            active = conductor.plugin_manager.toggle(name)
        except KeyError:
            return self._json_response({"error": f"Plugin '{name}' not found"}, status=404)
        return self._json_response({"ok": True, "name": name, "active": active})

    # ------------------------------------------------------------------
    # Data Retention endpoints
    # ------------------------------------------------------------------
    async def _get_retention(self, request):
        """GET /api/retention — Returns current retention policy config + stats."""
        config = self._resolve_config(request)
        conductor = self._resolve_conductor(request)
        mgr = RetentionManager(conductor.store, config)
        stats = mgr.get_retention_stats()
        return self._json_response({
            "enabled": config.retention_enabled,
            "retention_conversations_days": config.retention_conversations_days,
            "retention_events_days": config.retention_events_days,
            "retention_memory_archive_days": config.retention_memory_archive_days,
            "retention_holds_days": config.retention_holds_days,
            "retention_run_hour": config.retention_run_hour,
            "stats": stats,
        })

    async def _retention_preview(self, request):
        """POST /api/retention/preview — Dry run showing what would be affected."""
        config = self._resolve_config(request)
        conductor = self._resolve_conductor(request)
        mgr = RetentionManager(conductor.store, config)
        preview = mgr.dry_run()
        return self._json_response(preview)

    async def _retention_apply(self, request):
        """POST /api/retention/apply — Execute retention policies now."""
        config = self._resolve_config(request)
        conductor = self._resolve_conductor(request)
        mgr = RetentionManager(conductor.store, config)
        results = mgr.apply_policies()
        conductor.event_log.log("retention_applied", "retention", results)
        return self._json_response({"ok": True, "results": results})

    # ------------------------------------------------------------------
    # API Documentation endpoints
    # ------------------------------------------------------------------
    async def _serve_api_docs(self, request):
        """GET /api/docs -- Serve Swagger UI HTML page."""
        html = """<!DOCTYPE html>
<html>
<head>
  <title>Humane API Docs</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>SwaggerUIBundle({url:'/api/openapi.json',dom_id:'#swagger-ui',deepLinking:true})</script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    # ------------------------------------------------------------------
    # GDPR endpoints
    # ------------------------------------------------------------------

    async def _gdpr_export(self, request):
        """GET /api/gdpr/export -- Returns full personal data JSON."""
        conductor = self._resolve_conductor(request)
        exporter = GDPRExporter(conductor.store, conductor)
        data = exporter.export_personal_data()
        return self._json_response(data)

    async def _gdpr_export_download(self, request):
        """GET /api/gdpr/export/download -- Returns ZIP file download."""
        conductor = self._resolve_conductor(request)
        exporter = GDPRExporter(conductor.store, conductor)
        import datetime
        zip_bytes, _ = exporter.export_as_zip()
        date_str = datetime.date.today().isoformat()
        filename = f"humane-gdpr-export-{date_str}.zip"
        return web.Response(
            body=zip_bytes,
            content_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    async def _gdpr_export_entity(self, request):
        """GET /api/gdpr/export/{entity_id} -- Export data for specific entity."""
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["entity_id"]
        entity = conductor.store.get_entity(entity_id)
        if not entity:
            return self._json_response({"error": "Entity not found"}, status=404)
        exporter = GDPRExporter(conductor.store, conductor)
        if request.query.get("format") == "zip":
            import datetime
            zip_bytes, _ = exporter.export_as_zip(entity_id=entity_id)
            date_str = datetime.date.today().isoformat()
            filename = f"humane-gdpr-export-{entity_id}-{date_str}.zip"
            return web.Response(
                body=zip_bytes,
                content_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        data = exporter.export_personal_data(entity_id=entity_id)
        return self._json_response(data)

    async def _gdpr_erase(self, request):
        """DELETE /api/gdpr/erase/{entity_id} -- Right to erasure for an entity."""
        conductor = self._resolve_conductor(request)
        entity_id = request.match_info["entity_id"]
        entity = conductor.store.get_entity(entity_id)
        if not entity:
            return self._json_response({"error": "Entity not found"}, status=404)
        exporter = GDPRExporter(conductor.store, conductor)
        result = exporter.delete_personal_data(entity_id)
        if "error" in result:
            return self._json_response(result, status=404)
        return self._json_response(result)

        return web.Response(text=html, content_type="text/html")

    async def _serve_openapi_spec(self, request):
        """GET /api/openapi.json -- Return the OpenAPI specification."""
        spec = generate_openapi_spec()
        return self._json_response(spec)


    # ------------------------------------------------------------------
    # Simulation / Branching endpoints
    # ------------------------------------------------------------------
    async def _simulate_message(self, request):
        """POST /api/simulate — Simulate a hypothetical user message."""
        conductor = self._resolve_conductor(request)
        data = await request.json()
        message = data.get("message", "").strip()
        if not message:
            return self._json_response({"error": "message is required"}, status=400)
        chat_id = data.get("chat_id")
        conversation_engine = getattr(self, "_conversation_engine", None)
        branch = ConversationBranch(conductor, conversation_engine)
        result = await branch.simulate(message, chat_id=chat_id)
        return self._json_response(result)

    async def _simulate_compare(self, request):
        """POST /api/simulate/compare — Compare multiple hypothetical messages."""
        conductor = self._resolve_conductor(request)
        data = await request.json()
        messages = data.get("messages", [])
        if not messages or not isinstance(messages, list):
            return self._json_response({"error": "messages array is required"}, status=400)
        if len(messages) > 5:
            return self._json_response({"error": "Maximum 5 messages for comparison"}, status=400)
        chat_id = data.get("chat_id")
        conversation_engine = getattr(self, "_conversation_engine", None)
        branch = ConversationBranch(conductor, conversation_engine)
        results = await branch.compare(messages, chat_id=chat_id)
        return self._json_response({"comparisons": results, "count": len(results)})
    # ------------------------------------------------------------------
    # A/B Testing endpoints
    # ------------------------------------------------------------------
    async def _list_ab_tests(self, request):
        """GET /api/ab-tests — List all A/B tests."""
        tests = self.ab_manager.list_tests()
        return self._json_response({"tests": tests})

    async def _create_ab_test(self, request):
        """POST /api/ab-tests — Create a new A/B test."""
        data = await request.json()
        name = data.get("name", "").strip()
        personality_a = data.get("personality_a", "").strip()
        personality_b = data.get("personality_b", "").strip()
        if not name:
            return self._json_response({"error": "name is required"}, status=400)
        if not personality_a or not personality_b:
            return self._json_response(
                {"error": "personality_a and personality_b are required"}, status=400
            )
        test_id = self.ab_manager.create_test(name, personality_a, personality_b)
        return self._json_response({"id": test_id, "name": name}, status=201)

    async def _get_ab_test_results(self, request):
        """GET /api/ab-tests/{id}/results — Get test results with stats."""
        test_id = request.match_info["id"]
        results = self.ab_manager.get_results(test_id)
        if "error" in results:
            return self._json_response(results, status=404)
        return self._json_response(results)

    async def _end_ab_test(self, request):
        """POST /api/ab-tests/{id}/end — End test, optionally declare winner."""
        test_id = request.match_info["id"]
        data = await request.json()
        winner = data.get("winner")
        if winner and winner not in ("A", "B"):
            return self._json_response(
                {"error": "winner must be 'A' or 'B'"}, status=400
            )
        self.ab_manager.end_test(test_id, winner=winner)
        return self._json_response({"ok": True, "test_id": test_id, "winner": winner})

    # ------------------------------------------------------------------
    # Feedback & Tuning endpoints
    # ------------------------------------------------------------------

    async def _feedback_stats(self, request):
        """GET /api/feedback/stats — Training data statistics."""
        conductor = self._resolve_conductor(request)
        collector = FeedbackCollector(conductor.store)
        stats = collector.get_stats()
        return self._json_response(stats)

    async def _feedback_export(self, request):
        """GET /api/feedback/export?format=jsonl — Download training data."""
        conductor = self._resolve_conductor(request)
        fmt = request.query.get("format", "jsonl")
        if fmt not in ("jsonl", "csv"):
            return self._json_response({"error": "format must be jsonl or csv"}, status=400)

        collector = FeedbackCollector(conductor.store)
        data = collector.export_training_data(format=fmt)

        content_type = "application/jsonl" if fmt == "jsonl" else "text/csv"
        filename = f"humane_training_data.{fmt}"
        return web.Response(
            text=data,
            content_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    async def _feedback_recommendations(self, request):
        """GET /api/feedback/recommendations — Threshold optimization recommendations."""
        conductor = self._resolve_conductor(request)
        config = self._resolve_config(request)
        optimizer = ThresholdOptimizer(conductor.store, config)
        analysis = optimizer.analyze()
        return self._json_response(analysis)

    async def _feedback_auto_tune(self, request):
        """POST /api/feedback/auto-tune — Apply recommended threshold changes."""
        conductor = self._resolve_conductor(request)
        config = self._resolve_config(request)
        dry_run = request.query.get("dry_run", "true").lower() != "false"
        optimizer = ThresholdOptimizer(conductor.store, config)
        result = optimizer.auto_tune(dry_run=dry_run)
        return self._json_response(result)

    async def start(self, port: Optional[int] = None):
        """Start the API server. Returns the AppRunner for lifecycle management."""
        port = port or self.config.api_port
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("API server running at http://localhost:%d", port)
        return runner

    async def shutdown(self) -> None:
        """Clean up resources (webhook session, etc.)."""
        await self.webhook_manager.close()
        if self._whatsapp_bot:
            await self._whatsapp_bot.close()
