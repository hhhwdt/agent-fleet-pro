"""Agent Fleet — AI-powered multi-agent development pipeline.

Usage:
    from agent_fleet import AgentFleet
    fleet = AgentFleet(config)
    fleet.run("Build a blog system")
"""

__version__ = "0.1.0"

from .engine import AgentFleet, decomposition_prompt, init_pipeline, generate_report
from .adapters import BaseAgentAdapter, SubprocessAdapter, MockAdapter, get_adapter
from .planners import BasePlanner, TemplatePlanner, LLMPlanner, DocAwarePlanner, get_planner
from .events import append_event, read_events, get_task_status

__all__ = [
    "AgentFleet", "decomposition_prompt", "init_pipeline", "generate_report",
    "BaseAgentAdapter", "SubprocessAdapter", "MockAdapter", "get_adapter",
    "BasePlanner", "TemplatePlanner", "LLMPlanner", "DocAwarePlanner", "get_planner",
    "append_event", "read_events", "get_task_status",
]
