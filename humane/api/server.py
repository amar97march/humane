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

logger = logging.getLogger("humane.api")


class APIServer:
    def __init__(self, conductor: Conductor, config: HumaneConfig):
        self.conductor = conductor
        self.config = config
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        # Web dashboard
        self.app.router.add_get("/", self._serve_dashboard)

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

        # Goals
        self.app.router.add_get("/api/goals", self._list_goals)
        self.app.router.add_post("/api/goals", self._add_goal)
        self.app.router.add_patch("/api/goals/{id}", self._update_goal)

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

        # CORS middleware
        self.app.middlewares.append(self._cors_middleware)

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
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    def _json_response(self, data, status=200):
        return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, default=str))

    # --- Dashboard ---
    async def _serve_dashboard(self, request):
        html_path = Path(__file__).parent.parent / "web" / "index.html"
        if html_path.exists():
            return web.FileResponse(html_path)
        return web.Response(text="Dashboard not found", status=404)

    # --- State ---
    async def _get_state(self, request):
        self.conductor.human_state.tick()
        state = self.conductor.get_state_snapshot()
        return self._json_response({
            "state": state,
            "dqm": self.conductor.human_state.decision_quality_multiplier,
            "preferred_task_type": self.conductor.human_state.preferred_task_type.value,
        })

    # --- Hold Queue ---
    async def _get_queue(self, request):
        queue = self.conductor.get_hold_queue()
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
        hold_id = request.match_info["id"]
        try:
            self.conductor.approve_hold(hold_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True, "action": "approved", "id": hold_id})

    async def _reject_hold(self, request):
        hold_id = request.match_info["id"]
        try:
            self.conductor.reject_hold(hold_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True, "action": "rejected", "id": hold_id})

    # --- Entities ---
    async def _list_entities(self, request):
        entities = self.conductor.relational.list_entities()
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
        data = await request.json()
        name = data.get("name", "")
        if not name.strip():
            return self._json_response({"error": "name is required"}, status=400)
        entity_type_str = data.get("entity_type", "unknown")
        try:
            entity_type = EntityType(entity_type_str)
        except ValueError:
            entity_type = EntityType.UNKNOWN
        entity = self.conductor.relational.add_entity(name, entity_type)
        return self._json_response({"entity_id": entity.entity_id, "name": entity.name}, status=201)

    async def _get_entity(self, request):
        entity_id = request.match_info["id"]
        ctx = self.conductor.relational.get_context(entity_id)
        if not ctx:
            return self._json_response({"error": "Entity not found"}, status=404)
        return self._json_response(ctx)

    async def _log_interaction(self, request):
        entity_id = request.match_info["id"]
        data = await request.json()
        sentiment = float(data.get("sentiment", 0.0))
        summary = data.get("summary", "")
        self.conductor.relational.log_interaction(entity_id, sentiment, summary)
        return self._json_response({"ok": True})

    # --- Goals ---
    async def _list_goals(self, request):
        status_filter = request.query.get("status")
        if status_filter == "active":
            goals = self.conductor.goal_engine.active_goals()
        else:
            goals = self.conductor.store.list_goals(status_filter)
        return self._json_response({
            "goals": [{
                "id": g.id,
                "description": g.description,
                "expected_value": g.expected_value,
                "remaining_effort": g.remaining_effort,
                "progress_velocity": g.progress_velocity,
                "milestones_total": g.milestones_total,
                "milestones_completed": g.milestones_completed,
                "roi": self.conductor.goal_engine.compute_roi(g),
                "status": g.status,
                "created_at": g.created_at,
            } for g in goals],
        })

    async def _add_goal(self, request):
        data = await request.json()
        description = data.get("description", "")
        if not description.strip():
            return self._json_response({"error": "description is required"}, status=400)
        goal = self.conductor.goal_engine.register_goal(
            description=description,
            expected_value=float(data.get("expected_value", 1.0)),
            milestones_total=int(data.get("milestones_total", 0)),
        )
        return self._json_response({"id": goal.id, "description": goal.description}, status=201)

    async def _update_goal(self, request):
        goal_id = request.match_info["id"]
        data = await request.json()
        try:
            if "milestones_completed" in data or "velocity" in data:
                self.conductor.goal_engine.update_progress(
                    goal_id,
                    milestones_completed=data.get("milestones_completed"),
                    velocity=data.get("velocity"),
                )
            if data.get("action") == "abandon":
                self.conductor.goal_engine.abandon(goal_id)
            elif data.get("action") == "pause":
                self.conductor.goal_engine.pause(goal_id, data.get("resume_days", 7))
            elif data.get("action") == "resume":
                self.conductor.goal_engine.resume(goal_id)
        except Exception as e:
            return self._json_response({"error": str(e)}, status=400)
        return self._json_response({"ok": True})

    # --- Memories ---
    async def _list_memories(self, request):
        query = request.query.get("q", "")
        include_archived = request.query.get("archived") == "true"
        if query:
            memories = self.conductor.memory_decay.search(query, include_archived=include_archived)
        else:
            try:
                memories = self.conductor.memory_decay.active_memories()
            except AttributeError:
                memories = self.conductor.store.list_memories(include_archived=include_archived)
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
        data = await request.json()
        content = data.get("content", "")
        if not content.strip():
            return self._json_response({"error": "content is required"}, status=400)
        memory_type_str = data.get("memory_type", "episodic")
        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            memory_type = MemoryType.EPISODIC
        mem = self.conductor.memory_decay.add_memory(
            memory_type=memory_type,
            content=content,
            pinned=data.get("pinned", False),
        )
        return self._json_response({"id": mem.id}, status=201)

    # --- Events ---
    async def _list_events(self, request):
        limit = int(request.query.get("limit", "50"))
        engine = request.query.get("engine")
        events = self.conductor.event_log.recent(limit=limit, engine=engine)
        return self._json_response({"events": events})

    # --- Evaluate ---
    async def _evaluate_action(self, request):
        data = await request.json()
        action = ProposedAction(
            action_type=data.get("action_type", "test"),
            payload=data.get("payload", {}),
            confidence=float(data.get("confidence", 0.7)),
            rationale=data.get("rationale", "API evaluation"),
            source=data.get("source", "api"),
            target_entity=data.get("target_entity"),
        )
        result = self.conductor.evaluate(action)
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
        data = await request.json()
        impulse_type_str = data.get("type", "idle_discovery")
        try:
            impulse_type = ImpulseType(impulse_type_str)
        except ValueError:
            return self._json_response({"error": f"Invalid impulse type: {impulse_type_str}"}, status=400)
        event = self.conductor.impulse_engine.force_fire(impulse_type)
        return self._json_response({
            "id": event.id,
            "type": event.impulse_type.value,
            "payload": event.payload,
            "state_snapshot": event.state_snapshot,
        })

    # --- Config ---
    async def _get_config(self, request):
        from dataclasses import asdict
        return self._json_response(asdict(self.config))

    async def _update_config(self, request):
        data = await request.json()
        from dataclasses import fields as dc_fields
        valid = {f.name for f in dc_fields(HumaneConfig)}
        updated = []
        for key, value in data.items():
            if key in valid:
                setattr(self.config, key, value)
                updated.append(key)
        if not updated:
            return self._json_response({"error": "No valid config fields provided"}, status=400)
        return self._json_response({"ok": True, "updated": updated})

    # --- Values ---
    async def _list_values(self, request):
        values = self.conductor.values.get_values()
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
        data = await request.json()
        description = data.get("description", "")
        if not description.strip():
            return self._json_response({"error": "description is required"}, status=400)
        severity = ValueSeverity.HARD if data.get("severity") == "hard" else ValueSeverity.SOFT
        stmt = self.conductor.values.add_value(
            description=description,
            behavioral_pattern=data.get("behavioral_pattern", ""),
            violation_examples=data.get("violation_examples", []),
            honoring_examples=data.get("honoring_examples", []),
            severity=severity,
        )
        return self._json_response({"id": stmt.id}, status=201)

    async def start(self, port: Optional[int] = None):
        """Start the API server. Returns the AppRunner for lifecycle management."""
        port = port or self.config.api_port
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("API server running at http://localhost:%d", port)
        return runner
