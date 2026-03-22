"""Goal Templates — pre-built goal configurations for common workflows."""

from __future__ import annotations

import re
from typing import Any, Dict, List


GOAL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "sales_pipeline": {
        "description": "Close {client} deal",
        "milestones": [
            "Initial contact",
            "Discovery call",
            "Proposal sent",
            "Negotiation",
            "Close",
        ],
        "expected_value": 1.0,
    },
    "project_launch": {
        "description": "Launch {project}",
        "milestones": [
            "Requirements",
            "Design",
            "Build",
            "Test",
            "Deploy",
            "Post-launch review",
        ],
        "expected_value": 0.8,
    },
    "hiring": {
        "description": "Hire {role}",
        "milestones": [
            "Write JD",
            "Source candidates",
            "Screen",
            "Interview",
            "Offer",
            "Onboard",
        ],
        "expected_value": 0.7,
    },
    "content_campaign": {
        "description": "Run {campaign} campaign",
        "milestones": [
            "Strategy",
            "Content creation",
            "Review",
            "Publish",
            "Promote",
            "Analyze results",
        ],
        "expected_value": 0.6,
    },
    "client_onboarding": {
        "description": "Onboard {client}",
        "milestones": [
            "Kickoff",
            "Setup",
            "Training",
            "First deliverable",
            "30-day check-in",
        ],
        "expected_value": 0.9,
    },
    "personal_growth": {
        "description": "{skill} improvement",
        "milestones": [
            "Define learning path",
            "Complete course/reading",
            "Practice exercises",
            "Apply in project",
            "Review progress",
        ],
        "expected_value": 0.5,
    },
}


def _extract_variables(template_desc: str) -> List[str]:
    """Return placeholder names from a description template string."""
    return re.findall(r"\{(\w+)\}", template_desc)


def instantiate_template(
    template_name: str,
    variables: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Instantiate a goal template into goal parameters ready for registration.

    Returns a dict with keys: description, expected_value, milestones_total.
    """
    if template_name not in GOAL_TEMPLATES:
        raise KeyError(f"Unknown template: {template_name}")

    variables = variables or {}
    tpl = GOAL_TEMPLATES[template_name]

    description = tpl["description"]
    for var_name in _extract_variables(description):
        value = variables.get(var_name, var_name)
        description = description.replace(f"{{{var_name}}}", value)

    return {
        "description": description,
        "expected_value": tpl["expected_value"],
        "milestones_total": len(tpl["milestones"]),
    }


def list_templates() -> List[Dict[str, Any]]:
    """Return a summary list of all available templates."""
    result = []
    for name, tpl in GOAL_TEMPLATES.items():
        result.append({
            "name": name,
            "description": tpl["description"],
            "milestones": tpl["milestones"],
            "milestone_count": len(tpl["milestones"]),
            "expected_value": tpl["expected_value"],
            "variables": _extract_variables(tpl["description"]),
        })
    return result
