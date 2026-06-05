"""Test agent adapters."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_fleet.adapters import MockAdapter, SubprocessAdapter, get_adapter

def test_mock_adapter():
    adapter = MockAdapter()
    result = adapter.execute("hello", ".", tempfile.mkdtemp())
    assert result["success"]
    assert len(result["events"]) >= 2
    assert result["events"][0]["event"] == "task.started"
    assert result["events"][-1]["event"] == "task.completed"

def test_mock_adapter_events_structure():
    adapter = MockAdapter()
    result = adapter.execute("test", ".", tempfile.mkdtemp())
    for ev in result["events"]:
        assert "ts" in ev
        assert "event" in ev

def test_get_adapter_factory():
    a1 = get_adapter({"backend": "mock"})
    assert isinstance(a1, MockAdapter)
    a2 = get_adapter({"backend": "subprocess", "agent_command": "cat {prompt_file}"})
    assert isinstance(a2, SubprocessAdapter)
