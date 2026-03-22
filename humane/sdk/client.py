"""Synchronous Python client for the Humane REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests


class HumaneAPIError(Exception):
    """Raised when the Humane API returns an error response."""

    def __init__(self, status_code: int, detail: Any = None):
        self.status_code = status_code
        self.detail = detail
        msg = f"HTTP {status_code}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class HumaneClient:
    """Synchronous client for the Humane REST API.

    Parameters
    ----------
    base_url : str
        Root URL of the Humane API server (default ``http://localhost:8765``).
    api_key : str | None
        Optional API key sent as ``Authorization: Bearer <key>`` header.
    agent_id : str | None
        Optional agent id appended as ``?agent_id=`` query parameter for
        multi-agent setups.
    timeout : float
        Default request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.agent_id = agent_id
        self.timeout = timeout
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if self.agent_id:
            params["agent_id"] = self.agent_id
        if extra:
            params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Any:
        resp = self._session.request(
            method,
            self._url(path),
            params=self._params(params),
            json=json,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise HumaneAPIError(resp.status_code, detail)
        return resp.json()

    def _get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: Optional[Any] = None) -> Any:
        return self._request("POST", path, json=json)

    def _patch(self, path: str, json: Optional[Any] = None) -> Any:
        return self._request("PATCH", path, json=json)

    def _delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """GET /api/state — full state snapshot."""
        return self._get("/api/state")

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    def list_entities(self) -> list:
        """GET /api/entities"""
        return self._get("/api/entities")

    def add_entity(self, name: str, entity_type: str = "unknown") -> dict:
        """POST /api/entities"""
        return self._post("/api/entities", json={
            "name": name,
            "entity_type": entity_type,
        })

    def get_entity(self, entity_id: str) -> dict:
        """GET /api/entities/{id}"""
        return self._get(f"/api/entities/{entity_id}")

    def get_entity_timeline(self, entity_id: str, limit: int = 100) -> dict:
        """GET /api/entities/{id}/timeline"""
        return self._get(f"/api/entities/{entity_id}/timeline", limit=limit)

    def log_interaction(
        self,
        entity_id: str,
        sentiment: float,
        summary: str,
    ) -> dict:
        """POST /api/entities/{id}/interact"""
        return self._post(f"/api/entities/{entity_id}/interact", json={
            "sentiment": sentiment,
            "summary": summary,
        })

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    def list_goals(self, status: Optional[str] = None) -> list:
        """GET /api/goals — optionally filter by status ('active', etc.)."""
        return self._get("/api/goals", status=status)

    def add_goal(
        self,
        description: str,
        expected_value: float = 1.0,
        milestones: int = 0,
    ) -> dict:
        """POST /api/goals"""
        return self._post("/api/goals", json={
            "description": description,
            "expected_value": expected_value,
            "milestones_total": milestones,
        })

    def pause_goal(self, goal_id: str, resume_days: int = 7) -> dict:
        """PATCH /api/goals/{id} with action=pause."""
        return self._patch(f"/api/goals/{goal_id}", json={
            "action": "pause",
            "resume_days": resume_days,
        })

    def resume_goal(self, goal_id: str) -> dict:
        """PATCH /api/goals/{id} with action=resume."""
        return self._patch(f"/api/goals/{goal_id}", json={"action": "resume"})

    def abandon_goal(self, goal_id: str) -> dict:
        """PATCH /api/goals/{id} with action=abandon."""
        return self._patch(f"/api/goals/{goal_id}", json={"action": "abandon"})

    def update_goal_progress(
        self,
        goal_id: str,
        milestones_completed: Optional[int] = None,
        velocity: Optional[float] = None,
    ) -> dict:
        """PATCH /api/goals/{id} — update milestones_completed / velocity."""
        body: Dict[str, Any] = {}
        if milestones_completed is not None:
            body["milestones_completed"] = milestones_completed
        if velocity is not None:
            body["velocity"] = velocity
        return self._patch(f"/api/goals/{goal_id}", json=body)

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    def list_memories(
        self,
        query: Optional[str] = None,
        archived: bool = False,
    ) -> list:
        """GET /api/memories"""
        params: Dict[str, Any] = {}
        if query:
            params["q"] = query
        if archived:
            params["archived"] = "true"
        return self._get("/api/memories", **params)

    def add_memory(
        self,
        content: str,
        memory_type: str = "episodic",
        pinned: bool = False,
    ) -> dict:
        """POST /api/memories"""
        return self._post("/api/memories", json={
            "content": content,
            "memory_type": memory_type,
            "pinned": pinned,
        })

    # ------------------------------------------------------------------
    # Actions — evaluate & impulse
    # ------------------------------------------------------------------

    def evaluate(
        self,
        action_type: str,
        confidence: float = 0.7,
        rationale: str = "",
        target_entity: Optional[str] = None,
        payload: Optional[dict] = None,
        source: str = "sdk",
    ) -> dict:
        """POST /api/evaluate"""
        body: Dict[str, Any] = {
            "action_type": action_type,
            "confidence": confidence,
            "rationale": rationale,
            "source": source,
        }
        if target_entity is not None:
            body["target_entity"] = target_entity
        if payload is not None:
            body["payload"] = payload
        return self._post("/api/evaluate", json=body)

    def fire_impulse(self, impulse_type: str = "idle_discovery") -> dict:
        """POST /api/impulse/fire"""
        return self._post("/api/impulse/fire", json={"type": impulse_type})

    # ------------------------------------------------------------------
    # Hold queue
    # ------------------------------------------------------------------

    def get_queue(self) -> list:
        """GET /api/queue"""
        return self._get("/api/queue")

    def approve(self, hold_id: str) -> dict:
        """POST /api/queue/{id}/approve"""
        return self._post(f"/api/queue/{hold_id}/approve")

    def reject(self, hold_id: str) -> dict:
        """POST /api/queue/{id}/reject"""
        return self._post(f"/api/queue/{hold_id}/reject")

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def list_values(self) -> list:
        """GET /api/values"""
        return self._get("/api/values")

    def add_value(
        self,
        description: str,
        severity: str = "SOFT",
        behavioral_pattern: str = "",
        violation_examples: Optional[List[str]] = None,
        honoring_examples: Optional[List[str]] = None,
    ) -> dict:
        """POST /api/values"""
        return self._post("/api/values", json={
            "description": description,
            "severity": severity,
            "behavioral_pattern": behavioral_pattern,
            "violation_examples": violation_examples or [],
            "honoring_examples": honoring_examples or [],
        })

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self) -> dict:
        """GET /api/config"""
        return self._get("/api/config")

    def update_config(self, **kwargs: Any) -> dict:
        """PATCH /api/config — pass config fields as keyword arguments."""
        return self._patch("/api/config", json=kwargs)

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_data(self) -> dict:
        """GET /api/export"""
        return self._get("/api/export")

    def import_data(self, bundle: dict, mode: str = "merge") -> dict:
        """POST /api/import"""
        return self._request("POST", "/api/import", params={"mode": mode}, json=bundle)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def list_events(self, limit: int = 50, engine: Optional[str] = None) -> dict:
        """GET /api/events"""
        return self._get("/api/events", limit=limit, engine=engine)

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    def register_webhook(
        self,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
    ) -> dict:
        """POST /api/webhooks"""
        body: Dict[str, Any] = {"url": url, "events": events}
        if secret is not None:
            body["secret"] = secret
        return self._post("/api/webhooks", json=body)

    def list_webhooks(self) -> list:
        """GET /api/webhooks"""
        return self._get("/api/webhooks")

    def delete_webhook(self, webhook_id: str) -> dict:
        """DELETE /api/webhooks/{id}"""
        return self._delete(f"/api/webhooks/{webhook_id}")

    def test_webhook(self, url: str, secret: Optional[str] = None) -> dict:
        """POST /api/webhooks/test"""
        body: Dict[str, Any] = {"url": url}
        if secret is not None:
            body["secret"] = secret
        return self._post("/api/webhooks/test", json=body)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def analytics_state_history(self, hours: int = 24) -> dict:
        """GET /api/analytics/state-history"""
        return self._get("/api/analytics/state-history", hours=hours)

    def analytics_engine_stats(self) -> dict:
        """GET /api/analytics/engine-stats"""
        return self._get("/api/analytics/engine-stats")

    def analytics_entity_interactions(self) -> dict:
        """GET /api/analytics/entity-interactions"""
        return self._get("/api/analytics/entity-interactions")

    def analytics_approval_rate(self) -> dict:
        """GET /api/analytics/approval-rate"""
        return self._get("/api/analytics/approval-rate")

    def analytics_impulse_stats(self) -> dict:
        """GET /api/analytics/impulse-stats"""
        return self._get("/api/analytics/impulse-stats")

    # ------------------------------------------------------------------
    # Agents (multi-agent management)
    # ------------------------------------------------------------------

    def list_agents(self) -> dict:
        """GET /api/agents"""
        return self._get("/api/agents")

    def create_agent(
        self,
        name: str,
        personality: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> dict:
        """POST /api/agents"""
        body: Dict[str, Any] = {"name": name}
        if personality is not None:
            body["personality"] = personality
        if llm_provider is not None:
            body["llm_provider"] = llm_provider
        return self._post("/api/agents", json=body)

    def get_agent_state(self, agent_id: str) -> dict:
        """GET /api/agents/{id}/state"""
        return self._get(f"/api/agents/{agent_id}/state")

    def delete_agent(self, agent_id: str) -> dict:
        """DELETE /api/agents/{id}"""
        return self._delete(f"/api/agents/{agent_id}")

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        chat_id: Optional[int] = None,
    ) -> dict:
        """GET /api/conversations"""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if chat_id is not None:
            params["chat_id"] = chat_id
        return self._get("/api/conversations", **params)

    def conversation_stats(self) -> dict:
        """GET /api/conversations/stats"""
        return self._get("/api/conversations/stats")

    def clear_conversations(self, before: Optional[float] = None) -> dict:
        """DELETE /api/conversations"""
        params: Dict[str, Any] = {}
        if before is not None:
            params["before"] = before
        return self._request("DELETE", "/api/conversations", params=params)

    # ------------------------------------------------------------------
    # Models / Providers
    # ------------------------------------------------------------------

    def list_models(self) -> dict:
        """GET /api/models"""
        return self._get("/api/models")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying requests session."""
        self._session.close()

    def __enter__(self) -> "HumaneClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
