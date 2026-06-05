"""Test events module and state machine."""
import tempfile, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_fleet.events import (
    append_event, read_events, get_task_status, get_task_errors,
    get_state, is_terminal, can_transition, VALID_STATES, TRANSITIONS
)

def test_append_and_read():
    td = tempfile.mkdtemp()
    append_event(td, "task.started")
    append_event(td, "task.completed")
    evts = read_events(td)
    assert len(evts) == 2
    assert evts[0]["event"] == "task.started"
    assert evts[1]["event"] == "task.completed"

def test_get_task_status():
    td = tempfile.mkdtemp()
    assert get_task_status(td) == "pending"
    append_event(td, "task.started")
    assert get_task_status(td) == "running"
    append_event(td, "task.completed")
    assert get_task_status(td) == "completed"

def test_get_task_errors():
    td = tempfile.mkdtemp()
    assert get_task_errors(td) == []
    append_event(td, "task.started")
    append_event(td, "task.failed", error="timeout")
    assert "timeout" in get_task_errors(td)[0]

def test_state_machine_transitions():
    # Valid transitions
    assert can_transition("pending", "ready")
    assert can_transition("ready", "running")
    assert can_transition("running", "completed")
    assert can_transition("running", "failed_retryable")
    assert can_transition("failed_retryable", "ready")
    # Invalid transitions
    assert not can_transition("completed", "ready")
    assert not can_transition("pending", "completed")
    assert not can_transition("cancelled", "running")

def test_terminal_states():
    assert is_terminal("completed")
    assert is_terminal("failed_terminal")
    assert is_terminal("cancelled")
    assert not is_terminal("pending")
    assert not is_terminal("running")

def test_all_states_in_transitions():
    for s in VALID_STATES:
        assert s in TRANSITIONS, f"Missing: {s}"

def test_get_state_from_events():
    td = tempfile.mkdtemp()
    assert get_state(td) == "pending"
    append_event(td, "task.ready")
    assert get_state(td) == "ready"
    append_event(td, "task.started")
    assert get_state(td) == "running"
    append_event(td, "task.completed")
    assert get_state(td) == "completed"
