# Contributing to Agent Fleet

## Setup

```bash
git clone https://github.com/hhhwdt/agent-fleet-pro.git
cd agent-fleet-pro
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
agent_fleet/
├── adapters/     # Agent backends (BaseAgentAdapter + impls)
├── planners/     # Task decomposition strategies
├── events.py     # Event store + state machine
├── engine.py     # Pipeline init + AgentFleet orchestrator
├── storage.py    # File I/O for plan/status/progress/events
├── server.py     # Flask API + WebSocket Dashboard
├── cli.py        # CLI commands
└── templates/    # Dashboard HTML
```

## Architecture

Agent Fleet is NOT an AI agent. It's a CI/CD pipeline + monitoring dashboard that sits on top of whatever agent you use.

Key principles:
- **Events as truth**: Task status comes from events.ndjson, not log parsing
- **Pluggable**: Adapters and planners are interfaces, not hardcoded
- **File-first**: All data is JSON/Markdown in .fleet/, human-readable
- **Local-first**: No cloud dependency, runs on your machine

## Adding a new Agent Adapter

1. Subclass `BaseAgentAdapter` in `adapters/__init__.py`
2. Implement `execute(prompt, work_dir, task_dir, timeout) -> dict`
3. Return `{success, output, error, events}` where events is a list of `{ts, event, ...}`

## Adding a new Planner

1. Subclass `BasePlanner` in `planners/__init__.py`
2. Implement `plan(task, context=None) -> dict`
3. Return `{summary, acceptance_criteria, tasks}`

## Commit Convention

- `feat:` new feature
- `fix:` bug fix
- `refactor:` code restructuring
- `docs:` documentation
- `test:` tests

## License

MIT
