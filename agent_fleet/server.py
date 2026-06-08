"""Agent Fleet Dashboard server — App factory + WebSocket watcher."""

import os, json, time, threading, sys, logging
from flask import Flask
from flask_socketio import SocketIO

logger = logging.getLogger("agent_fleet.server")
logging.basicConfig(level=logging.WARNING, format="[%(name)s] %(levelname)s: %(message)s")

from .api.routes import register_routes
from .storage import scan_runs

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
register_routes(app)

_watcher_running = False


# ---- WebSocket watcher ----

def _fleet_watcher():
    work_dir = app.config["WORK_DIR"]
    fleet_dir = app.config["FLEET_DIR"]
    last_runs_json = ""
    log_mtimes = {}

    while _watcher_running:
        try:
            runs = scan_runs(work_dir, fleet_dir)
            runs_json = json.dumps([{
                "id": r["id"], "status": r["status"], "phase": r.get("phase", ""),
                "task": r["task"], "done": r["done"], "total": r["total"],
                "plan_tasks": r.get("plan_tasks", []),
                "completed": r.get("completed", []),
                "running_list": r.get("running_list", []),
                "failed_list": r.get("failed_list", []),
                "started_at": r.get("started_at", ""),
                "finished_at": r.get("finished_at", ""),
                "phases": r.get("phases", {}), "round": r.get("round", {}),
            } for r in runs], sort_keys=True)

            if runs_json != last_runs_json:
                last_runs_json = runs_json
                socketio.emit("runs_updated", {"runs": runs})

            for r in runs:
                run_dir = os.path.join(work_dir, fleet_dir, r["id"])
                for item in os.listdir(run_dir):
                    ip = os.path.join(run_dir, item)
                    if not os.path.isdir(ip): continue
                    lf = os.path.join(ip, "output.log")
                    if not os.path.exists(lf): continue
                    try:
                        mtime = os.path.getmtime(lf)
                        key = f"{r['id']}/{item}"
                        if log_mtimes.get(key) != mtime:
                            log_mtimes[key] = mtime
                            with open(lf, "r", encoding="utf-8") as f:
                                lines = [l.strip() for l in f.readlines() if l.strip()]
                            socketio.emit("task_log", {"run": r["id"], "task": item, "log": lines})
                    except Exception as e:
                        logger.warning("watcher: log check failed: %s", e)
        except Exception as e:
            logger.error("watcher: scan failed: %s", e)
        time.sleep(2)


@socketio.on("connect")
def _on_connect():
    runs = scan_runs(app.config["WORK_DIR"], app.config["FLEET_DIR"])
    socketio.emit("runs_updated", {"runs": runs})


# ---- Start ----

def start(config):
    global _watcher_running
    app.config["WORK_DIR"] = os.path.abspath(config.get("work_dir", "."))
    app.config["FLEET_DIR"] = config.get("fleet_dir", ".fleet")
    host = config.get("host", "127.0.0.1")
    port = config.get("port", 8765)

    _watcher_running = True
    threading.Thread(target=_fleet_watcher, daemon=True).start()

    try:
        print(f"[Agent Fleet] http://{host}:{port}  (WebSocket enabled)")
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True, debug=False)
    except OSError as e:
        if "Address already in use" in str(e) or "10048" in str(e) or "10013" in str(e):
            print(f"[Agent Fleet] Port {port} in use. Change port in config.yaml.")
            sys.exit(1)
        raise
    finally:
        _watcher_running = False
