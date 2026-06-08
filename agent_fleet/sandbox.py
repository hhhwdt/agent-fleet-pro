"""Sandbox — execute agent-generated code with timeout. NOT a security sandbox — runs as current user. For local dev use only."""

import os, subprocess, json, time
from dataclasses import dataclass


@dataclass
class SandboxResult:
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    success: bool = False


class SubprocessSandbox:
    """Execute code in subprocess with timeout protection."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def execute(self, command: list, cwd: str = None,
                timeout: int = None) -> SandboxResult:
        t0 = time.time()
        try:
            r = subprocess.run(
                command, cwd=cwd or ".", capture_output=True, text=True,
                timeout=timeout or self.timeout,
                encoding="utf-8", errors="replace"
            )
            return SandboxResult(
                exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr,
                duration_seconds=time.time() - t0, success=r.returncode == 0
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(timed_out=True, duration_seconds=time.time() - t0)
        except Exception as e:
            return SandboxResult(stderr=str(e), duration_seconds=time.time() - t0)

    def run_tests(self, test_dir: str, timeout: int = None) -> SandboxResult:
        return self.execute(
            ["python", "-m", "pytest", test_dir, "-v", "--tb=short"],
            cwd=test_dir, timeout=timeout or self.timeout
        )

    def run_script(self, script_path: str, args: list = None,
                   timeout: int = None) -> SandboxResult:
        cmd = ["python", script_path] + (args or [])
        return self.execute(cmd, cwd=os.path.dirname(script_path),
                            timeout=timeout or self.timeout)
