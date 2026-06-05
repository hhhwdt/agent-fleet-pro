"""File storage: plan.json / status.json / progress.log I/O"""

import os, json, shutil, logging, tempfile, threading
from datetime import datetime

logger = logging.getLogger("agent_fleet.storage")
_status_locks = {}  # per-file locks for concurrent writes
_lock_guard = threading.Lock()


def _atomic_write(path: str, content: str):
    """Atomic write: write to temp file, then os.replace (atomic on all platforms)."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def init_run(work_dir, fleet_dir, plan, task):
    """Initialize a run: create directories and files."""
    run_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(work_dir, fleet_dir, run_id)
    roles_dir = os.path.join(run_dir, "roles")
    os.makedirs(roles_dir, exist_ok=True)
    now = datetime.now().isoformat()

    tasks_list = []
    for t in plan.get("tasks", []):
        tasks_list.append({
            "id": t["id"],
            "type": t.get("type", "code"),
            "name": t.get("name", t["id"]),
            "responsibility": t.get("responsibility", ""),
            "expected_files": t.get("expected_files", []),
            "depends_on": t.get("depends_on", []),
        })

    plan_data = {
        "summary": plan.get("summary", ""),
        "acceptance_criteria": plan.get("acceptance_criteria", []),
        "tasks": tasks_list,
    }
    with open(os.path.join(run_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)

    agents = {
        t["id"]: {"role": t.get("name", ""), "status": "pending", "round": 0}
        for t in tasks_list
    }

    status = {
        "run_id": run_id, "task": task, "status": "executing",
        "phase": "coding", "started_at": now,
        "phases": {
            "init": {"start": now, "end": now},
            "coding": {"start": now, "end": None},
            "testing": {"start": None, "end": None},
            "acceptance": {"start": None, "end": None},
        },
        "round": {"coding": 1, "testing": 0, "acceptance": 0},
        "max_acceptance_rounds": 5, "agents": agents,
        "progress": {
            "done": 0, "total": len(tasks_list),
            "by_type": {"code": 0, "test": 0, "acceptance": 0},
        },
    }
    with open(os.path.join(run_dir, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    logs = ["[启动] Agent Fleet", f"[启动] {task[:80]}"]
    for t in tasks_list:
        logs.append(f"  {t['id']}: {t['name']}")
    with open(os.path.join(run_dir, "progress.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(logs) + "\n")

    return {
        "run_id": run_id, "run_dir": run_dir,
        "roles_dir": roles_dir, "tasks": tasks_list,
    }


def _get_lock(path):
    with _lock_guard:
        if path not in _status_locks:
            _status_locks[path] = threading.Lock()
        return _status_locks[path]


def update_status(run_dir, **kwargs):
    """Deep-merge updates into status.json (thread-safe)."""
    sf = os.path.join(run_dir, "status.json")
    if not os.path.exists(sf):
        logger.warning("status.json not found: %s", sf)
        return
    lock = _get_lock(sf)
    with lock:
        try:
            with open(sf, "r", encoding="utf-8") as f:
                s = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read status.json: %s", e)
            return

        def deep(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    deep(d[k], v)
                else:
                    d[k] = v

        deep(s, kwargs)
        _atomic_write(sf, json.dumps(s, ensure_ascii=False, indent=2))


def append_log(run_dir, *lines):
    """Append lines to progress.log (thread-safe)."""
    lf = os.path.join(run_dir, "progress.log")
    lock = _get_lock(lf)
    with lock:
        try:
            with open(lf, "a", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
        except IOError as e:
            logger.error("Failed to write progress.log: %s", e)


def phase_start(run_dir, phase):
    now = datetime.now().isoformat()
    update_status(run_dir, phase=phase,
                  phases={phase: {"start": now, "end": None}})


def phase_end(run_dir, phase, next_phase=None):
    now = datetime.now().isoformat()
    upd = {"phases": {phase: {"end": now}}}
    if next_phase:
        upd["phase"] = next_phase
        upd["phases"][next_phase] = {"start": now, "end": None}
    update_status(run_dir, **upd)


def scan_runs(work_dir, fleet_dir=".fleet"):
    """Scan all runs, return status list compatible with Dashboard API."""
    fd = os.path.join(work_dir, fleet_dir)
    if not os.path.isdir(fd):
        return []

    result = []
    entries = []
    for name in os.listdir(fd):
        if not name.startswith("run-"):
            continue
        d = os.path.join(fd, name)
        if os.path.isdir(d):
            entries.append((d, name))

    entries.sort(key=lambda x: os.path.getmtime(x[0]), reverse=True)

    for run_dir, name in entries:
        run = {
            "id": name, "task": "", "status": "unknown", "phase": "",
            "done": 0, "total": 0, "plan_tasks": [], "completed": [],
            "failed_list": [], "running_list": [],
            "log_tail": [], "log_full": [],
            "started_at": "", "finished_at": "", "phases": {}, "round": {},
            "mtime": os.path.getmtime(run_dir),
        }

        sf = os.path.join(run_dir, "status.json")
        if os.path.exists(sf):
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    s = json.load(f)
                for k in ["task", "status", "phase", "started_at",
                           "finished_at", "phases", "round"]:
                    run[k] = s.get(k, run[k])
                prog = s.get("progress", {})
                run["done"] = prog.get("done", 0)
                run["total"] = prog.get("total", 0)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to read %s: %s", sf, e)

        pf = os.path.join(run_dir, "plan.json")
        if os.path.exists(pf):
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    run["plan_tasks"] = json.load(f).get("tasks", [])
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to read %s: %s", pf, e)

        # Events-driven status detection (fallback: log parsing)
        from .events import get_task_status, get_task_errors
        for item in os.listdir(run_dir):
            ip = os.path.join(run_dir, item)
            if not os.path.isdir(ip) or item in ("roles", "analysis"):
                continue
            st = get_task_status(ip)
            if st == "completed":
                run["completed"].append(item)
            elif st in ("running", "ready"):
                run["running_list"].append(item)
            elif st in ("failed", "failed_retryable", "failed_terminal", "cancelled"):
                run["failed_list"].append(item)
            elif st == "pending":
                # Events-only: no log parsing fallback. If no events.ndjson, task hasn't started.
                pass

        run["done"] = max(run["done"], len(run["completed"]))

        lf = os.path.join(run_dir, "progress.log")
        if os.path.exists(lf):
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                run["log_full"] = lines
                run["log_tail"] = lines[-15:] if len(lines) > 15 else lines
            except (IOError, UnicodeDecodeError) as e:
                logger.warning("Failed to read %s: %s", lf, e)

        result.append(run)
    return result


def delete_run(work_dir, fleet_dir, run_id):
    """Delete a run directory."""
    run_dir = os.path.join(work_dir, fleet_dir, run_id)
    if not os.path.isdir(run_dir):
        logger.warning("Run not found: %s", run_dir)
        return False
    try:
        shutil.rmtree(run_dir)
        return True
    except OSError as e:
        logger.error("Failed to delete %s: %s", run_dir, e)
        return False
