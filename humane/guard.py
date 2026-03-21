"""The @guard decorator — simplest integration point for Humane."""

from __future__ import annotations
import functools
from typing import Optional

from humane.core.models import ProposedAction, Verdict
from humane.conductor import Conductor

_default_conductor: Optional[Conductor] = None


def get_conductor() -> Conductor:
    global _default_conductor
    if _default_conductor is None:
        _default_conductor = Conductor()
    return _default_conductor


def set_conductor(conductor: Conductor):
    global _default_conductor
    _default_conductor = conductor


def guard(action_type: str = "default", confidence: float = 0.7, target_entity: Optional[str] = None):
    """Decorator that gates a function through the full Humane decision stack.

    Usage:
        @guard(action_type="send_message", confidence=0.8)
        def send_followup(contact_id, message):
            send_email(contact_id, message)

    The decorated function only executes if all 10 gates return PROCEED.
    If any gate returns HOLD or DEFER, the action enters the dashboard queue.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            conductor = get_conductor()

            payload = {
                "function": func.__name__,
                "args": [str(a) for a in args],
                "kwargs": {k: str(v) for k, v in kwargs.items()},
            }

            action = ProposedAction(
                action_type=action_type,
                payload=payload,
                confidence=confidence,
                rationale=f"Guarded call to {func.__name__}",
                source="user",
                target_entity=target_entity or kwargs.get("target_entity"),
            )

            result = conductor.evaluate(action)

            if result.final_verdict == Verdict.PROCEED:
                return func(*args, **kwargs)

            return result

        wrapper._humane_guarded = True
        wrapper._action_type = action_type
        return wrapper
    return decorator
