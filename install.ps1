# Agent Fleet Windows 安装脚本
# 以管理员身份运行或在项目目录下执行: .\install.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== Agent Fleet Installer ===" -ForegroundColor Cyan

# 1. Python 依赖
Write-Host "[1/3] Installing Python dependencies..." -ForegroundColor Yellow
pip install -e . 2>&1 | Out-Null
Write-Host "  Done." -ForegroundColor Green

# 2. SKILL.md
Write-Host "[2/3] Installing Claude Code skill..." -ForegroundColor Yellow
$skillDir = "$env:USERPROFILE\.claude\skills\agent-fleet-pro"
New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
Copy-Item -Force "SKILL.md" "$skillDir\SKILL.md"
Write-Host "  SKILL.md -> $skillDir" -ForegroundColor Green

# 3. config
Write-Host "[3/3] Setting up config..." -ForegroundColor Yellow
if (-not (Test-Path "config.local.yaml")) {
    $workDir = (Get-Location).Path -replace '\', '\'
    "work_dir: `"$workDir`"" | Out-File -FilePath "config.local.yaml" -Encoding utf8
    Write-Host "  config.local.yaml created with work_dir = $workDir" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installation complete! Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit $skillDir\SKILL.md -> change FLEET_DIR path"
Write-Host "  2. Run: agent-fleet dashboard"
Write-Host "  3. Open http://localhost:8765"
