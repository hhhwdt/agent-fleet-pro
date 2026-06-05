"""Test storage module."""
import os, sys, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_fleet.storage import init_run, scan_runs, update_status, append_log, delete_run
from agent_fleet.events import append_event

WORK_DIR = tempfile.mkdtemp()

def test_init_run():
    plan = {"summary":"test","acceptance_criteria":["works"],"tasks":[{"id":"c1","type":"code","name":"Coder","depends_on":[]}]}
    meta = init_run(WORK_DIR, ".fleet", plan, "test task")
    assert os.path.exists(meta["run_dir"])
    assert os.path.exists(os.path.join(meta["run_dir"], "plan.json"))
    assert os.path.exists(os.path.join(meta["run_dir"], "status.json"))
    assert os.path.exists(os.path.join(meta["run_dir"], "progress.log"))
    assert meta["tasks"][0]["id"] == "c1"
    delete_run(WORK_DIR, ".fleet", meta["run_id"])

def test_scan_runs():
    plan = {"tasks":[{"id":"c1","type":"code","name":"T","depends_on":[]}]}
    meta = init_run(WORK_DIR, ".fleet", plan, "test")
    runs = scan_runs(WORK_DIR, ".fleet")
    assert any(r["id"] == meta["run_id"] for r in runs)
    delete_run(WORK_DIR, ".fleet", meta["run_id"])

def test_scan_runs_with_events():
    plan = {"tasks":[{"id":"c1","type":"code","name":"T","depends_on":[]}]}
    meta = init_run(WORK_DIR, ".fleet", plan, "test events")
    append_event(os.path.join(meta["run_dir"], "c1"), "task.started")
    append_event(os.path.join(meta["run_dir"], "c1"), "task.completed")
    runs = scan_runs(WORK_DIR, ".fleet")
    r = [x for x in runs if x["id"] == meta["run_id"]][0]
    assert "c1" in r["completed"]
    delete_run(WORK_DIR, ".fleet", meta["run_id"])

def test_update_status():
    plan = {"tasks":[{"id":"c1","type":"code","name":"T","depends_on":[]}]}
    meta = init_run(WORK_DIR, ".fleet", plan, "test")
    update_status(meta["run_dir"], phase="testing", status="testing")
    sf = os.path.join(meta["run_dir"], "status.json")
    with open(sf) as f:
        s = json.load(f)
    assert s["phase"] == "testing"
    delete_run(WORK_DIR, ".fleet", meta["run_id"])

def test_delete_run():
    plan = {"tasks":[{"id":"c1","type":"code","name":"T","depends_on":[]}]}
    meta = init_run(WORK_DIR, ".fleet", plan, "test")
    assert delete_run(WORK_DIR, ".fleet", meta["run_id"])
    assert not os.path.exists(meta["run_dir"])
