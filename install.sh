#!/bin/bash
# Agent Fleet Linux/macOS 安装脚本

set -e
echo -e "\033[36m=== Agent Fleet Installer ===\033[0m"

# 1. Python deps
echo -e "\033[33m[1/3] Installing Python dependencies...\033[0m"
pip install -e . > /dev/null 2>&1
echo -e "\033[32m  Done.\033[0m"

# 2. SKILL.md
echo -e "\033[33m[2/3] Installing Claude Code skill...\033[0m"
SKILL_DIR="$HOME/.claude/skills/agent-fleet-pro"
mkdir -p "$SKILL_DIR"
cp SKILL.md "$SKILL_DIR/SKILL.md"
echo -e "\033[32m  SKILL.md -> $SKILL_DIR\033[0m"

# 3. config
echo -e "\033[33m[3/3] Setting up config...\033[0m"
if [ ! -f "config.local.yaml" ]; then
    echo "work_dir: \"$(pwd)\"" > config.local.yaml
    echo -e "\033[32m  config.local.yaml created\033[0m"
fi

echo ""
echo -e "\033[36mInstallation complete! Next steps:\033[0m"
echo "  1. Edit $SKILL_DIR/SKILL.md -> change FLEET_DIR path"
echo "  2. Run: agent-fleet dashboard"
echo "  3. Open http://localhost:8765"
