"""Agent Fleet 启动入口 — python run.py"""

import os, sys, yaml

# 确保包路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_fleet.server import start as start_server


def load_config():
    """加载配置：config.yaml <- config.local.yaml 覆盖"""
    cfg = {}
    for fn in ["config.yaml", "config.local.yaml"]:
        if os.path.exists(fn):
            with open(fn, "r", encoding="utf-8") as f:
                cfg.update(yaml.safe_load(f) or {})
    return cfg


if __name__ == "__main__":
    config = load_config()
    port = config.get("port", 8765)
    print(f"Agent Fleet v0.1.0")
    print(f"Dashboard: http://127.0.0.1:{port}")
    start_server(config)
