---
name: agent-fleet-pro
description: "Multi-agent parallel orchestration engine. Triggered only by /agent-fleet-pro."
---

# Agent Fleet Pro — Multi-Agent Parallel Orchestration

**Triggered only when the user types `/agent-fleet-pro`.**

## Directory Convention

| Directory | Value | Purpose |
|---|---|---|
| `FLEET_DIR` | **Fixed**: `/path/to/data/.fleet/` | Pipeline data, Dashboard reads here |
| `CODE_DIR` | **Dynamic**: current session dir | Agents write code here |

Dashboard: `python agent-fleet-pro/run.py` -> http://localhost:8765

---

## Speed Card (30 sec)

```
1. Has doc? -> Phase 0: analysis Agent
2. Decompose -> Agent -> code/test/accept -> plan.json / status.json / roles
3. Code -> Agent(bg) x N -> verify: output.log>=5 + [think][analyze][act][result]>=1 + result.md
4. Test -> Agent(bg) -> test-report.md -> fail? notify coder -> back to 3
5. Accept -> Agent(bg) -> acceptance-report.md -> fail+round<5? back to 3
6. Summary -> Agent(bg) -> FINAL_REPORT.md -> 6 quality checks

Iron: orchestrator NEVER codes/tests/accepts | independent Agent per phase | missing file = blocked
```

---

## Iron Rule: Orchestrator Must NOT Do Agent Work

Orchestrator does ONLY: decompose, dispatch, decide, summarize. MUST NOT: write code, run tests, do acceptance. Each phase MUST launch independent Agent (`run_in_background: true`).

---

## Quality Checks (Every Dispatch)

**Pre**: 9-item checklist (log format, failure consequence, role file, round info, output filename, all placeholders replaced, concrete paths, fix context, markers).

**Post**: Verify output.log exists, >=5 lines, has [think]/[analyze]/[act]/[result]/[done] markers. Verify type-specific output file exists. Fix-round agents also need result.md. Any check fails -> retry.

## Phase Gates

| Phase | Gate |
|---|---|
| 2 done | All coder output.log + result.md exist |
| 3 done | All tester output.log + test-report.md exist, all pass |
| 4 done | Acceptor output.log + acceptance-report.md exist, pass |
| 6 done | FINAL_REPORT.md exists |

## Phases 0-6

- **Phase 0**: Requirement analysis (URL/file only). Read doc, scan code, launch analysis Agent.
- **Phase 1**: Decomposition + init. Create dirs, decompose, write role files, plan.json, status.json, progress.log.
- **Phase 2**: Parallel coding. Agent(bg) x N. Verify logs.
- **Phase 3**: Parallel testing. Agent(bg). Read test-report.md -> pass or fix.
- **Phase 4**: Acceptance. MUST launch independent Agent. Read acceptance-report.md -> pass or loop (max 5).
- **Phase 5**: Force stop.
- **Phase 6**: Summary. Pre-check acceptance-report.md. MUST launch independent Agent. Report: 7 sections. Orchestrator verifies 6 quality checks.

## Timeout & Dashboard

Check agents every 60-90s. `TaskOutput(timeout=90000)`. Max 5 min per agent.

```bash
python agent-fleet-pro/run.py
```
