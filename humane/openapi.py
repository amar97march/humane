"""OpenAPI 3.1 specification for the Humane API."""

from __future__ import annotations


def generate_openapi_spec() -> dict:
    """Return a complete OpenAPI 3.1 specification covering all Humane API endpoints."""

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Humane API",
            "description": (
                "REST API for the Humane autonomous-agent framework. "
                "Manage agent state, entities, goals, memories, values, "
                "conversations, webhooks, analytics, and more."
            ),
            "version": "1.0.0",
        },
        "servers": [{"url": "/", "description": "Current host"}],
        "tags": [
            {"name": "State", "description": "Agent state snapshot"},
            {"name": "Queue", "description": "Hold-queue management (approve / reject pending actions)"},
            {"name": "Entities", "description": "Relational entity CRUD and interaction logging"},
            {"name": "Goals", "description": "Goal lifecycle management"},
            {"name": "Memories", "description": "Memory storage with decay and search"},
            {"name": "Events", "description": "Event log queries"},
            {"name": "Values", "description": "Value statements that govern agent behaviour"},
            {"name": "Config", "description": "Runtime configuration read / write"},
            {"name": "Analytics", "description": "Historical analytics and statistics"},
            {"name": "Conversations", "description": "Conversation history and statistics"},
            {"name": "Webhooks", "description": "Outbound webhook registration and testing"},
            {"name": "Agents", "description": "Multi-agent management"},
            {"name": "Models", "description": "LLM provider and model information"},
            {"name": "Import/Export", "description": "Bulk import and export of agent data"},
            {"name": "Voice", "description": "Voice transcription"},
            {"name": "Evaluate", "description": "Action evaluation through the gate pipeline"},
            {"name": "Impulse", "description": "Fire impulse events"},
            {"name": "Digest", "description": "Daily digest generation"},
            {"name": "Schedule", "description": "Smart scheduling for entity interactions"},
            {"name": "Insights", "description": "Agent behavioural insights"},
            {"name": "Plugins", "description": "Plugin management"},
            {"name": "Audit", "description": "Audit log queries"},
            {"name": "Auth", "description": "API key authentication management"},
            {"name": "Retention", "description": "Data retention policies"},
            {"name": "GDPR", "description": "GDPR data export and erasure"},
            {"name": "Goal Templates", "description": "Pre-defined goal templates"},
            {"name": "Agent Communication", "description": "Agent-to-agent messaging and resource sharing"},
            {"name": "A/B Testing", "description": "A/B test management for threshold experimentation"},
            {"name": "Feedback", "description": "Feedback collection, statistics, and auto-tuning"},
            {"name": "Simulation", "description": "Conversation simulation and branching"},
            {"name": "WhatsApp", "description": "WhatsApp webhook integration"},
        ],
        "paths": {
            # ── State ──────────────────────────────────────────────
            "/api/state": {
                "get": {
                    "tags": ["State"],
                    "summary": "Get current agent state",
                    "description": "Returns the full state snapshot including energy, mood, fatigue, decision quality multiplier, and preferred task type.",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "State snapshot",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "state": {"type": "object", "description": "Full state snapshot dict"},
                                    "dqm": {"type": "number", "description": "Decision quality multiplier"},
                                    "preferred_task_type": {"type": "string"},
                                    "agent_name": {"type": "string"},
                                },
                            }}},
                        },
                    },
                },
            },

            # ── Queue ──────────────────────────────────────────────
            "/api/queue": {
                "get": {
                    "tags": ["Queue"],
                    "summary": "List hold-queue items",
                    "description": "Returns all items currently in the hold queue awaiting approval or rejection.",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Queue listing",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "items": {"type": "array", "items": {"$ref": "#/components/schemas/HoldItem"}},
                                    "count": {"type": "integer"},
                                },
                            }}},
                        },
                    },
                },
            },
            "/api/queue/{id}/approve": {
                "post": {
                    "tags": ["Queue"],
                    "summary": "Approve a held action",
                    "parameters": [_path_id("Hold item ID"), _agent_id_param()],
                    "responses": {
                        "200": _ok_response("Action approved"),
                        "400": _error_response(),
                    },
                },
            },
            "/api/queue/{id}/reject": {
                "post": {
                    "tags": ["Queue"],
                    "summary": "Reject a held action",
                    "parameters": [_path_id("Hold item ID"), _agent_id_param()],
                    "responses": {
                        "200": _ok_response("Action rejected"),
                        "400": _error_response(),
                    },
                },
            },

            # ── Entities ───────────────────────────────────────────
            "/api/entities": {
                "get": {
                    "tags": ["Entities"],
                    "summary": "List all entities",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Entity list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "entities": {"type": "array", "items": {"$ref": "#/components/schemas/Entity"}},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Entities"],
                    "summary": "Create a new entity",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string", "description": "Entity name"},
                                "entity_type": {
                                    "type": "string",
                                    "enum": ["person", "organization", "place", "concept", "unknown"],
                                    "default": "unknown",
                                },
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Entity created",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "entity_id": {"type": "string"},
                                    "name": {"type": "string"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/entities/{id}": {
                "get": {
                    "tags": ["Entities"],
                    "summary": "Get entity context",
                    "description": "Returns full relational context for a single entity.",
                    "parameters": [_path_id("Entity ID"), _agent_id_param()],
                    "responses": {
                        "200": {"description": "Entity context object", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "404": _error_response("Entity not found"),
                    },
                },
            },
            "/api/entities/{id}/interact": {
                "post": {
                    "tags": ["Entities"],
                    "summary": "Log an interaction with an entity",
                    "parameters": [_path_id("Entity ID"), _agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "sentiment": {"type": "number", "default": 0.0, "description": "Sentiment score (-1.0 to 1.0)"},
                                "summary": {"type": "string", "default": "", "description": "Interaction summary"},
                            },
                        }}},
                    },
                    "responses": {"200": _ok_response("Interaction logged")},
                },
            },
            "/api/entities/{id}/timeline": {
                "get": {
                    "tags": ["Entities"],
                    "summary": "Get entity interaction timeline",
                    "description": "Returns the interaction history and statistics for an entity.",
                    "parameters": [
                        _path_id("Entity ID"),
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 100}, "description": "Max timeline entries"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Timeline with stats",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "entity_id": {"type": "string"},
                                    "entity_name": {"type": "string"},
                                    "timeline": {"type": "array", "items": {"type": "object"}},
                                    "stats": {"type": "object"},
                                },
                            }}},
                        },
                        "404": _error_response("Entity not found"),
                    },
                },
            },

            # ── Goals ──────────────────────────────────────────────
            "/api/goals": {
                "get": {
                    "tags": ["Goals"],
                    "summary": "List goals",
                    "parameters": [
                        {"name": "status", "in": "query", "schema": {"type": "string"}, "description": "Filter by status (e.g. 'active')"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Goal list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "goals": {"type": "array", "items": {"$ref": "#/components/schemas/Goal"}},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Goals"],
                    "summary": "Register a new goal",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["description"],
                            "properties": {
                                "description": {"type": "string"},
                                "expected_value": {"type": "number", "default": 1.0},
                                "milestones_total": {"type": "integer", "default": 0},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Goal created",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/goals/{id}": {
                "patch": {
                    "tags": ["Goals"],
                    "summary": "Update goal progress or perform actions",
                    "parameters": [_path_id("Goal ID"), _agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "milestones_completed": {"type": "integer"},
                                "velocity": {"type": "number"},
                                "action": {"type": "string", "enum": ["abandon", "pause", "resume"]},
                                "resume_days": {"type": "integer", "default": 7},
                            },
                        }}},
                    },
                    "responses": {
                        "200": _ok_response("Goal updated"),
                        "400": _error_response(),
                    },
                },
            },

            # ── Memories ───────────────────────────────────────────
            "/api/memories": {
                "get": {
                    "tags": ["Memories"],
                    "summary": "List or search memories",
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Search query"},
                        {"name": "archived", "in": "query", "schema": {"type": "string", "enum": ["true", "false"]}, "description": "Include archived memories"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Memory list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "memories": {"type": "array", "items": {"$ref": "#/components/schemas/Memory"}},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Memories"],
                    "summary": "Add a new memory",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["content"],
                            "properties": {
                                "content": {"type": "string"},
                                "memory_type": {"type": "string", "enum": ["episodic", "semantic", "procedural"], "default": "episodic"},
                                "pinned": {"type": "boolean", "default": False},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Memory created",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {"id": {"type": "string"}},
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },

            # ── Events ─────────────────────────────────────────────
            "/api/events": {
                "get": {
                    "tags": ["Events"],
                    "summary": "List recent events",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}, "description": "Max events to return"},
                        {"name": "engine", "in": "query", "schema": {"type": "string"}, "description": "Filter by engine name"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Event list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "events": {"type": "array", "items": {"type": "object"}},
                                },
                            }}},
                        },
                    },
                },
            },

            # ── Evaluate ───────────────────────────────────────────
            "/api/evaluate": {
                "post": {
                    "tags": ["Evaluate"],
                    "summary": "Evaluate a proposed action",
                    "description": "Runs a proposed action through the full gate pipeline and returns the verdict.",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "action_type": {"type": "string", "default": "test"},
                                "payload": {"type": "object", "default": {}},
                                "confidence": {"type": "number", "default": 0.7},
                                "rationale": {"type": "string", "default": "API evaluation"},
                                "source": {"type": "string", "default": "api"},
                                "target_entity": {"type": "string", "nullable": True},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {
                            "description": "Evaluation result",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "verdict": {"type": "string"},
                                    "gate_results": {"type": "array", "items": {
                                        "type": "object",
                                        "properties": {
                                            "engine": {"type": "string"},
                                            "verdict": {"type": "string"},
                                            "score": {"type": "number"},
                                            "reason": {"type": "string"},
                                        },
                                    }},
                                    "audit_trail": {"type": "array", "items": {"type": "string"}},
                                    "hold_item": {"type": "object", "nullable": True},
                                },
                            }}},
                        },
                    },
                },
            },

            # ── Impulse ────────────────────────────────────────────
            "/api/impulse/fire": {
                "post": {
                    "tags": ["Impulse"],
                    "summary": "Fire an impulse event",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "description": "Impulse type (e.g. idle_discovery)", "default": "idle_discovery"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {
                            "description": "Impulse fired",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "type": {"type": "string"},
                                    "payload": {"type": "object"},
                                    "state_snapshot": {"type": "object"},
                                },
                            }}},
                        },
                        "400": _error_response("Invalid impulse type"),
                    },
                },
            },

            # ── Config ─────────────────────────────────────────────
            "/api/config": {
                "get": {
                    "tags": ["Config"],
                    "summary": "Get current configuration",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Full config object", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
                "patch": {
                    "tags": ["Config"],
                    "summary": "Update configuration fields",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "description": "Key-value pairs of config fields to update",
                            "additionalProperties": True,
                        }}},
                    },
                    "responses": {
                        "200": {
                            "description": "Updated fields",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "updated": {"type": "array", "items": {"type": "string"}},
                                },
                            }}},
                        },
                        "400": _error_response("No valid config fields"),
                    },
                },
            },

            # ── Values ─────────────────────────────────────────────
            "/api/values": {
                "get": {
                    "tags": ["Values"],
                    "summary": "List value statements",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Value list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "values": {"type": "array", "items": {"$ref": "#/components/schemas/ValueStatement"}},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Values"],
                    "summary": "Add a value statement",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["description"],
                            "properties": {
                                "description": {"type": "string"},
                                "behavioral_pattern": {"type": "string", "default": ""},
                                "violation_examples": {"type": "array", "items": {"type": "string"}, "default": []},
                                "honoring_examples": {"type": "array", "items": {"type": "string"}, "default": []},
                                "severity": {"type": "string", "enum": ["SOFT", "HARD"], "default": "SOFT"},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Value created",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {"id": {"type": "string"}},
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },

            # ── Webhooks ───────────────────────────────────────────
            "/api/webhooks": {
                "get": {
                    "tags": ["Webhooks"],
                    "summary": "List registered webhooks",
                    "responses": {
                        "200": {
                            "description": "Webhook list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "webhooks": {"type": "array", "items": {"$ref": "#/components/schemas/Webhook"}},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Webhooks"],
                    "summary": "Register a new webhook",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["url", "events"],
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "events": {"type": "array", "items": {"type": "string"}, "description": "Event types to subscribe to"},
                                "secret": {"type": "string", "nullable": True, "description": "Optional HMAC secret"},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Webhook registered",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "url": {"type": "string"},
                                    "events": {"type": "array", "items": {"type": "string"}},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/webhooks/{id}": {
                "delete": {
                    "tags": ["Webhooks"],
                    "summary": "Unregister a webhook",
                    "parameters": [_path_id("Webhook ID")],
                    "responses": {"200": _ok_response("Webhook removed")},
                },
            },
            "/api/webhooks/test": {
                "post": {
                    "tags": ["Webhooks"],
                    "summary": "Send a test webhook delivery",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["url"],
                            "properties": {
                                "url": {"type": "string", "format": "uri"},
                                "secret": {"type": "string", "nullable": True},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Test result", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },

            # ── Import / Export ────────────────────────────────────
            "/api/export": {
                "get": {
                    "tags": ["Import/Export"],
                    "summary": "Export agent data as JSON",
                    "description": "Returns the full data bundle (entities, goals, memories, values, events, config).",
                    "responses": {
                        "200": {"description": "Export bundle", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/export/download": {
                "get": {
                    "tags": ["Import/Export"],
                    "summary": "Download export as a JSON file",
                    "description": "Returns the export bundle as a downloadable .json file attachment.",
                    "responses": {
                        "200": {
                            "description": "Downloadable JSON file",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                            "headers": {
                                "Content-Disposition": {"schema": {"type": "string"}},
                            },
                        },
                    },
                },
            },
            "/api/import": {
                "post": {
                    "tags": ["Import/Export"],
                    "summary": "Import agent data from a JSON bundle",
                    "parameters": [
                        {"name": "mode", "in": "query", "schema": {"type": "string", "enum": ["replace", "merge"], "default": "merge"}, "description": "Import mode"},
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object", "description": "Export bundle JSON"}}},
                    },
                    "responses": {
                        "200": {"description": "Import result", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "207": {"description": "Partial import with errors", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response("Invalid JSON body"),
                    },
                },
            },

            # ── Conversations ──────────────────────────────────────
            "/api/conversations": {
                "get": {
                    "tags": ["Conversations"],
                    "summary": "List conversations",
                    "parameters": [
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                        {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}},
                        {"name": "chat_id", "in": "query", "schema": {"type": "integer"}, "description": "Filter by chat ID"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Paginated conversation list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "conversations": {"type": "array", "items": {"$ref": "#/components/schemas/Conversation"}},
                                    "total": {"type": "integer"},
                                    "limit": {"type": "integer"},
                                    "offset": {"type": "integer"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
                "delete": {
                    "tags": ["Conversations"],
                    "summary": "Clear conversation history",
                    "parameters": [
                        {"name": "before", "in": "query", "schema": {"type": "number"}, "description": "Delete conversations before this Unix timestamp"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Conversations deleted",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "deleted": {"type": "integer"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/conversations/stats": {
                "get": {
                    "tags": ["Conversations"],
                    "summary": "Get conversation statistics",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Conversation statistics",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "total_count": {"type": "integer"},
                                    "avg_sentiment": {"type": "number"},
                                    "avg_messages_per_day": {"type": "number"},
                                    "messages_by_role": {"type": "object", "additionalProperties": {"type": "integer"}},
                                    "daily_counts": {"type": "array", "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {"type": "string"},
                                            "count": {"type": "integer"},
                                        },
                                    }},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },

            # ── Models ─────────────────────────────────────────────
            "/api/models": {
                "get": {
                    "tags": ["Models"],
                    "summary": "List LLM providers and their status",
                    "responses": {
                        "200": {
                            "description": "Provider list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "active_provider": {"type": "string"},
                                    "active_model": {"type": "string"},
                                    "providers": {"type": "array", "items": {
                                        "type": "object",
                                        "properties": {
                                            "provider": {"type": "string"},
                                            "default_model": {"type": "string"},
                                            "base_url": {"type": "string"},
                                            "sdk_installed": {"type": "boolean"},
                                            "sdk_package": {"type": "string"},
                                            "api_key_set": {"type": "boolean"},
                                            "ready": {"type": "boolean"},
                                            "active": {"type": "boolean"},
                                            "error": {"type": "string", "nullable": True},
                                        },
                                    }},
                                },
                            }}},
                        },
                    },
                },
            },

            # ── Analytics ──────────────────────────────────────────
            "/api/analytics/state-history": {
                "get": {
                    "tags": ["Analytics"],
                    "summary": "Get state history snapshots",
                    "parameters": [
                        {"name": "hours", "in": "query", "schema": {"type": "integer", "default": 24}, "description": "Lookback window in hours"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "State snapshots over time",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "snapshots": {"type": "array", "items": {
                                        "type": "object",
                                        "properties": {
                                            "timestamp": {"type": "number"},
                                            "energy": {"type": "number", "nullable": True},
                                            "mood": {"type": "number", "nullable": True},
                                            "fatigue": {"type": "number", "nullable": True},
                                            "boredom": {"type": "number", "nullable": True},
                                            "social_load": {"type": "number", "nullable": True},
                                            "focus": {"type": "number", "nullable": True},
                                        },
                                    }},
                                    "hours": {"type": "integer"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/analytics/engine-stats": {
                "get": {
                    "tags": ["Analytics"],
                    "summary": "Get gate engine evaluation statistics",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Engine verdict counts keyed by engine name",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "properties": {
                                        "proceed": {"type": "integer"},
                                        "hold": {"type": "integer"},
                                        "defer": {"type": "integer"},
                                        "total": {"type": "integer"},
                                    },
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/analytics/entity-interactions": {
                "get": {
                    "tags": ["Analytics"],
                    "summary": "Get entity interaction statistics",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Aggregated interaction stats per entity",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "entities": {"type": "array", "items": {
                                        "type": "object",
                                        "properties": {
                                            "entity_id": {"type": "string"},
                                            "name": {"type": "string", "nullable": True},
                                            "interaction_count": {"type": "integer"},
                                            "avg_sentiment": {"type": "number"},
                                            "last_interaction_at": {"type": "number", "nullable": True},
                                        },
                                    }},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/analytics/approval-rate": {
                "get": {
                    "tags": ["Analytics"],
                    "summary": "Get hold approval/rejection rates",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Approval rate statistics",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "total": {"type": "integer"},
                                    "approved": {"type": "integer"},
                                    "rejected": {"type": "integer"},
                                    "approval_rate": {"type": "number"},
                                    "by_engine": {"type": "object", "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "approved": {"type": "integer"},
                                            "rejected": {"type": "integer"},
                                            "rate": {"type": "number"},
                                        },
                                    }},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },
            "/api/analytics/impulse-stats": {
                "get": {
                    "tags": ["Analytics"],
                    "summary": "Get impulse event statistics",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Impulse statistics",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "total": {"type": "integer"},
                                    "by_type": {"type": "object", "additionalProperties": {"type": "integer"}},
                                    "avg_per_day": {"type": "number"},
                                },
                            }}},
                        },
                        "400": _error_response(),
                    },
                },
            },

            # ── Agents (multi-agent) ───────────────────────────────
            "/api/agents": {
                "get": {
                    "tags": ["Agents"],
                    "summary": "List all agents",
                    "responses": {
                        "200": {
                            "description": "Agent list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "agents": {"type": "array", "items": {"type": "object"}},
                                    "multi_agent": {"type": "boolean"},
                                },
                            }}},
                        },
                    },
                },
                "post": {
                    "tags": ["Agents"],
                    "summary": "Create a new agent",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "personality": {"type": "string"},
                                "llm_provider": {"type": "string"},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {
                            "description": "Agent created",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                },
                            }}},
                        },
                        "400": _error_response("Multi-agent mode not enabled"),
                        "409": _error_response("Agent already exists"),
                    },
                },
            },
            "/api/agents/{id}/state": {
                "get": {
                    "tags": ["Agents"],
                    "summary": "Get state for a specific agent",
                    "parameters": [_path_id("Agent ID")],
                    "responses": {
                        "200": {
                            "description": "Agent state",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "state": {"type": "object"},
                                    "dqm": {"type": "number"},
                                    "preferred_task_type": {"type": "string"},
                                },
                            }}},
                        },
                        "400": _error_response("Multi-agent mode not enabled"),
                        "404": _error_response("Agent not found"),
                    },
                },
            },
            "/api/agents/{id}": {
                "delete": {
                    "tags": ["Agents"],
                    "summary": "Delete an agent",
                    "parameters": [_path_id("Agent ID")],
                    "responses": {
                        "200": _ok_response("Agent deleted"),
                        "400": _error_response("Multi-agent mode not enabled"),
                        "404": _error_response("Agent not found"),
                    },
                },
            },

            # ── Voice ──────────────────────────────────────────────
            "/api/voice/transcribe": {
                "post": {
                    "tags": ["Voice"],
                    "summary": "Transcribe an audio file to text",
                    "description": "Accepts a multipart form upload with an audio file. Supports ogg, mp3, wav, m4a, and webm formats.",
                    "requestBody": {
                        "required": True,
                        "content": {"multipart/form-data": {"schema": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {
                                "file": {"type": "string", "format": "binary", "description": "Audio file"},
                                "format": {"type": "string", "description": "Audio format override (ogg, mp3, wav, m4a, webm)"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {
                            "description": "Transcription result",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                            }}},
                        },
                        "400": _error_response("Voice disabled or no file"),
                        "500": _error_response("Transcription failed"),
                    },
                },
            },

            # ── Digest ─────────────────────────────────────────────
            "/api/digest": {
                "get": {
                    "tags": ["Digest"],
                    "summary": "Get daily digest as JSON",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Digest data", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/digest/preview": {
                "get": {
                    "tags": ["Digest"],
                    "summary": "Get daily digest as formatted HTML",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "HTML preview", "content": {"text/html": {"schema": {"type": "string"}}}},
                    },
                },
            },

            # ── WhatsApp ───────────────────────────────────────────
            "/webhook/whatsapp": {
                "get": {
                    "tags": ["WhatsApp"],
                    "summary": "WhatsApp webhook verification",
                    "description": "Meta webhook verification challenge endpoint.",
                    "parameters": [
                        {"name": "hub.mode", "in": "query", "schema": {"type": "string"}},
                        {"name": "hub.verify_token", "in": "query", "schema": {"type": "string"}},
                        {"name": "hub.challenge", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {"description": "Challenge response"},
                        "404": {"description": "WhatsApp bot not configured"},
                    },
                },
                "post": {
                    "tags": ["WhatsApp"],
                    "summary": "Incoming WhatsApp message webhook",
                    "description": "Receives incoming messages from the WhatsApp Business API.",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {
                        "200": {"description": "Message processed"},
                        "404": {"description": "WhatsApp bot not configured"},
                    },
                },
            },

            # ── Goal Templates ─────────────────────────────────────
            "/api/goal-templates": {
                "get": {
                    "tags": ["Goal Templates"],
                    "summary": "List available goal templates",
                    "responses": {
                        "200": {
                            "description": "Template list",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        },
                    },
                },
            },
            "/api/goal-templates/instantiate": {
                "post": {
                    "tags": ["Goal Templates"],
                    "summary": "Instantiate a goal from a template",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "template_id": {"type": "string"},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {"description": "Goal created from template", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },

            # ── Conversations Categories ───────────────────────────
            "/api/conversations/categories": {
                "get": {
                    "tags": ["Conversations"],
                    "summary": "Get conversation category breakdown",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Category statistics", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },

            # ── Plugins ────────────────────────────────────────────
            "/api/plugins": {
                "get": {
                    "tags": ["Plugins"],
                    "summary": "List all loaded plugins",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {
                            "description": "Plugin list",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "plugins": {"type": "array", "items": {"type": "object"}},
                                },
                            }}},
                        },
                    },
                },
            },
            "/api/plugins/reload": {
                "post": {
                    "tags": ["Plugins"],
                    "summary": "Reload all plugins from the plugins directory",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Plugins reloaded", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/plugins/{name}/toggle": {
                "post": {
                    "tags": ["Plugins"],
                    "summary": "Enable or disable a plugin",
                    "parameters": [
                        {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Plugin name"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {
                            "description": "Plugin toggled",
                            "content": {"application/json": {"schema": {
                                "type": "object",
                                "properties": {
                                    "ok": {"type": "boolean"},
                                    "name": {"type": "string"},
                                    "active": {"type": "boolean"},
                                },
                            }}},
                        },
                        "404": _error_response("Plugin not found"),
                    },
                },
            },

            # ── Schedule ───────────────────────────────────────────
            "/api/schedule": {
                "get": {
                    "tags": ["Schedule"],
                    "summary": "Get smart schedule for all entities",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Schedule data", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/schedule/{entity_id}": {
                "get": {
                    "tags": ["Schedule"],
                    "summary": "Get smart schedule for a specific entity",
                    "parameters": [
                        {"name": "entity_id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Entity ID"},
                        _agent_id_param(),
                    ],
                    "responses": {
                        "200": {"description": "Entity schedule", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },

            # ── Insights ───────────────────────────────────────────
            "/api/insights": {
                "get": {
                    "tags": ["Insights"],
                    "summary": "Get agent behavioural insights",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Insight data", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },

            # ── Audit ──────────────────────────────────────────────
            "/api/audit": {
                "get": {
                    "tags": ["Audit"],
                    "summary": "Get audit log entries",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Audit entries", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },

            # ── Auth / API Keys ────────────────────────────────────
            "/api/auth/keys": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "List API keys",
                    "responses": {
                        "200": {"description": "API key list", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
                "post": {
                    "tags": ["Auth"],
                    "summary": "Generate a new API key",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Key label"},
                            },
                        }}},
                    },
                    "responses": {
                        "201": {"description": "API key created", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/auth/keys/{id}": {
                "delete": {
                    "tags": ["Auth"],
                    "summary": "Revoke an API key",
                    "parameters": [_path_id("API key ID")],
                    "responses": {
                        "200": _ok_response("Key revoked"),
                        "404": _error_response("Key not found"),
                    },
                },
            },

            # ── Retention ──────────────────────────────────────────
            "/api/retention": {
                "get": {
                    "tags": ["Retention"],
                    "summary": "Get current data retention policy",
                    "responses": {
                        "200": {"description": "Retention policy", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/retention/preview": {
                "post": {
                    "tags": ["Retention"],
                    "summary": "Preview data that would be removed by a retention policy",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {
                        "200": {"description": "Preview of affected data", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/retention/apply": {
                "post": {
                    "tags": ["Retention"],
                    "summary": "Apply a data retention policy",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {
                        "200": {"description": "Retention applied", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },

            # ── GDPR ──────────────────────────────────────────────
            "/api/gdpr/export": {
                "get": {
                    "tags": ["GDPR"],
                    "summary": "Export all personal data (GDPR data portability)",
                    "responses": {
                        "200": {"description": "GDPR export bundle", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/gdpr/export/download": {
                "get": {
                    "tags": ["GDPR"],
                    "summary": "Download GDPR export as a file",
                    "responses": {
                        "200": {
                            "description": "Downloadable GDPR export",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        },
                    },
                },
            },
            "/api/gdpr/export/{entity_id}": {
                "get": {
                    "tags": ["GDPR"],
                    "summary": "Export data for a specific entity",
                    "parameters": [
                        {"name": "entity_id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Entity ID"},
                    ],
                    "responses": {
                        "200": {"description": "Entity data export", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/gdpr/erase/{entity_id}": {
                "delete": {
                    "tags": ["GDPR"],
                    "summary": "Erase all data for a specific entity (right to be forgotten)",
                    "parameters": [
                        {"name": "entity_id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Entity ID to erase"},
                    ],
                    "responses": {
                        "200": _ok_response("Entity data erased"),
                        "404": _error_response("Entity not found"),
                    },
                },
            },

            # ── Agent Communication ────────────────────────────────
            "/api/agents/{id}/inbox": {
                "get": {
                    "tags": ["Agent Communication"],
                    "summary": "Get messages in an agent's inbox",
                    "parameters": [_path_id("Agent ID")],
                    "responses": {
                        "200": {"description": "Inbox messages", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/agents/{id}/send": {
                "post": {
                    "tags": ["Agent Communication"],
                    "summary": "Send a message to an agent",
                    "parameters": [_path_id("Target agent ID")],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "from_agent_id": {"type": "string"},
                                "message_type": {"type": "string"},
                                "payload": {"type": "object"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Message sent", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/agents/broadcast": {
                "post": {
                    "tags": ["Agent Communication"],
                    "summary": "Broadcast a message to all agents",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "from_agent_id": {"type": "string"},
                                "message_type": {"type": "string"},
                                "payload": {"type": "object"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Broadcast result", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/agents/{id}/share-entity": {
                "post": {
                    "tags": ["Agent Communication"],
                    "summary": "Share an entity with another agent",
                    "parameters": [_path_id("Target agent ID")],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "from_agent_id": {"type": "string"},
                                "entity_id": {"type": "string"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Entity shared", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/agents/{id}/share-goal": {
                "post": {
                    "tags": ["Agent Communication"],
                    "summary": "Share a goal with another agent",
                    "parameters": [_path_id("Target agent ID")],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "from_agent_id": {"type": "string"},
                                "goal_id": {"type": "string"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Goal shared", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },

            # ── A/B Testing ────────────────────────────────────────
            "/api/ab-tests": {
                "get": {
                    "tags": ["A/B Testing"],
                    "summary": "List all A/B tests",
                    "responses": {
                        "200": {"description": "Test list", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/ab-tests/{id}/results": {
                "get": {
                    "tags": ["A/B Testing"],
                    "summary": "Get results for an A/B test",
                    "parameters": [_path_id("Test ID")],
                    "responses": {
                        "200": {"description": "Test results", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "404": _error_response("Test not found"),
                    },
                },
            },
            "/api/ab-tests/{id}/end": {
                "post": {
                    "tags": ["A/B Testing"],
                    "summary": "End an A/B test and apply the winner",
                    "parameters": [_path_id("Test ID")],
                    "responses": {
                        "200": {"description": "Test ended", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "404": _error_response("Test not found"),
                    },
                },
            },

            # ── Feedback ───────────────────────────────────────────
            "/api/feedback/stats": {
                "get": {
                    "tags": ["Feedback"],
                    "summary": "Get feedback statistics",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Feedback stats", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/feedback/export": {
                "get": {
                    "tags": ["Feedback"],
                    "summary": "Export feedback data",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Feedback export", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/feedback/recommendations": {
                "get": {
                    "tags": ["Feedback"],
                    "summary": "Get threshold adjustment recommendations",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Recommendations", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },
            "/api/feedback/auto-tune": {
                "post": {
                    "tags": ["Feedback"],
                    "summary": "Auto-tune thresholds based on feedback",
                    "parameters": [_agent_id_param()],
                    "responses": {
                        "200": {"description": "Tuning result", "content": {"application/json": {"schema": {"type": "object"}}}},
                    },
                },
            },

            # ── Simulation ─────────────────────────────────────────
            "/api/simulate": {
                "post": {
                    "tags": ["Simulation"],
                    "summary": "Simulate a conversation message",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"},
                                "chat_id": {"type": "integer"},
                            },
                        }}},
                    },
                    "responses": {
                        "200": {"description": "Simulation result", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
            "/api/simulate/compare": {
                "post": {
                    "tags": ["Simulation"],
                    "summary": "Compare simulation results across different configurations",
                    "parameters": [_agent_id_param()],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {
                        "200": {"description": "Comparison result", "content": {"application/json": {"schema": {"type": "object"}}}},
                        "400": _error_response(),
                    },
                },
            },
        },
        "components": {
            "schemas": {
                "HoldItem": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "action_type": {"type": "string"},
                        "payload": {"type": "object"},
                        "confidence": {"type": "number"},
                        "adjusted_confidence": {"type": "number"},
                        "hold_reason": {"type": "string"},
                        "hold_source": {"type": "string"},
                        "created_at": {"type": "number"},
                    },
                },
                "Entity": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "name": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "sentiment_score": {"type": "number"},
                        "grudge_score": {"type": "number"},
                        "trust_level": {"type": "string"},
                        "relationship_health": {"type": "string"},
                        "disclosure_threshold": {"type": "number"},
                        "interaction_count": {"type": "integer"},
                        "last_interaction_at": {"type": "number", "nullable": True},
                    },
                },
                "Goal": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "expected_value": {"type": "number"},
                        "remaining_effort": {"type": "number"},
                        "progress_velocity": {"type": "number"},
                        "milestones_total": {"type": "integer"},
                        "milestones_completed": {"type": "integer"},
                        "roi": {"type": "number"},
                        "status": {"type": "string"},
                        "created_at": {"type": "number"},
                    },
                },
                "Memory": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "memory_type": {"type": "string"},
                        "content": {"type": "string"},
                        "relevance_score": {"type": "number"},
                        "access_count": {"type": "integer"},
                        "pinned": {"type": "boolean"},
                        "archived": {"type": "boolean"},
                        "created_at": {"type": "number"},
                    },
                },
                "ValueStatement": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "behavioral_pattern": {"type": "string"},
                        "violation_examples": {"type": "array", "items": {"type": "string"}},
                        "honoring_examples": {"type": "array", "items": {"type": "string"}},
                        "severity": {"type": "string", "enum": ["SOFT", "HARD"]},
                    },
                },
                "Webhook": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "url": {"type": "string"},
                        "events": {"type": "array", "items": {"type": "string"}},
                        "has_secret": {"type": "boolean"},
                        "created_at": {"type": "number"},
                    },
                },
                "Conversation": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "chat_id": {"type": "integer"},
                        "user_id": {"type": "string"},
                        "role": {"type": "string"},
                        "content": {"type": "string"},
                        "sentiment": {"type": "number", "nullable": True},
                        "created_at": {"type": "number"},
                    },
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                    },
                },
            },
        },
    }


# ── Helper functions for building spec fragments ──────────────────

def _agent_id_param() -> dict:
    return {
        "name": "agent_id",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
        "description": "Target a specific agent in multi-agent mode",
    }


def _path_id(description: str = "Resource ID") -> dict:
    return {
        "name": "id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "description": description,
    }


def _ok_response(description: str = "Success") -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
        }}},
    }


def _error_response(description: str = "Error") -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }
