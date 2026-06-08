"""Agent adapters — unified interface for different AI agents."""

import abc, os, subprocess, tempfile, shlex, logging
from datetime import datetime

logger = logging.getLogger("agent_fleet.adapters")


class BaseAgentAdapter(abc.ABC):
    """Abstract agent adapter. Subclass for each agent type."""

    @abc.abstractmethod
    def execute(self, prompt: str, work_dir: str, task_dir: str,
                timeout: int = 300, task_type: str = "code") -> dict:
        """Execute an agent. Returns {success, output, error, events}."""
        ...


class MockAdapter(BaseAgentAdapter):
    """Mock adapter for testing — echoes prompt back."""

    def execute(self, prompt, work_dir, task_dir, timeout=300, task_type="code"):
        events = []
        now = datetime.now().isoformat()
        events.append({"ts": now, "event": "task.started"})
        events.append({"ts": now, "event": "task.progress", "msg": f"Received {len(prompt)} chars prompt"})
        events.append({"ts": now, "event": "task.completed"})
        base = "[Mock] Task completed successfully.\n\n## Output\n\n"
        pad = "Mock execution output line for validation.\n" * 60
        output = base + pad
        if task_type == "acceptance":
            output += '\n## VERDICT\n```json\n{"pass": true, "evidence": ["all criteria satisfied"]}\n```\n'
        return {"success": True, "output": output, "error": "", "events": events}


class SubprocessAdapter(BaseAgentAdapter):
    """Generic subprocess-based adapter. Configurable command template."""

    def __init__(self, command: str = "claude -p --input-file {prompt_file}"):
        if not command or "{prompt_file}" not in command:
            raise ValueError("agent_command must contain '{prompt_file}' placeholder")
        self.command = command

    def execute(self, prompt, work_dir, task_dir, timeout=300, task_type="code"):
        events = []
        now = datetime.now().isoformat()
        events.append({"ts": now, "event": "task.started"})

        # prompt.md already written by engine._run(), adapter just reads it
        prompt_file = os.path.join(task_dir, "prompt.md")
        os.makedirs(task_dir, exist_ok=True)

        try:
            # Split template first, then replace — avoids breaking on spaces in paths
            cmd_list = [prompt_file if arg == "{prompt_file}" else arg for arg in shlex.split(self.command)]
            result = subprocess.run(
                cmd_list, cwd=work_dir, shell=False,
                capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace"
            )
            ok = result.returncode == 0
            now2 = datetime.now().isoformat()
            if ok:
                events.append({"ts": now2, "event": "task.completed"})
            else:
                events.append({"ts": now2, "event": "task.failed", "error": result.stderr[:500]})
            out_text = result.stdout
            err_text = result.stderr
            if len(out_text) > 50000:
                out_text = out_text[:50000] + f"\n...(truncated, original: {len(result.stdout)} chars)"
            if len(err_text) > 500:
                err_text = err_text[:500] + f"\n...(truncated, original: {len(result.stderr)} chars)"
            return {"success": ok, "output": out_text, "error": err_text, "events": events}
        except subprocess.TimeoutExpired:
            events.append({"ts": datetime.now().isoformat(), "event": "task.failed", "error": f"Timeout ({timeout}s)"})
            logger.error("SubprocessAdapter: timeout after %ds", timeout)
            return {"success": False, "output": "", "error": f"Timeout ({timeout}s)", "events": events}
        except FileNotFoundError:
            msg = f"Command not found: {cmd_list[0]}. Install the CLI (e.g. 'claude') or check agent_command in config.yaml."
            events.append({"ts": datetime.now().isoformat(), "event": "task.failed", "error": msg})
            logger.error("SubprocessAdapter: %s", msg)
            return {"success": False, "output": "", "error": msg, "events": events}
        except Exception as e:
            events.append({"ts": datetime.now().isoformat(), "event": "task.failed", "error": str(e)})
            logger.error("SubprocessAdapter: unexpected error: %s", e)
            return {"success": False, "output": "", "error": str(e), "events": events}


def get_adapter(config: dict) -> BaseAgentAdapter:
    """Factory: create adapter from config."""
    backend = config.get("backend", "subprocess")
    if backend == "mock":
        return MockAdapter()
    cmd = config.get("agent_command", "claude -p --input-file {prompt_file}")
    return SubprocessAdapter(cmd)
