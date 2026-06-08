"""Agent Fleet CLI — full pipeline management.

Usage:
    agent-fleet run "task"         # Full pipeline: plan + dispatch + monitor
    agent-fleet resume <run-id>    # Resume interrupted run
    agent-fleet cancel <run-id>    # Cancel a run
    agent-fleet dashboard          # Start monitoring dashboard
    agent-fleet list               # List all runs
    agent-fleet clean --force      # Delete completed runs
"""

import os, yaml, argparse, json, sys
from datetime import datetime
from .engine import AgentFleet, init_pipeline, decomposition_prompt, simple_plan, generate_report
from .storage import scan_runs, delete_run, update_status, append_log


def load_config():
    cfg = {}
    for fn in ["config.yaml", "config.local.yaml"]:
        if os.path.exists(fn):
            with open(fn, "r", encoding="utf-8") as f:
                cfg.update(yaml.safe_load(f) or {})
    return cfg


def cmd_run(args):
    """Full pipeline: plan + dispatch + report."""
    config = load_config()
    if args.work_dir:
        config["work_dir"] = args.work_dir
    fleet = AgentFleet(config)
    meta = fleet.run(args.task)
    print(f"\nDone! Run ID: {meta['run_id']}")
    print(f"Report: {meta['run_dir']}/FINAL_REPORT.md")
    print(f"Dashboard: http://{config.get('host','127.0.0.1')}:{config.get('port',8765)}")


def cmd_resume(args):
    """Resume a run: re-dispatch incomplete tasks."""
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    run_dir = os.path.join(work_dir, fleet_dir, args.run_id)
    if not os.path.isdir(run_dir):
        print(f"Run not found: {args.run_id}"); sys.exit(1)

    # Load plan and check which tasks are incomplete
    with open(os.path.join(run_dir, "plan.json"), "r", encoding="utf-8") as f:
        plan = json.load(f)
    tasks = plan.get("tasks", [])
    from .events import get_task_status
    incomplete = [t for t in tasks if get_task_status(os.path.join(run_dir, t["id"])) not in ("completed",)]
    if not incomplete:
        print("All tasks already completed. Run 'agent-fleet report' to generate FINAL_REPORT.md.")
        return

    update_status(run_dir, status="executing")
    append_log(run_dir, f"[Resume] Re-dispatching {len(incomplete)} incomplete tasks")
    fleet = AgentFleet(config)
    # Re-dispatch incomplete tasks respecting dependency order
    done_ids = set(t["id"] for t in tasks if t["id"] not in set(i["id"] for i in incomplete))
    phase = json.load(open(os.path.join(run_dir, "status.json"), "r", encoding="utf-8")).get("phase", "coding")
    if phase in ("coding", "code", "init"):
        fleet._dispatch_type("code", tasks, run_dir, done_ids)
    if phase in ("testing", "test", "coding", "code"):
        fleet._dispatch_type("test", tasks, run_dir, done_ids)
    if phase in ("acceptance", "testing", "test", "coding", "code"):
        fleet._dispatch_type("acceptance", tasks, run_dir, done_ids)

def cmd_cancel(args):
    """Cancel a running task."""
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    run_dir = os.path.join(work_dir, fleet_dir, args.run_id)
    if not os.path.isdir(run_dir):
        print(f"Run not found: {args.run_id}")
        sys.exit(1)
    update_status(run_dir, status="cancelled", finished_at=datetime.now().isoformat())
    append_log(run_dir, "[Cancel] Task cancelled by user")
    print(f"Cancelled: {args.run_id}")


def cmd_init(args):
    """Initialize a pipeline run (lightweight, no dispatch)."""
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    plan = simple_plan(args.task)
    meta = init_pipeline(work_dir, fleet_dir, args.task, plan)
    print(f"Pipeline initialized: {meta['run_id']}")
    print(f"Tasks: {len(meta['tasks'])} ({', '.join(t['id'] for t in meta['tasks'])})")
    print(f"Next: agent-fleet run '{args.task}'  or  agent-fleet dashboard")


def cmd_report(args):
    """Generate FINAL_REPORT.md for a completed run."""
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    run_dir = os.path.join(work_dir, fleet_dir, args.run_id)
    if not os.path.isdir(run_dir):
        print(f"Run not found: {args.run_id}")
        return
    plan_file = os.path.join(run_dir, "plan.json")
    status_file = os.path.join(run_dir, "status.json")
    if not os.path.exists(plan_file):
        print("plan.json not found"); return
    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)
    task = ""
    if os.path.exists(status_file):
        with open(status_file, "r", encoding="utf-8") as f:
            task = json.load(f).get("task", "")
    # Check actual acceptance result
    from .engine import AgentFleet
    fleet = AgentFleet({})
    acc_file = os.path.join(run_dir, "acceptor-01", "acceptance-report.md")
    verdict = os.path.exists(acc_file) and fleet._check_acceptance(run_dir)
    tasks = plan.get("tasks", [])
    report_path = generate_report(run_dir, task, tasks, verdict, args.run_id)
    print(f"Report: {report_path} (verdict: {'PASS' if verdict else 'FAIL'})")


def cmd_dashboard(args):
    config = load_config()
    from .server import start
    start(config)


def cmd_list(args):
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    runs = scan_runs(work_dir, fleet_dir)

    if not runs:
        print("No runs found.")
        return

    print(f"{'RUN ID':<24} {'STATUS':<12} {'DONE':<6} TASK")
    print("-" * 80)
    for r in runs:
        print(f"{r['id']:<24} {r['status']:<12} {r['done']}/{r['total']:<4}  {r['task'][:40]}")


def cmd_clean(args):
    if not args.force:
        print("This will delete all completed runs. Use --force to confirm.")
        return
    config = load_config()
    work_dir = os.path.abspath(config.get("work_dir", "."))
    fleet_dir = config.get("fleet_dir", ".fleet")
    runs = scan_runs(work_dir, fleet_dir)
    deleted = 0
    for r in runs:
        if r["status"] in ("done", "force_stopped"):
            delete_run(work_dir, fleet_dir, r["id"])
            deleted += 1
            print(f"Deleted: {r['id']}")
    print(f"Cleaned {deleted} runs.")


def main():
    parser = argparse.ArgumentParser(
        prog="agent-fleet",
        description="Agent Fleet — AI agent pipeline & dashboard. NOT an agent itself.",
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Full pipeline: plan + dispatch")
    p_run.add_argument("task", help="Task description")
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="Resume an interrupted run")
    p_resume.add_argument("run_id", help="Run ID to resume")
    p_resume.set_defaults(func=cmd_resume)

    p_cancel = sub.add_parser("cancel", help="Cancel a running task")
    p_cancel.add_argument("run_id", help="Run ID to cancel")
    p_cancel.set_defaults(func=cmd_cancel)

    p_init = sub.add_parser("init", help="Initialize pipeline (no dispatch)")
    p_init.add_argument("task", help="Task description")
    p_init.set_defaults(func=cmd_init)

    p_report = sub.add_parser("report", help="Generate FINAL_REPORT.md")
    p_report.add_argument("run_id", help="Run ID")
    p_report.set_defaults(func=cmd_report)

    p_dash = sub.add_parser("dashboard", help="Start monitoring dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    p_list = sub.add_parser("list", help="List all runs")
    p_list.set_defaults(func=cmd_list)

    p_clean = sub.add_parser("clean", help="Delete completed runs")
    p_clean.add_argument("--force", "-f", action="store_true")
    p_clean.set_defaults(func=cmd_clean)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
