"""Agent Fleet — Pipeline manager (no agent execution).

Agent Fleet is NOT an agent. It's the CI/CD pipeline + dashboard that sits
on top of whatever AI agent you use (Claude Code, Cursor, Codex, OpenCode, etc.).

It handles:
  - Task decomposition (split requirements into code/test/accept subtasks)
  - Pipeline state management (plan.json / status.json / progress.log)
  - Report generation (FINAL_REPORT.md)
  - Web dashboard for real-time monitoring

Your agent does the actual coding/testing/acceptance work. Agent Fleet tells
it WHAT to do and shows you the big picture.
"""

import os, json
from datetime import datetime
from . import storage, events
from .adapters import get_adapter
from .planners import get_planner


# ---- Phase 0: Requirement Analysis ----

def analysis_prompt(requirement_text: str, project_context: str = "", lang: str = "en") -> str:
    """Return a prompt for analyzing a requirement document in context of existing code.

    Call this with your agent before task decomposition when the user provides
    a URL, file path, or document link.

    Args:
        requirement_text: The content of the requirement document.
        project_context: Optional project structure/codebase overview.

    Returns:
        A prompt for the analyst agent.
    """
    ctx = f"\n## 现有项目\n{project_context}" if project_context else ""
    return f"""你是需求分析师。分析需求文档，结合现有代码库，输出分析报告。

## 需求文档
{requirement_text}
{ctx}

输出分析报告（用中文）：

## 需求分析报告

### 需求概述
（用 2-3 句话概述要做什么）

### 影响范围
- 涉及哪些现有模块/文件
- 需要新增哪些文件

### 技术方案
- 推荐实现方式
- 关键技术选型

### 风险评估
- 潜在风险

### 建议的任务拆分
- 推荐拆成几个编码任务
- 各任务负责什么"""


def is_requirement_document(user_input: str) -> bool:
    """Check if user input is a requirement document (URL or file path)."""
    return (
        user_input.startswith("http://") or
        user_input.startswith("https://") or
        any(user_input.endswith(ext) for ext in [".md", ".txt", ".pdf", ".docx", ".rst"])
    )


# ---- Phase 1: Task Decomposition ----

def decomposition_prompt(task: str, analysis_report: str = "") -> dict:
    """Return a prompt for decomposing a task into subtasks.

    Call this with your agent to get the plan JSON.
    """
    analysis_context = ""
    if analysis_report:
        analysis_context = f"\n## 需求分析报告\n{analysis_report}\n\n基于以上分析报告，拆分任务。"

    return f"""You are a task decomposition expert. Split the following task into coding, testing, and acceptance subtasks.

Task: {task}
{analysis_context}

Rules:
- code tasks: 2-4, responsible for writing implementation code, maximize parallelism
- test tasks: 1-2, responsible for writing and running tests, depends on related code tasks
- acceptance task: 1, verifies all acceptance criteria, depends on all tests

Return ONLY valid JSON (no other text):
{{
  "summary": "one-line summary",
  "acceptance_criteria": ["criterion 1", "criterion 2", ...],
  "tasks": [
    {{"id": "coder-01", "type": "code", "name": "Module Name", "responsibility": "What to build", "expected_files": [], "depends_on": []}},
    {{"id": "tester-01", "type": "test", "name": "Test Name", "responsibility": "What to test", "expected_files": [], "depends_on": ["coder-01"]}},
    {{"id": "acceptor-01", "type": "acceptance", "name": "Acceptance", "responsibility": "Verify all criteria", "expected_files": [], "depends_on": ["tester-01"]}}
  ]
}}"""


def simple_plan(task: str) -> dict:
    """Generate a minimal 1-coder plan without calling an agent."""
    return {
        "summary": task[:80],
        "acceptance_criteria": ["Code runs without errors", "Meets requirements"],
        "tasks": [
            {"id": "coder-01", "type": "code", "name": "Main Implementation",
             "responsibility": f"Implement: {task}", "expected_files": [], "depends_on": []},
            {"id": "tester-01", "type": "test", "name": "Tests",
             "responsibility": "Write and run tests", "expected_files": [], "depends_on": ["coder-01"]},
            {"id": "acceptor-01", "type": "acceptance", "name": "Acceptance",
             "responsibility": "Verify requirements", "expected_files": [], "depends_on": ["tester-01"]},
        ]
    }


