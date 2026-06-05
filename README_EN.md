<p align="center"><img src="agent-fleet.png" width="120" alt="Agent Fleet"></p>

# Agent Fleet

> CI/CD pipeline for AI dev teams — a senior engineer + QA tester + code reviewer all working for you at once

> [中文](README.md) | English

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

Agent Fleet is **not** an AI agent. It's an orchestration layer on top of Claude Code / Cursor / Codex — decomposing tasks, dispatching agents, monitoring in real-time, and enforcing quality gates.

---

## Table of Contents

- [What is Agent Fleet?](#what-is-agent-fleet)
- [Where Files Go](#where-files-go)
- [Installation & Setup](#installation--setup)
- [Usage Scenarios](#usage-scenarios)
- [Dashboard Walkthrough](#dashboard-walkthrough)
- [Configuration](#configuration)
- [FAQ](#faq)

---

## What is Agent Fleet?

Agent Fleet handles the entire dev pipeline for you:

- Splits requirements into coding, testing, and acceptance subtasks
- Dispatches independent parallel agents for each subtask
- Real-time Dashboard shows every agent's thinking and output
- Failed tests automatically notify coders to fix
- Failed acceptance automatically loops back for fixes (up to 5 rounds)
- Generates a comprehensive execution report when done

**One sentence**: the coder doesn't test itself, the tester doesn't write code, the reviewer answers only to requirements. Three independent brains holding each other accountable.

### vs Other Tools

| | Agent Fleet | ChatGPT | Cursor | Devin |
|---|---|---|---|---|
| Multi-role teamwork | 3 roles auto-split | None | None | Black box |
| Independent verification | Separate QA agent | Self-review | None | Opaque |
| Closed-loop fixing | Auto-iterates 5 rounds | Manual | None | Limited |
| Real-time dashboard | Yes | No | No | Yes |
| Open source (self-hosted) | MIT | - | No | No |

---

## Where Files Go

Pipeline data and source code go to separate places:

```
/your-fleet-data/              <- Pipeline data (set once)
  .fleet/
    run-20260604-120000/
      plan.json           <- Decomposition plan
      status.json         <- Current progress
      progress.log        <- Timeline log
      FINAL_REPORT.md     <- Final report
      analysis/           <- Requirement analysis
      roles/              <- Agent role definitions
      coder-01/
        output.log        <- Agent thinking process
        prompt.md         <- Full prompt agent received
        result.md         <- Agent output
      tester-01/
        output.log
        test-report.md
    run-20260604-150000/

  agent-fleet-pro/             <- Dashboard code here

/your-project/                 <- Your project (agents write code here)
  main.py
```

**Key rule**: Dashboard deployed once. Pipeline data centralized. Code wherever you work.

---

## Installation & Setup

### Step 1: Clone

```bash
git clone https://github.com/hhhwdt/agent-fleet-pro.git
cd agent-fleet-pro
```

### Step 2: Install Skill (Claude Code users)

SKILL.md contains the orchestration instructions. Copy it to your skills directory:

**Windows:**
```powershell
mkdir %USERPROFILE%\.claude\skills\agent-fleet-pro
copy SKILL_EN.md %USERPROFILE%\.claude\skills\agent-fleet-pro\SKILL.md
```

**macOS / Linux:**
```bash
mkdir -p ~/.claude/skills/agent-fleet-pro
cp SKILL_EN.md ~/.claude/skills/agent-fleet-pro/SKILL.md
```

Then open the copied SKILL.md and update these lines to your own directories:

```
| `FLEET_DIR` | /path/to/your/data/.fleet/ |
```

### Step 3: Deploy Dashboard (one-time, keep it running)

Install dependencies:

```bash
pip install -e .
```

Edit `config.yaml`. Set `work_dir` to the parent of `.fleet/`:

```yaml
# config.yaml
work_dir: "/path/to/your-data"   # .fleet/ will appear here
port: 8765                        # Dashboard port
```

Start:

```bash
agent-fleet dashboard
```

You should see:

```
[Agent Fleet] http://127.0.0.1:8765  (WebSocket enabled)
```

Open `http://localhost:8765` in your browser.

### Step 4: Verify Installation

Open any Claude Code session and run:

```
/agent-fleet-pro Write a Hello World Python script
```

Switch to the Dashboard — you should see a new run appear with live progress.

**If Dashboard shows nothing**, check:
1. `work_dir` in config.yaml and `FLEET_DIR` in SKILL.md point to the same directory
2. Dashboard is running
3. `.fleet/run-xxx/` folders exist under your data directory

---

## Usage Scenarios

### New Project from Scratch

```bash
cd ~/projects
claude
/agent-fleet-pro Build a blog system with Go backend + Vue frontend
```

### Existing Project + Requirements Doc

```bash
cd ~/my-existing-app
claude
/agent-fleet-pro ./docs/login-feature-spec.md
# or URL
/agent-fleet-pro https://wiki.company.com/req/LOGIN-2024
```

Agent Fleet first runs a **requirement analysis agent**: reads document, scans existing code, outputs analysis (impact scope, tech approach, risks). Then decomposes and executes.

### Multiple Projects Simultaneously

```bash
# Terminal 1: Project A
cd ~/project-a && claude
/agent-fleet-pro Fix slow user list loading

# Terminal 2: Project B
cd ~/project-b && claude
/agent-fleet-pro Add CSV export feature
```

Both appear in the **same Dashboard**, running independently.

### Python API (without Claude Code)

```python
from agent_fleet import init_pipeline, decompose_task, generate_report

meta = init_pipeline("./my-project", ".fleet", "Build a calculator")
print(decompose_task("Build a calculator"))
# Send to your agent. Write output.log + result.md per task.
# Dashboard auto-detects.
```

---

## Dashboard Walkthrough

```
+----------+-------------+----------------------------------+
| Runs     | Tasks       | Console        [Think][Result]   |
|          |             |                                  |
| Calc     | coder-01 + |  Analysis Report                 |
| Crawler  | coder-02 + |  Changed Files (3) [+]          |
|          | tester-01 + |    > main.py     [coder-01]     |
|          | acceptor +  |  Execution Report                |
|          |             |  Total: 3m 12s                  |
+----------+-------------+----------------------------------+
```

- **Left panel**: All runs, sorted by time. Click X to delete. Shows status and duration.
- **Middle panel**: Subtasks for selected run, color-coded by status.
- **Right panel**: Three tabs — Think Log (real-time agent thinking, color-tagged), Results (Markdown output), Prompt (complete prompt sent to agent).

When a run is selected but no task: shows comprehensive view — analysis report -> changed files (click to expand) -> execution report -> timing.

---

## Configuration

`config.yaml` (override with `config.local.yaml` for local changes):

```yaml
work_dir: "/path/to/your-data"  # .fleet/ parent directory
port: 8765
max_acceptance_rounds: 5        # max acceptance iterations
parallel_limit: 3               # max concurrent agents
agent_timeout_seconds: 300      # single agent timeout
```

---

## FAQ

**Q: Dashboard shows nothing after running a task?**
A: Check: 1) Dashboard's `work_dir` and SKILL.md's `FLEET_DIR` point to the same directory 2) `.fleet/run-xxx/` folders exist 3) Hard refresh browser (Ctrl+F5)

**Q: Agent produces no output files?**
A: Check the "Prompt" tab in Dashboard — if it still has `{placeholders}`, the orchestrator didn't fill in variables.

**Q: Agent log only has start and end lines?**
A: The system auto-detects and retries. If retries also fail, check if the agent received the full prompt template.

**Q: Do I need Claude Code?**
A: No. The Python API works with any agent (Cursor, Codex, etc). See Scenario 4.

**Q: Can I delete `.fleet/` data?**
A: Use the delete button in Dashboard, or `agent-fleet clean --force`. Add `.fleet/` to `.gitignore`.

---

## License

MIT
