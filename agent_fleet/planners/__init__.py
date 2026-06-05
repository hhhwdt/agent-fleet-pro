"""Planners — task decomposition strategies."""

import abc, json, tempfile, os, logging
logger = logging.getLogger("agent_fleet.planners")


class BasePlanner(abc.ABC):
    """Abstract planner. Given a task description, return a plan dict."""

    @abc.abstractmethod
    def plan(self, task: str, context: dict = None) -> dict:
        """Return a plan: {summary, acceptance_criteria, tasks}."""
        ...


class TemplatePlanner(BasePlanner):
    """Default template planner — one coder, one tester, one acceptor."""

    def plan(self, task, context=None):
        return {
            "summary": task[:80],
            "acceptance_criteria": [
                {"id": "ac-1", "description": "核心功能正常执行",
                 "verify": f"输入: 正常调用 {task[:30]}\n期望: 返回预期结果，无异常"},
                {"id": "ac-2", "description": "边界输入处理",
                 "verify": "输入: 空值/0/-1/超长字符串\n期望: 不会崩溃，返回明确错误信息"},
                {"id": "ac-3", "description": "错误输入有提示",
                 "verify": "输入: 类型错误/None/非法格式\n期望: 返回错误信息，不静默吞错"},
            ],
            "tasks": [
                {"id": "coder-01", "type": "code", "name": "Main Implementation",
                 "responsibility": f"Implement: {task}", "expected_files": [], "depends_on": []},
                {"id": "tester-01", "type": "test", "name": "Tests",
                 "responsibility": "Write and run tests for the implementation",
                 "expected_files": [], "depends_on": ["coder-01"]},
                {"id": "acceptor-01", "type": "acceptance", "name": "Acceptance",
                 "responsibility": "Verify all acceptance criteria are met",
                 "expected_files": [], "depends_on": ["tester-01"]},
            ]
        }


class LLMPlanner(BasePlanner):
    """LLM-based planner — uses an adapter to decompose tasks."""

    def __init__(self, adapter):
        self.adapter = adapter

    def plan(self, task, context=None):
        ctx = ""
        if context and context.get("analysis"):
            ctx = f"\n## Analysis Report\n{context['analysis']}\nBased on the analysis above, decompose the task."

        prompt = f"""You are a task decomposition expert. Split the following task into coding, testing, and acceptance subtasks.

Task: {task}
{ctx}

Rules:
- code tasks: 2-4, maximize parallelism
- test tasks: 1-2, each depends on related code tasks
- acceptance task: 1, depends on all tests

Return ONLY valid JSON:
{{
  "summary": "one-line summary",
  "acceptance_criteria": [
    {{"id": "ac-1", "description": "specific scenario", "verify": "Input: xxx. Expected: yyy"}},
    {{"id": "ac-2", "description": "edge case", "verify": "Input: empty/zero. Expected: graceful error"}}
  ],
  "tasks": [
    {{"id": "coder-01", "type": "code", "name": "Name", "responsibility": "What to build", "expected_files": [], "depends_on": []}},
    {{"id": "tester-01", "type": "test", "name": "Name", "responsibility": "What to test", "expected_files": [], "depends_on": ["coder-01"]}},
    {{"id": "acceptor-01", "type": "acceptance", "name": "Acceptance", "responsibility": "Verify all criteria", "expected_files": [], "depends_on": ["tester-01"]}}
  ]
}}"""

        plan_dir = os.path.join(tempfile.gettempdir(), "agent_fleet_plan")
        result = self.adapter.execute(prompt, ".", plan_dir, 120)
        if result.get("success") and result.get("output"):
            text = result["output"].strip()
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.warning("LLMPlanner: JSON parse failed, falling back to TemplatePlanner. Raw output: %s", text[:200])
        # Fallback
        logger.info("LLMPlanner: using TemplatePlanner (fallback)")
        return TemplatePlanner().plan(task, context)


class DocAwarePlanner(LLMPlanner):
    """Document-aware planner — reads requirement docs before planning."""

    def plan(self, task, context=None):
        ctx = context or {}
        if any(task.endswith(ext) for ext in [".md", ".txt", ".rst"]):
            if os.path.isfile(task):
                try:
                    with open(task, "r", encoding="utf-8") as f:
                        ctx["analysis"] = f"## Document: {task}\n\n{f.read()[:3000]}"
                except Exception as e:
                    logger.warning("DocAwarePlanner: failed to read %s: %s", task, e)
            else:
                logger.warning("DocAwarePlanner: file not found: %s", task)
        return super().plan(task, ctx)


def get_planner(config: dict, adapter=None) -> BasePlanner:
    """Factory: create planner from config."""
    planner_type = config.get("planner", "template")
    if planner_type == "llm" and adapter:
        return LLMPlanner(adapter)
    elif planner_type == "doc_aware" and adapter:
        return DocAwarePlanner(adapter)
    return TemplatePlanner()
