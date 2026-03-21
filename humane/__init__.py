"""Humane — human behavioral middleware for AI agents."""

__version__ = "1.0.0"

from humane.guard import guard
from humane.core.models import ProposedAction, Verdict, HoldItem
from humane.conductor import Conductor

__all__ = ["guard", "Conductor", "ProposedAction", "Verdict", "HoldItem", "__version__"]
