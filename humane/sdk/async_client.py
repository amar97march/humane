"""Asynchronous Python client for the Humane REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import aiohttp


class HumaneAPIError(Exception):
    """Raised when the Humane API returns an error response."""

    def __init__(self, status_code: int, detail: Any = None):
        self.status_code = status_code
        self.detail = detail
        msg = f"HTTP {status_code}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class AsyncHumaneClient:
    """Asynchronous client for the Humane REST API.

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
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers: Dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=self.timeout,
            )
        return self._session

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Any:
        session = self._get_session()
        async with session.request(
            method,
            self._url(path),
            params=self._params(params),
            json=json,
        ) as resp:
            if resp.status >= 400:
                try:
                    detail = await resp.json()
                except Exception:
                    detail = await resp.text()
                raise HumaneAPIError(resp.status, detail)
            return await resp.json()

    async def _get(self, path: str, **params: Any) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json: Optional[Any] = None) -> Any:
        return await self._request("POST", path, json=json)

    async def _patch(self, path: str, json: Optional[Any] = None) -> Any:
        return await self._request("PATCH", path, json=json)

    async def _delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def get_state(self) -> dict:
        """GET /api/state — full state snapshot."""
        return await self._get("/api/state")

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def list_entities(self) -> list:
        """GET /api/entities"""
        return await self._get("/api/entities")

    async def add_entity(self, name: str, entity_type: str = "unknown") -> dict:
        """POST /api/entities"""
        return await self._post("/api/entities", json={
            "name": name,
            "entity_type": entity_type,
        })

    async def get_entity(self, entity_id: str) -> dict:
        """GET /api/entities/{id}"""
        return await self._get(f"/api/entities/{entity_id}")

    async def get_entity_timeline(self, entity_id: str, limit: int = 100) -> dict:
        """GET /api/entities/{id}/timeline"""
        return await self._get(f"/api/entities/{entity_id}/timeline", limit=limit)

    async def log_interaction(
        self,
        entity_id: str,
        sentiment: float,
        summary: str,
    ) -> dict:
        """POST /api/entities/{id}/interact"""
        return await self._post(f"/api/entities/{entity_id}/interact", json={
            "sentiment": sentiment,
            "summary": summary,
        })

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    async def list_goals(self, status: Optional[str] = None) -> list:
        """GET /api/goals — optionally filter by status ('active', etc.)."""
        return await self._get("/api/goals", status=status)

    async def add_goal(
        self,
        description: str,
        expected_value: float = 1.0,
        milestones: int = 0,
    ) -> dict:
        """POST /api/goals"""
        return await self._post("/api/goals", json={
            "description": description,
            "expected_value": expected_value,
            "milestones_total": milestones,
        })

    async def pause_goal(self, goal_id: str, resume_days: int = 7) -> dict:
        """PATCH /api/goals/{id} with action=pause."""
        return await self._patch(f"/api/goals/{goal_id}", json={
            "action": "pause",
            "resume_days": resume_days,
        })

    async def resume_goal(self, goal_id: str) -> dict:
        """PATCH /api/goals/{id} with action=resume."""
        return await self._patch(f"/api/goals/{goal_id}", json={"action": "resume"})

    async def abandon_goal(self, goal_id: str) -> dict:
        """PATCH /api/goals/{id} with action=abandon."""
        return await self._patch(f"/api/goals/{goal_id}", json={"action": "abandon"})

    async def update_goal_progress(
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
        return await self._patch(f"/api/goals/{goal_id}", json=body)

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    async def list_memories(
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
        return await self._get("/api/memories", **params)

    async def add_memory(
        self,
        content: str,
        memory_type: str = "episodic",
        pinned: bool = False,
    ) -> dict:
        """POST /api/memories"""
        return await self._post("/api/memories", json={
            "content": content,
            "memory_type": memory_type,
            "pinned": pinned,
        })

    # ------------------------------------------------------------------
    # Actions — evaluate & impulse
    # ------------------------------------------------------------------

    async def evaluate(
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
        return await self._post("/api/evaluate", json=body)

    async def fire_impulse(self, impulse_type: str = "idle_discovery") -> dict:
        """POST /api/impulse/fire"""
        return await self._post("/api/impulse/fire", json={"type": impulse_type})

    # ------------------------------------------------------------------
    # Hold queue
    # ------------------------------------------------------------------

    async def get_queue(self) -> list:
        """GET /api/queue"""
        return await self._get("/api/queue")

    async def approve(self, hold_id: str) -> dict:
        """POST /api/queue/{id}/approve"""
        return await self._post(f"/api/queue/{hold_id}/approve")

    async def reject(self, hold_id: str) -> dict:
        """POST /api/queue/{id}/reject"""
        return await self._post(f"/api/queue/{hold_id}/reject")

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    async def list_values(self) -> list:
        """GET /api/values"""
        return await self._get("/api/values")

    async def add_value(
        self,
        description: str,
        severity: str = "SOFT",
        behavioral_pattern: str = "",
        violation_examples: Optional[List[str]] = None,
        honoring_examples: Optional[List[str]] = None,
    ) -> dict:
        """POST /api/values"""
        return await self._post("/api/values", json={
            "description": description,
            "severity": severity,
            "behavioral_pattern": behavioral_pattern,
            "violation_examples": violation_examples or [],
            "honoring_examples": honoring_examples or [],
        })

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def get_config(self) -> dict:
        """GET /api/config"""
        return await self._get("/api/config")

    async def update_config(self, **kwargs: Any) -> dict:
        """PATCH /api/config — pass config fields as keyword arguments."""
        return await self._patch("/api/config", json=kwargs)

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    async def export_data(self) -> dict:
        """GET /api/export"""
        return await self._get("/api/export")

    async def import_data(self, bundle: dict, mode: str = "merge") -> dict:
        """POST /api/import"""
        return await self._request("POST", "/api/import", params={"mode": mode}, json=bundle)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def list_events(self, limit: int = 50, engine: Optional[str] = None) -> dict:
        """GET /api/events"""
        return await self._get("/api/events", limit=limit, engine=engine)

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    async def register_webhook(
        self,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
    ) -> dict:
        """POST /api/webhooks"""
        body: Dict[str, Any] = {"url": url, "events": events}
        if secret is not None:
            body["secret"] = secret
        return await self._post("/api/webhooks", json=body)

    async def list_webhooks(self) -> list:
        """GET /api/webhooks"""
        return await self._get("/api/webhooks")

    async def delete_webhook(self, webhook_id: str) -> dict:
        """DELETE /api/webhooks/{id}"""
        return await self._delete(f"/api/webhooks/{webhook_id}")

    async def test_webhook(self, url: str, secret: Optional[str] = None) -> dict:
        """POST /api/webhooks/test"""
        body: Dict[str, Any] = {"url": url}
        if secret is not None:
            body["secret"] = secret
        return await self._post("/api/webhooks/test", json=body)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def analytics_state_history(self, hours: int = 24) -> dict:
        """GET /api/analytics/state-history"""
        return await self._get("/api/analytics/state-history", hours=hours)

    async def analytics_engine_stats(self) -> dict:
        """GET /api/analytics/engine-stats"""
        return await self._get("/api/analytics/engine-stats")

    async def analytics_entity_interactions(self) -> dict:
        """GET /api/analytics/entity-interactions"""
        return await self._get("/api/analytics/entity-interactions")

    async def analytics_approval_rate(self) -> dict:
        """GET /api/analytics/approval-rate"""
        return await self._get("/api/analytics/approval-rate")

    async def analytics_impulse_stats(self) -> dict:
        """GET /api/analytics/impulse-stats"""
        return await self._get("/api/analytics/impulse-stats")

    # ------------------------------------------------------------------
    # Agents (multi-agent management)
    # ------------------------------------------------------------------

    async def list_agents(self) -> dict:
        """GET /api/agents"""
        return await self._get("/api/agents")

    async def create_agent(
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
        return await self._post("/api/agents", json=body)

    async def get_agent_state(self, agent_id: str) -> dict:
        """GET /api/agents/{id}/state"""
        return await self._get(f"/api/agents/{agent_id}/state")

    async def delete_agent(self, agent_id: str) -> dict:
        """DELETE /api/agents/{id}"""
        return await self._delete(f"/api/agents/{agent_id}")

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    async def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        chat_id: Optional[int] = None,
    ) -> dict:
        """GET /api/conversations"""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if chat_id is not None:
            params["chat_id"] = chat_id
        return await self._get("/api/conversations", **params)

    async def conversation_stats(self) -> dict:
        """GET /api/conversations/stats"""
        return await self._get("/api/conversations/stats")

    async def clear_conversations(self, before: Optional[float] = None) -> dict:
        """DELETE /api/conversations"""
        params: Dict[str, Any] = {}
        if before is not None:
            params["before"] = before
        return await self._request("DELETE", "/api/conversations", params=params)

    # ------------------------------------------------------------------
    # Models / Providers
    # ------------------------------------------------------------------

    async def list_models(self) -> dict:
        """GET /api/models"""
        return await self._get("/api/models")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "AsyncHumaneClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
