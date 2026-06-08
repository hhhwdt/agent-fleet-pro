"""Agent Fleet — Pipeline infrastructure (orchestration is in SKILL.md).

Agent Fleet is NOT an agent. It's the file I/O + state management + Dashboard
that supports multi-agent pipelines.

IMPORTANT: The full orchestration logic (Phase 0-6 with quality gates, retry
penalties, cross-validation, prompt templates) lives in SKILL.md — a Claude Code
skill that Claude interprets at runtime. engine.py provides the Python
infrastructure: plan/status/progress file I/O, adapter dispatch, report generation.
For the complete pipeline experience, use /agent-fleet-pro in Claude Code.

It handles:
  - Task decomposition (split requirements into code/test/accept subtasks)
  - Pipeline state management (plan.json / status.json / progress.log)
  - Report generation (FINAL_REPORT.md)
  - Web dashboard for real-time monitoring
  - Topology loading for custom pipeline stages
"""

import os, json, yaml, threading
from datetime import datetime
from . import storage, events
from .adapters import get_adapter
from .planners import get_planner
from .sandbox import SubprocessSandbox


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
        "acceptance_criteria": [
            {"id": "ac-1", "描述": "核心功能正常执行",
             "输入": f"正常调用 {task[:30]}", "期望": "返回预期结果，无异常"},
            {"id": "ac-2", "描述": "边界输入不崩溃",
             "输入": "空值/0/-1/超长字符串", "期望": "返回明确错误信息，不静默崩溃"},
        ],
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
    criteria_lines = []
    for i, c in enumerate(criteria):
        if isinstance(c, dict):
            desc = c.get('描述', c.get('description', ''))
            inp = c.get('输入', c.get('verify', ''))
            exp = c.get('期望', '')
            criteria_lines.append(f"  {i+1}. {desc}\n     输入: {inp}\n     期望: {exp}")
        else:
            criteria_lines.append(f"  {i+1}. {c}")
    criteria_text = "\n".join(criteria_lines)

    for t in meta["tasks"]:
        tp = t.get("type", "code")
        if tp == "code":
            content = (
                f"# Role: {t['name']}\n\n"
                f"## Responsibility\n{t.get('responsibility', '')}\n\n"
                f"## Rules\n- Only write implementation code, do not write tests\n"
                f"- Ensure code is runnable\n- Output a main entry point that can be executed\n"
            )
        elif tp == "test":
            # Tester does NOT see implementation code — only requirements + interface
            content = (
                f"# Role: {t['name']}\n\n"
                f"## Responsibility\n{t.get('responsibility', '')}\n\n"
                f"## CRITICAL RULES\n"
                f"- You CANNOT see the implementation code. You only see requirements below.\n"
                f"- Write tests that CHALLENGE the code, not tests that fit the code.\n"
                f"- Cover: happy path, edge cases (0/-1/empty), invalid input, combinations.\n"
                f"- Run tests and paste REAL output. Do NOT modify implementation code.\n"
                f"- Write test-report.md with test case table and pass/fail per case.\n"
            )
        else:
            # Acceptor checks independently — doesn't trust coder or tester
            content = (
                f"# Role: Acceptance Reviewer\n\n"
                f"## Acceptance Criteria (check EVERY item below)\n{criteria_text}\n\n"
                f"## CRITICAL RULES\n"
                f"- You answer to REQUIREMENTS only — not to the coder, not to the tester.\n"
                f"- For EACH criterion: actually run the code, get real output, compare.\n"
                f"- Output: acceptance-report.md with table: | # | Criterion | Expected | Actual | Pass? | Evidence |\n"
                f"- Also check: did coder add features NOT in requirements? (over-implementation)\n"
                f"- Also check: did coder MISS any requirement? (under-implementation)\n"
                f"- Verdict must include JSON: {{\"pass\": true/false, \"evidence\": [...]}}\n"
                f"- Do NOT pass just because tests passed. Verify against requirements.\n"
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
        sb_cfg = config.get("sandbox", {})
        self.sandbox = SubprocessSandbox(timeout=sb_cfg.get("timeout_seconds", 30)) if sb_cfg.get("enabled", True) else None
        self._stats_lock = threading.Lock()
        self.stats = {"tasks": 0, "retries": 0, "failures": {}, "durations": []}

    def _topology_to_plan(self, topo: dict, task: str) -> dict:
        """Convert topology YAML to plan dict for the pipeline."""
        tasks = []
        for stage in topo.get("stages", []):
            sid = stage["id"]
            count_str = str(stage.get("count", "1"))
            count_max = int(count_str.split("-")[-1]) if "-" in count_str else int(count_str)
            for i in range(count_max):
                tid = f"{sid}-{i+1:02d}" if count_max > 1 else f"{sid}-01"
                deps = []
                for d in stage.get("depends_on", []):
                    for other in topo.get("stages", []):
                        if other["id"] == d:
                            dc = str(other.get("count", "1"))
                            dm = int(dc.split("-")[-1]) if "-" in dc else int(dc)
                            deps.extend(f"{d}-{j+1:02d}" for j in range(dm))
                            break
                    if not deps:
                        deps.append(f"{d}-01")
                tasks.append({
                    "id": tid, "type": sid,
                    "name": f"{sid} #{i+1}" if count_max > 1 else sid,
                    "responsibility": stage.get("role", f"Execute {sid} stage"),
                    "expected_files": [], "depends_on": deps,
                })
        return {
            "summary": task[:80],
            "acceptance_criteria": [{"id": "ac-1", "description": "All stages complete", "verify": "Pipeline passes"}],
            "tasks": tasks,
        }

    def _load_topology(self, name: str) -> dict:
        """Load topology from topologies/<name>.yaml."""
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "topologies", f"{name}.yaml")
        if not os.path.exists(path):
            raise ValueError(f"Topology not found: {name}. Available: review-first, security-audit, pair-programming")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self, task: str, plan: dict = None, topology: str = None):
        if plan is None:
            if topology:
                topo = self._load_topology(topology)
                plan = self._topology_to_plan(topo, task)
            else:
                plan = self.planner.plan(task)
        meta = init_pipeline(self.work_dir, self.fleet_dir, task, plan)
        run_dir, tasks = meta["run_dir"], meta["tasks"]

        # Phase 0: Basic analysis (scan project structure, write report)
        analysis_dir = os.path.join(run_dir, "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        files_found = []
        for root, _, files in os.walk(self.work_dir):
            if ".fleet" in root:
                continue
            for fn in files:
                if fn.endswith((".py", ".js", ".ts", ".html", ".css", ".go", ".rs", ".java")):
                    files_found.append(os.path.relpath(os.path.join(root, fn), self.work_dir))
        analysis_text = f"## Project Analysis\n\n**Task**: {task}\n\n**Working Directory**: {self.work_dir}\n\n**Existing files** ({len(files_found)}):\n"
        analysis_text += "\n".join(f"- {f}" for f in files_found[:50])
        if len(files_found) > 50:
            analysis_text += f"\n... and {len(files_found) - 50} more"
        with open(os.path.join(analysis_dir, "requirement-analysis.md"), "w", encoding="utf-8") as f:
            f.write(analysis_text)
        storage.append_log(run_dir, "[Phase 0] 项目分析完成")

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
                # Fix round: only reset FAILED agents (not all code+test)
                failed_ids = {tid for tid, count in self.stats["failures"].items() if count > 0}
                done -= failed_ids  # Only reset agents that actually failed
                done = self._dispatch_type("code", tasks, run_dir, done)
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
                        with self._stats_lock:
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
        """Run one agent with isolated workspace. Returns success bool."""
        import time as _time
        t_start = _time.time()
        tid = task["id"]
        td = os.path.join(run_dir, tid)
        # Isolated workspace: each agent gets its own subdir to avoid file collisions
        work_subdir = os.path.join(self.work_dir, f"_{tid}_workspace")
        os.makedirs(td, exist_ok=True)
        os.makedirs(work_subdir, exist_ok=True)

        # Write prompt
        prompt = self._prompt(task, run_dir, work_subdir)
        with open(os.path.join(td, "prompt.md"), "w", encoding="utf-8") as f:
            f.write(prompt)

        # Init log
        log_file = os.path.join(td, "output.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[开始] {task['id']}: {task.get('name','')}\n")

        # Execute — use isolated workspace, pass task type for mock adapter
        task_type = task.get("type", "code")
        events.append_event(td, "task.started")
        result = self.adapter.execute(prompt, work_subdir, td, self.timeout, task_type=task_type)

        # Write output to files
        raw_output = result.get("output", "")
        if len(raw_output) > 10000:
            raw_output = raw_output[:10000] + f"\n...(truncated, {len(result.get('output', ''))} chars total)"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(raw_output + "\n")
            f.write(f"[{'完成' if result['success'] else '错误'}] {task['id']}\n")

        # Write result.md for coders (full output, no arbitrary truncation)
        out_file = {"code": "result.md", "test": "test-report.md", "acceptance": "acceptance-report.md"}.get(task_type, "result.md")
        with open(os.path.join(td, out_file), "w", encoding="utf-8") as f:
            f.write(f"# {task.get('name', tid)}\n\n{result.get('output', '')}\n")

        with self._stats_lock:
            self.stats["durations"].append(_time.time() - t_start)

        # Sandbox verification for coder output
        if self.sandbox and task_type == "code":
            sb_result = self._run_sandbox(run_dir, td)
            with open(os.path.join(td, "sandbox.json"), "w", encoding="utf-8") as f:
                json.dump({"exit_code": sb_result.exit_code, "stdout": sb_result.stdout[:2000],
                           "stderr": sb_result.stderr[:1000], "success": sb_result.success,
                           "timed_out": sb_result.timed_out, "duration": sb_result.duration_seconds}, f)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[沙箱] exit={sb_result.exit_code} success={sb_result.success}\n")
                if sb_result.stderr:
                    f.write(f"[沙箱错误] {sb_result.stderr[:500]}\n")

        # Validate output quality — failures override agent success
        issues = self.validate_output(td, task_type)
        for issue in issues:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[验证] {issue}\n")

        # Output validation failure → agent is NOT done, can be retried
        agent_ok = result.get("success", False) and not issues
        if issues:
            events.append_event(td, "task.failed", error=f"output validation: {len(issues)} issues")
            self.stats["failures"][tid] = self.stats["failures"].get(tid, 0) + 1
            # Max 2 retries (SKILL.md standard)
            if self.stats["failures"][tid] >= 3:
                events.append_event(td, "task.failed", error="max retries (3) exceeded")
                agent_ok = True  # Mark as "done" anyway to avoid infinite loop

        storage.update_status(run_dir,
            agents={tid: {"status": "done" if agent_ok else "failed"}},
            progress={"done": self.stats["tasks"]})
        return agent_ok

    def _prompt(self, task, run_dir, work_subdir=None):
        """Build agent prompt from role file + task info + acceptance criteria."""
        tid = task["id"]
        if work_subdir is None:
            work_subdir = self.work_dir
        # Read role file as prompt body
        role_file = os.path.join(run_dir, "roles", f"{tid}.md")
        body = ""
        if os.path.exists(role_file):
            with open(role_file, "r", encoding="utf-8") as f:
                body = f.read()

        # Inject previous sandbox errors if this is a fix round
        sandbox_context = ""
        sb_file = os.path.join(run_dir, tid, "sandbox.json")
        if os.path.exists(sb_file):
            try:
                import json as _j
                sb = _j.load(open(sb_file, "r", encoding="utf-8"))
                if not sb.get("success", True):
                    sandbox_context = f"\n## Previous Runtime Errors (fix these)\n{sb.get('stderr', '')[:1000]}\n"
            except Exception:
                pass

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

{sandbox_context}
## Working Directory: {work_subdir}
## Output Directory: {os.path.join(run_dir, tid)}"""

    @staticmethod
    def validate_output(task_dir: str, task_type: str) -> list:
        """Validate agent output against SKILL.md quality standards. Returns list of issues."""
        issues = []
        log_file = os.path.join(task_dir, "output.log")
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                log_lines = [l for l in f.readlines() if l.strip()]
            if len(log_lines) < 10:
                issues.append(f"output.log too short ({len(log_lines)} lines, need >=10)")
        else:
            issues.append("output.log missing")

        out_map = {"code": ("result.md", 800), "test": ("test-report.md", 1500),
                    "acceptance": ("acceptance-report.md", 2000)}
        out_info = out_map.get(task_type, ("result.md", 100))
        out_file = os.path.join(task_dir, out_info[0])
        if os.path.exists(out_file):
            size = os.path.getsize(out_file)
            if size < out_info[1]:
                issues.append(f"{out_info[0]} too small ({size}B, need >={out_info[1]}B)")
        else:
            issues.append(f"{out_info[0]} missing")
        return issues

    def _run_sandbox(self, run_dir, task_dir):
        """Run coder's generated code in sandbox. Find entry point intelligently."""
        from .sandbox import SandboxResult
        # Check task's result.md for file list, then verify those files exist and are new
        result_md = os.path.join(task_dir, "result.md")
        candidates = []
        if os.path.exists(result_md):
            with open(result_md, "r", encoding="utf-8") as f:
                text = f.read()
                import re
                for m in re.finditer(r'[\w./-]+\.py', text):
                    fp = os.path.join(self.work_dir, m.group(0).lstrip("./\\"))
                    if os.path.isfile(fp):
                        candidates.append(fp)
        # Fallback: find Python files modified after task started
        if not candidates:
            for root, _, files in os.walk(self.work_dir):
                if ".fleet" in root: continue
                for fn in files:
                    if fn.endswith(".py") and fn != "setup.py":
                        fp = os.path.join(root, fn)
                        if os.path.getmtime(fp) > os.path.getmtime(task_dir):
                            candidates.append(fp)
        if candidates:
            return self.sandbox.run_script(candidates[0])
        return SandboxResult()

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
                # JSON-only verdict detection (case-insensitive for True/False)
                import re
                # Match JSON: {"pass": true} or Chinese: {"通过": true}
                m = re.search(r'(?is)"(?:pass|通过|通过验收)"\s*[：:]\s*(true|false|True|False)', text)
                if m:
                    return m.group(1).lower() == "true"
                # Match VERDICT: PASS (plain text format, case insensitive)
                if re.search(r'(?i)VERDICT\s*[：:]\s*PASS', text):
                    return True
                if re.search(r'(?i)VERDICT\s*[：:]\s*FAIL', text):
                    return False
            except Exception:
                return False
        return False


def generate_report(run_dir: str, task: str, tasks: list, passed: bool, run_id: str):
    """Generate FINAL_REPORT.md matching SKILL.md Phase 6 7-section format."""
    now = datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Agent Fleet — Execution Report",
        "",
        "## 1. Basic Information",
        f"- **Task**: {task}",
        f"- **Run ID**: {run_id}",
        f"- **Status**: {'PASSED' if passed else 'NOT PASSED'}",
        f"- **Started**: {ts}",
        "",
        "## 2. Requirements Analysis Summary",
    ]

    # Read analysis report if exists
    af = os.path.join(run_dir, "analysis", "requirement-analysis.md")
    if os.path.exists(af):
        try:
            with open(af, "r", encoding="utf-8") as f:
                lines.append(f.read()[:2000])
        except Exception:
            lines.append("(analysis report unavailable)")
    else:
        lines.append("(no Phase 0 analysis was generated)")

    lines.append("")
    lines.append("## 3. Agent Outputs")
    lines.append("| Agent | Type | Output Files | Status |")
    lines.append("|-------|------|-------------|--------|")

    for t in tasks:
        tid = t["id"]
        tdir = os.path.join(run_dir, tid)
        result_files = []
        status = "pending"
        if os.path.isdir(tdir):
            for fn in ["result.md", "test-report.md", "acceptance-report.md"]:
                fp = os.path.join(tdir, fn)
                if os.path.exists(fp) and os.path.getsize(fp) > 100:
                    result_files.append(fn)
            if os.path.exists(os.path.join(tdir, "output.log")):
                status = "completed"
        lines.append(
            f"| {tid} | {t.get('type', 'code')} | "
            f"{', '.join(result_files) if result_files else '(no output)'} | {status} |"
        )

    lines.append("")
    lines.append("## 4. Acceptance Results")
    acc_files = [os.path.join(run_dir, t["id"], "acceptance-report.md")
                 for t in tasks if t.get("type") == "acceptance"]
    for acc_f in acc_files:
        if os.path.exists(acc_f):
            try:
                with open(acc_f, "r", encoding="utf-8") as f:
                    lines.append(f.read()[:2000])
            except Exception:
                lines.append(f"Verdict: {'PASS' if passed else 'FAIL'}")
        else:
            lines.append(f"Verdict: {'PASS' if passed else 'FAIL'} (no report file)")

    lines.append("")
    lines.append("## 5. Output File Manifest")
    for t in tasks:
        tdir = os.path.join(run_dir, t["id"])
        if not os.path.isdir(tdir):
            continue
        lines.append(f"### {t['id']}: {t.get('name', '')}")
        for root, _, files in os.walk(tdir):
            for fn in sorted(files):
                fp = os.path.join(root, fn)
                size = os.path.getsize(fp)
                lines.append(f"- `{os.path.relpath(fp, run_dir)}` ({size} bytes)")

    lines.append("")
    lines.append("## 6. How to Run")
    lines.append("(check individual agent output files for run instructions)")
    lines.append("")
    lines.append("## 7. Known Issues")
    lines.append("(none reported)" if passed else "(see acceptance results above)")

    report_path = os.path.join(run_dir, "FINAL_REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    storage.append_log(run_dir, "[报告] FINAL_REPORT.md 已生成")
    return report_path
