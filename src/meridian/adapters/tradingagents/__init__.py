"""Optional TradingAgents adapter; vendor imports stay isolated in this package."""

from .engine import TradingAgentsResearchEngine
from .replay import ResearchReplayStore

__all__ = ["TradingAgentsResearchEngine", "ResearchReplayStore"]
