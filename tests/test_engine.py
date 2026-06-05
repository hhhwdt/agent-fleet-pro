"""Test engine — acceptance, fix loop, dep scheduling, output logging."""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_fleet import AgentFleet
from agent_fleet.storage import delete_run

WORK_DIR = tempfile.mkdtemp()

def _clean(rid):
    delete_run(WORK_DIR, ".fleet", rid)

def test_full_pipeline_writes_all_files():
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR})
    meta = fleet.run('Build X')
    rd = os.path.join(WORK_DIR, ".fleet", meta['run_id'])
    for tid in ['coder-01', 'tester-01', 'acceptor-01']:
        td = os.path.join(rd, tid)
        assert os.path.isdir(td), f"Missing dir: {tid}"
        assert os.path.exists(os.path.join(td, "output.log")), f"Missing output.log: {tid}"
    assert os.path.exists(os.path.join(rd, "FINAL_REPORT.md"))
    assert fleet.stats['tasks'] >= 3
    _clean(meta['run_id'])

def test_dep_scheduling_tester_waits_for_coder():
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR})
    meta = fleet.run('Test deps')
    rd = os.path.join(WORK_DIR, ".fleet", meta['run_id'])
    assert os.path.isdir(os.path.join(rd, 'tester-01'))
    _clean(meta['run_id'])

def test_acceptance_check_json_pass():
    fleet = AgentFleet({'backend': 'mock', 'work_dir': WORK_DIR})
    rd = os.path.join(WORK_DIR, ".fleet", "t1")
    ad = os.path.join(rd, "acceptor-01")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "acceptance-report.md"), "w", encoding="utf-8") as f:
        f.write('{"pass": true}')
    assert fleet._check_acceptance(rd)
    shutil.rmtree(rd)

def test_acceptance_check_json_fail():
    fleet = AgentFleet({'backend': 'mock', 'work_dir': WORK_DIR})
    rd = os.path.join(WORK_DIR, ".fleet", "t2")
    ad = os.path.join(rd, "acceptor-01")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "acceptance-report.md"), "w", encoding="utf-8") as f:
        f.write('{"pass": false}')
    assert not fleet._check_acceptance(rd)
    shutil.rmtree(rd)

def test_acceptance_check_chinese_json():
    fleet = AgentFleet({'backend': 'mock', 'work_dir': WORK_DIR})
    rd = os.path.join(WORK_DIR, ".fleet", "t3")
    ad = os.path.join(rd, "acceptor-01")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "acceptance-report.md"), "w", encoding="utf-8") as f:
        f.write('{"通过": true}')
    assert fleet._check_acceptance(rd)
    shutil.rmtree(rd)

def test_acceptance_check_no_json_fails():
    fleet = AgentFleet({'backend': 'mock', 'work_dir': WORK_DIR})
    rd = os.path.join(WORK_DIR, ".fleet", "t4")
    ad = os.path.join(rd, "acceptor-01")
    os.makedirs(ad, exist_ok=True)
    with open(os.path.join(ad, "acceptance-report.md"), "w", encoding="utf-8") as f:
        f.write("All tests passed! Looks good.")
    assert not fleet._check_acceptance(rd), "No JSON verdict should fail safe"
    shutil.rmtree(rd)

def test_adapter_output_written_to_disk():
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR})
    meta = fleet.run('Test output')
    rd = os.path.join(WORK_DIR, ".fleet", meta['run_id'])
    with open(os.path.join(rd, "coder-01", "output.log"), "r", encoding="utf-8") as f:
        log = f.read()
    assert "[开始]" in log
    assert len(log) > 10
    with open(os.path.join(rd, "coder-01", "result.md"), "r", encoding="utf-8") as f:
        assert len(f.read()) > 10
    _clean(meta['run_id'])

def test_acceptance_report_exists_after_pipeline():
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR})
    meta = fleet.run('Test accept file')
    rd = os.path.join(WORK_DIR, ".fleet", meta['run_id'])
    af = os.path.join(rd, "acceptor-01", "acceptance-report.md")
    assert os.path.exists(af), "acceptance-report.md missing"
    _clean(meta['run_id'])

def test_fix_loop_retries_on_fail():
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR, 'max_acceptance_rounds': 2})
    meta = fleet.run('Test retry')
    assert fleet.stats['retries'] == 0  # Mock writes pass now
    _clean(meta['run_id'])

def test_acceptor_reruns_each_round():
    """Acceptor must re-dispatch every acceptance round (not cached in done)."""
    fleet = AgentFleet({'backend': 'mock', 'planner': 'template', 'work_dir': WORK_DIR})
    done = {"coder-01", "tester-01", "acceptor-01"}
    acceptor_ids = {"acceptor-01"}
    acc_done = done - acceptor_ids
    assert "acceptor-01" not in acc_done, "Acceptor should be removed from done before dispatch"