def init_pipeline(work_dir: str, fleet_dir: str, task: str,
                  plan: dict = None, analysis_report: str = "") -> dict:
    """Initialize a pipeline run: create directories and all metadata files.

    Args:
        work_dir: Working directory for the project.
        fleet_dir: Subdirectory for .fleet data (default: ".fleet").
        task: Task description from user.
        plan: Optional task breakdown plan. If None, uses simple_plan().
        analysis_report: Optional Phase 0 analysis report (saved to analysis/).

    Returns the meta dict with run_id, run_dir, roles_dir, tasks.
    """
    if plan is None:
        plan = simple_plan(task)

    # 输入校验
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")
    tasks = plan.get("tasks", [])
    if not tasks:
        raise ValueError("plan.tasks is empty")
    for t in tasks:
        if "id" not in t:
            raise ValueError(f"task missing 'id': {t}")
        if "type" not in t:
            raise ValueError(f"task missing 'type': {t}")

    # 如果有分析报告，写入 plan.json
    if analysis_report:
        plan["analysis"] = analysis_report

    meta = storage.init_run(work_dir, fleet_dir, plan, task)

    # 保存分析报告到独立文件
    if analysis_report:
        analysis_dir = os.path.join(meta["run_dir"], "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        with open(os.path.join(analysis_dir, "requirement-analysis.md"),
                  "w", encoding="utf-8") as f:
            f.write(analysis_report)

    # Write role prompt files
    criteria = plan.get("acceptance_criteria", [])
    criteria_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(criteria))

    for t in meta["tasks"]:
        tp = t.get("type", "code")
        if tp == "code":
            content = (
                f"# Role: {t['name']}\n\n"
                f"## Responsibility\n{t.get('responsibility', '')}\n\n"
                f"## Rules\n- Only write implementation code, do not write tests\n"
                f"- Ensure code is runnable\n- Write all output in English or Chinese consistently\n"
            )
        elif tp == "test":
            content = (
                f"# Role: {t['name']}\n\n"
                f"## Responsibility\n{t.get('responsibility', '')}\n\n"
                f"## Rules\n- Run tests and paste real output\n"
                f"- Analyze root cause of failures\n- Do NOT modify implementation code\n"
            )
        else:
            content = (
                f"# Role: Acceptance Reviewer\n\n"
                f"## Acceptance Criteria\n{criteria_text}\n\n"
                f"## Rules\n- Check each criterion, provide evidence\n"
                f"- Must actually run the project\n- Report pass/fail per criterion\n"
            )

        path = os.path.join(meta["roles_dir"], f"{t['id']}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    return meta


# ---- AgentFleet class ----

class AgentFleet:
    """Main orchestrator using pluggable adapters and planners."""

    def __init__(self, config: dict):
        self._validate_config(config)
        self.work_dir = os.path.abspath(config.get("work_dir", "."))
        self.fleet_dir = config.get("fleet_dir", ".fleet")
        self.max_accept = config.get("max_acceptance_rounds", 5)
        self.max_coding = config.get("max_coding_rounds", 10)
        self.timeout = config.get("agent_timeout_seconds", 300)
        self.max_parallel = config.get("parallel_limit", 3)
        self.adapter = get_adapter(config)
        self.planner = get_planner(config, self.adapter)
        # Observability
        self.stats = {"tasks": 0, "retries": 0, "failures": {}, "durations": []}

    def run(self, task: str, plan: dict = None):
        if plan is None:
            plan = self.planner.plan(task)
        meta = init_pipeline(self.work_dir, self.fleet_dir, task, plan)
        run_dir, tasks = meta["run_dir"], meta["tasks"]
        done = set()  # Global done set — survives across phases

        # Phase 2 + 3: coding then testing
        for phase in [("coding", "code"), ("testing", "test")]:
            storage.phase_start(run_dir, phase[0])
            done = self._dispatch_type(phase[1], tasks, run_dir, done)
            storage.phase_end(run_dir, phase[0],
                              "testing" if phase[0] == "coding" else "acceptance")

        # Phase 4: acceptance loop. Each round must re-run acceptor.
        passed = False
        acceptor_ids = {t["id"] for t in tasks if t.get("type") == "acceptance"}
        for rnd in range(1, self.max_accept + 1):
            storage.phase_start(run_dir, "acceptance")
            # Remove acceptor from done so it re-runs every round
            acc_done = done - acceptor_ids
            done = self._dispatch_type("acceptance", tasks, run_dir, acc_done)
            passed = self._check_acceptance(run_dir)
            if passed:
                storage.phase_end(run_dir, "acceptance")
                storage.append_log(run_dir, f"[验收] 第{rnd}轮: 通过")
                break
            if rnd < self.max_accept:
                storage.append_log(run_dir, f"[验收] 第{rnd}轮: 不通过，进入修复")
                self.stats["retries"] += 1
                # Fix round: re-dispatch ALL coders and testers (ignore previous done)
                done = self._dispatch_type("code", tasks, run_dir)
                done = self._dispatch_type("test", tasks, run_dir, done)
            else:
                storage.update_status(run_dir, status="force_stopped")
                storage.append_log(run_dir, f"[验收] {self.max_accept}轮均未通过，强制结束")

        generate_report(run_dir, task, tasks, passed, meta["run_id"])
        storage.update_status(run_dir, status="done",
                              finished_at=datetime.now().isoformat())
        return meta

    def _dispatch_type(self, tp, tasks, run_dir, done=None):
        """Dispatch tasks with real parallel + dep scheduling. Returns updated done set."""
        import time as _time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if done is None:
            done = set()
        max_rounds = self.max_coding
        for _ in range(max_rounds):
            # Respect depends_on: only dispatch tasks whose deps are done
            ready = [t for t in tasks
                     if t.get("type") == tp
                     and t["id"] not in done
                     and all(d in done for d in t.get("depends_on", []))]
            if not ready:
                break

            # Real parallel execution
            max_w = min(self.max_parallel, len(ready))
            with ThreadPoolExecutor(max_workers=max_w) as ex:
                futures = {ex.submit(self._run, t, run_dir): t for t in ready}
                for f in as_completed(futures):
                    t = futures[f]
                    try:
                        ok = f.result()
                        if ok:
                            done.add(t["id"])
                            events.append_event(os.path.join(run_dir, t["id"]), "task.completed")
                        else:
                            events.append_event(os.path.join(run_dir, t["id"]), "task.failed", error="agent returned failure")
                        self.stats["tasks"] += 1
                    except Exception as e:
                        events.append_event(os.path.join(run_dir, t["id"]), "task.failed", error=str(e))

        return done

    @staticmethod
    def _validate_config(config: dict):
        """Validate config values, raise ValueError on bad inputs."""
        port = config.get("port", 8765)
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"port must be 1-65535, got {port}")
        mr = config.get("max_acceptance_rounds", 5)
        if not isinstance(mr, int) or mr < 1 or mr > 20:
            raise ValueError(f"max_acceptance_rounds must be 1-20, got {mr}")
        to = config.get("agent_timeout_seconds", 300)
        if not isinstance(to, int) or to < 1:
            raise ValueError(f"agent_timeout_seconds must be positive, got {to}")
        pl = config.get("parallel_limit", 3)
        if not isinstance(pl, int) or pl < 1 or pl > 100:
            raise ValueError(f"parallel_limit must be 1-100, got {pl}")

    def _run(self, task, run_dir) -> bool:
        """Run one agent and write output to disk. Returns success bool."""
        import time as _time
        t_start = _time.time()
        tid = task["id"]
        td = os.path.join(run_dir, tid)
        os.makedirs(td, exist_ok=True)

        # Write prompt
        prompt = self._prompt(task, run_dir)
        with open(os.path.join(td, "prompt.md"), "w", encoding="utf-8") as f:
            f.write(prompt)

        # Init log
        log_file = os.path.join(td, "output.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[开始] {task['id']}: {task.get('name','')}\n")

        # Execute
        events.append_event(td, "task.started")
        result = self.adapter.execute(prompt, self.work_dir, td, self.timeout)

        # Write output to files
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(result.get("output", "")[:5000] + "\n")
            f.write(f"[{'完成' if result['success'] else '错误'}] {task['id']}\n")

        # Write result.md for coders
        task_type = task.get("type", "code")
        out_file = {"code": "result.md", "test": "test-report.md", "acceptance": "acceptance-report.md"}.get(task_type, "result.md")
        with open(os.path.join(td, out_file), "w", encoding="utf-8") as f:
            f.write(f"# {task.get('name', tid)}\n\n{result.get('output', '')[:3000]}\n")

        self.stats["durations"].append(_time.time() - t_start)
        storage.update_status(run_dir,
            agents={tid: {"status": "done" if result["success"] else "failed"}})
        return result.get("success", False)

    def _prompt(self, task, run_dir):
        """Build agent prompt from role file + task info + acceptance criteria."""
        tid = task["id"]
        # Read role file as prompt body
        role_file = os.path.join(run_dir, "roles", f"{tid}.md")
        body = ""
        if os.path.exists(role_file):
            with open(role_file, "r", encoding="utf-8") as f:
                body = f.read()

        # Read acceptance criteria from plan.json
        criteria = ""
        pf = os.path.join(run_dir, "plan.json")
        if os.path.exists(pf):
            import json
            with open(pf, "r", encoding="utf-8") as f:
                plan = json.load(f)
            ac = plan.get("acceptance_criteria", [])
            if ac:
                criteria = "\n".join(f"{i+1}. {c}" for i, c in enumerate(ac))

        header = {
            "code": "Write only implementation code. Do NOT write tests.",
            "test": "Write and run tests. Paste real output. Do NOT modify implementation code. Write test-report.md.",
            "acceptance": "Check every criterion. Must run the project. Write acceptance-report.md with VERDICT: PASS or FAIL."
        }.get(task.get("type", "code"), "")

        return f"""## All output in your preferred language. Write output.log in real-time.
Format: [开始] [思考] [分析] [行动] [结果] [决定] [完成]
output.log with fewer than 5 lines = REJECTED.

{body}

## Task
{task.get('name', tid)}: {task.get('responsibility', '')}

## Rules
{header}

## Acceptance Criteria
{criteria if criteria else 'See plan.json'}

## Working Directory: {self.work_dir}
## Output Directory: {os.path.join(run_dir, tid)}"""

    def _check_acceptance(self, run_dir) -> bool:
        """Check acceptance-report.md for explicit pass verdict."""
        for item in os.listdir(run_dir):
            ip = os.path.join(run_dir, item)
            if not os.path.isdir(ip) or not item.startswith("acceptor"):
                continue
            rf = os.path.join(ip, "acceptance-report.md")
            if not os.path.exists(rf):
                return False
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    text = f.read().lower()
                # JSON-only verdict detection
                import re
                m = re.search(r'"(?:pass|通过|通过验收)"\s*:\s*(true|false)', text)
                return bool(m) and m.group(1) == "true"
            except Exception:
                return False
        return False


