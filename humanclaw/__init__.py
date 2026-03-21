"""HumanClaw — human behavioral middleware for AI agents."""

__version__ = "1.0.0"

from humanclaw.guard import guard
from humanclaw.core.models import ProposedAction, Verdict, HoldItem
from humanclaw.conductor import Conductor

__all__ = ["guard", "Conductor", "ProposedAction", "Verdict", "HoldItem", "__version__"]
