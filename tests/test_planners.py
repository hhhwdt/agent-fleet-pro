"""Test planner implementations."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_fleet.planners import TemplatePlanner, LLMPlanner, get_planner
from agent_fleet.adapters import MockAdapter

def test_template_planner():
    p = TemplatePlanner()
    plan = p.plan("Build a calculator")
    assert "summary" in plan
    assert "acceptance_criteria" in plan
    tasks = plan["tasks"]
    assert len(tasks) == 3
    types = {t["type"] for t in tasks}
    assert types == {"code", "test", "acceptance"}
    for t in tasks:
        assert "id" in t
        assert "name" in t
        assert "depends_on" in t

def test_template_planner_task_structure():
    p = TemplatePlanner()
    plan = p.plan("Any task")
    tasks = plan["tasks"]
    coder = [t for t in tasks if t["type"] == "code"][0]
    tester = [t for t in tasks if t["type"] == "test"][0]
    assert tester["depends_on"] == [coder["id"]]

def test_llm_planner_fallback():
    adapter = MockAdapter()
    p = LLMPlanner(adapter)
    plan = p.plan("Build X")
    assert len(plan["tasks"]) == 3  # Falls back to template

def test_get_planner_factory():
    p = get_planner({"planner": "template"})
    assert isinstance(p, TemplatePlanner)
    adapter = MockAdapter()
    p2 = get_planner({"planner": "llm"}, adapter)
    assert isinstance(p2, LLMPlanner)
