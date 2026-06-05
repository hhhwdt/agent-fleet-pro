"""Event store — events.ndjson is the single source of truth for task status."""

import os, json
from datetime import datetime


def append_event(task_dir: str, event_type: str, **kwargs) -> dict:
    """Append an event to <task_dir>/events.ndjson. Returns the event dict."""
    event = {"ts": datetime.now().isoformat(), "event": event_type, **kwargs}
    ef = os.path.join(task_dir, "events.ndjson")
    os.makedirs(task_dir, exist_ok=True)
    with open(ef, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(task_dir: str) -> list:
    """Read all events from a task directory."""
    ef = os.path.join(task_dir, "events.ndjson")
    if not os.path.exists(ef):
        return []
    events = []
    with open(ef, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def get_task_status(task_dir: str) -> str:
    """Derive task status from events (not log parsing)."""
    events = read_events(task_dir)
    if not events:
        return "pending"
    last = events[-1]["event"]
    if last == "task.completed":
        return "completed"
    if last == "task.failed":
        return "failed"
    if last == "task.ready":
        return "ready"
    if last == "task.started" or last == "task.progress":
        return "running"
    if any(e["event"] == "task.completed" for e in events):
        return "completed"
    return "unknown"


def get_task_errors(task_dir: str) -> list:
    """Extract error messages from events."""
    return [e.get("error", "") for e in read_events(task_dir) if e.get("event") == "task.failed" and e.get("error")]


# ---- State machine ----

VALID_STATES = {"pending","ready","running","blocked","completed","failed_retryable","failed_terminal","cancelled"}
TRANSITIONS = {
    "pending":{"ready"},"ready":{"running","cancelled"},
    "running":{"completed","failed_retryable","failed_terminal","cancelled"},
    "blocked":{"ready","cancelled"},"completed":set(),
    "failed_retryable":{"ready"},"failed_terminal":set(),"cancelled":set(),
}
EVENT_TO_STATE = {"task.ready":"ready","task.started":"running","task.progress":"running","task.completed":"completed","task.failed":"failed_retryable","task.cancelled":"cancelled","task.blocked":"blocked"}

def get_state(task_dir: str) -> str:
    evts = read_events(task_dir)
    if not evts: return "pending"
    state = "pending"
    for e in evts:
        ns = EVENT_TO_STATE.get(e.get("event",""), "")
        if ns in TRANSITIONS.get(state,set()): state = ns
    return state

def is_terminal(state: str) -> bool:
    return not bool(TRANSITIONS.get(state,set()))

def can_transition(cur: str, nxt: str) -> bool:
    return nxt in TRANSITIONS.get(cur,set())