def generate_report(run_dir: str, task: str, tasks: list, passed: bool, run_id: str):
    """Generate FINAL_REPORT.md after pipeline completion."""
    lines = [
        "# Agent Fleet — Execution Report",
        "",
        f"**Task**: {task}",
        f"**Run ID**: {run_id}",
        f"**Status**: {'PASSED' if passed else 'NOT PASSED'}",
        f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Agent Results",
        "",
        "| Agent | Type | Output |",
        "|-------|------|--------|",
    ]

    for t in tasks:
        tid = t["id"]
        tdir = os.path.join(run_dir, tid)
        result_files = []
        for fn in ["result.md", "test-report.md", "acceptance-report.md"]:
            if os.path.exists(os.path.join(tdir, fn)):
                result_files.append(fn)
        lines.append(
            f"| {tid} | {t.get('type', 'code')} | "
            f"{', '.join(result_files) if result_files else 'no output'} |"
        )

    lines.extend(["", "## Files Produced", ""])

    for t in tasks:
        rf = os.path.join(run_dir, t["id"], "result.md")
        if os.path.exists(rf):
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    content = f.read()
                lines.append(f"### {t['id']}: {t.get('name', '')}")
                lines.append(f"```\n{content[:500]}\n```\n")
            except (IOError, UnicodeDecodeError):
                pass

    report_path = os.path.join(run_dir, "FINAL_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    storage.append_log(run_dir, f"[报告] FINAL_REPORT.md 已生成")
    return report_path
