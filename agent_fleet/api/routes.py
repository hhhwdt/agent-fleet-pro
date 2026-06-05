"""All Fleet API routes. Imported by server.py to register with Flask app."""

import os, json, re, subprocess, shlex
from flask import request, jsonify, send_file
from ..storage import scan_runs, delete_run
from ..events import get_task_status, get_task_errors

TEMPLATE_DIR = None  # Set by server.py

def _safe(value: str, base_dir: str) -> str:
    """Validate path: normpath + realpath + reject .. segments."""
    value = value.replace("\\", "/")
    # Reject any path segment that is exactly ".."
    for seg in value.split("/"):
        if seg == "..":
            return ""
    value = re.sub(r"[^a-zA-Z0-9\-_./]", "", value)
    full = os.path.realpath(os.path.join(base_dir, os.path.normpath(value)))
    real_base = os.path.realpath(base_dir)
    if not full.startswith(real_base + os.sep) and full != real_base:
        return ""
    return os.path.relpath(full, base_dir)


def register_routes(app):
    """Register all API routes with the Flask app."""
    global TEMPLATE_DIR
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

    @app.before_request
    def _options():
        if request.method == "OPTIONS": return "", 204

    @app.after_request
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = app.config.get("CORS_ORIGINS", "http://localhost:*")
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @app.route("/")
    def index():
        return send_file(os.path.join(TEMPLATE_DIR, "dashboard.html"))

    @app.route("/api/status")
    def api_status():
        return jsonify({"work_dir": app.config["WORK_DIR"]})

    @app.route("/api/fleet-runs")
    def api_fleet_runs():
        d = request.args.get("dir", app.config["WORK_DIR"])
        return jsonify({"runs": scan_runs(d, app.config["FLEET_DIR"])})

    @app.route("/api/fleet-task-log")
    def api_fleet_task_log():
        run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
        task_id = _safe(request.args.get("task", ""), app.config["WORK_DIR"])
        lf = os.path.join(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id, task_id, "output.log")
        lines = []
        if os.path.exists(lf):
            try:
                with open(lf, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
            except (IOError, UnicodeDecodeError): pass
        return jsonify({"run": run_id, "task": task_id, "log": lines})

    @app.route("/api/fleet-task-result")
    def api_fleet_task_result():
        run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
        task_id = _safe(request.args.get("task", ""), app.config["WORK_DIR"])
        td = os.path.join(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id, task_id)
        results = {}
        for fn in ["result.md", "test-report.md", "acceptance-report.md"]:
            fp = os.path.join(td, fn)
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        results[fn] = f.read()
                except (IOError, UnicodeDecodeError): pass
        return jsonify({"run": run_id, "task": task_id, "results": results})

    @app.route("/api/fleet-task-prompt")
    def api_fleet_task_prompt():
        run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
        task_id = _safe(request.args.get("task", ""), app.config["WORK_DIR"])
        pf = os.path.join(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id, task_id, "prompt.md")
        prompt = ""
        if os.path.exists(pf):
            try:
                with open(pf, "r", encoding="utf-8") as f: prompt = f.read()
            except (IOError, UnicodeDecodeError): pass
        return jsonify({"run": run_id, "task": task_id, "prompt": prompt})

    @app.route("/api/fleet-run-report")
    def api_fleet_run_report():
        run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
        data = {"run": run_id, "report": "", "analysis": ""}
        for key, fname in [("report", "FINAL_REPORT.md"), ("analysis", "analysis/requirement-analysis.md")]:
            fp = os.path.join(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id, fname)
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f: data[key] = f.read()
                except (IOError, UnicodeDecodeError): pass
        return jsonify(data)

    @app.route("/api/fleet-run-changes")
    def api_fleet_run_changes():
        run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
        work_dir = app.config["WORK_DIR"]
        changes = {}
        # Git diff first
        try:
            for cmd, tag in [(["git","-C",work_dir,"diff","--name-only","HEAD"],"git"), (["git","-C",work_dir,"ls-files","--others","--exclude-standard"],"new")]:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    for fp in r.stdout.strip().split("\n"):
                        fp = fp.strip()
                        if not fp: continue
                        full = os.path.join(work_dir, fp)
                        if os.path.isfile(full) and fp not in changes:
                            try:
                                with open(full, "r", encoding="utf-8") as fc: changes[fp] = {"agents":[tag],"content":fc.read()}
                            except Exception: changes[fp] = {"agents":[tag],"content":"(binary)"}
        except Exception: pass
        # Fallback to result.md scan
        if not changes:
            base = os.path.join(work_dir, app.config["FLEET_DIR"], run_id)
            if os.path.isdir(base):
                for item in sorted(os.listdir(base)):
                    td = os.path.join(base, item)
                    if not os.path.isdir(td): continue
                    rf = os.path.join(td, "result.md")
                    if not os.path.exists(rf): continue
                    try:
                        with open(rf, "r", encoding="utf-8") as f: text = f.read()
                        files = re.findall(r'[\w./\-]+\.(?:py|js|ts|vue|html|css|json|yaml|yml|md|txt|sh|bat|go|rs|java|kt|cpp|c|h)', text)
                        for fp in set(f.strip().lstrip(".\/") for f in files):
                            full = os.path.join(work_dir, fp)
                            if os.path.isfile(full) and fp not in changes:
                                try:
                                    with open(full, "r", encoding="utf-8") as fc: changes[fp] = {"agents":[item],"content":fc.read()}
                                except Exception: changes[fp] = {"agents":[item],"content":"(binary)"}
                    except Exception: pass
        return jsonify({"run": run_id, "changes": changes})

    @app.route("/api/fleet-task-sandbox")
def api_fleet_task_sandbox():
    run_id = _safe(request.args.get("run", ""), app.config["WORK_DIR"])
    task_id = _safe(request.args.get("task", ""), app.config["WORK_DIR"])
    sf = os.path.join(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id, task_id, "sandbox.json")
    if os.path.exists(sf):
        try:
            with open(sf, "r", encoding="utf-8") as f:
                return jsonify({"run": run_id, "task": task_id, "sandbox": json.load(f)})
        except (IOError, json.JSONDecodeError): pass
    return jsonify({"run": run_id, "task": task_id, "sandbox": None})


@app.route("/api/fleet-runs/delete", methods=["POST"])
    def api_fleet_runs_delete():
        data = request.get_json() or {}
        run_id = _safe(data.get("run", ""))
        if not run_id: return jsonify({"ok": False, "error": "missing run id"}), 400
        ok = delete_run(app.config["WORK_DIR"], app.config["FLEET_DIR"], run_id)
        return jsonify({"ok": True if ok else False, "error": "" if ok else "not found"})
