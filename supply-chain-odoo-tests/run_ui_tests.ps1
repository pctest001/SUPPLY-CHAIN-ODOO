# UI 自动化测试运行脚本（在宿主机、主项目目录下执行）
#
# 前置条件：
#   1. 被测 Odoo 容器已在 8069 运行（docker compose up -d）
#   2. 容器内已安装 Playwright + Chromium（首次需执行一次）：
#        docker compose exec -u root odoo bash -c "pip install -q --break-system-packages pytest playwright pytest-playwright && python3 -m playwright install chromium && python3 -m playwright install-deps chromium"
#      （宿主机受代理白名单限制，无法安装浏览器，故装在可直连外网的容器内）
#
# 用法：
#   .\supply-chain-odoo-tests\run_ui_tests.ps1            # 跑全部 UI 用例
#   .\supply-chain-odoo-tests\run_ui_tests.ps1 -ExtraArgs "test_b01_login.py"   # 只跑某文件
param(
    [string]$Container = "supply-chain-odoo-odoo-1",
    [string]$BaseUrl = "http://localhost:8069",
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = 'Stop'
$UiDir = Join-Path $PSScriptRoot "ui_tests"

# 逐个同步用例文件到容器内 /mnt/ui_tests
# （Windows 上目录级 docker cp 行为不稳定，逐文件更可靠）
foreach ($f in Get-ChildItem $UiDir -File) {
    docker cp "$($UiDir)/$($f.Name)" "${Container}:/mnt/ui_tests/$($f.Name)"
}

docker compose exec -T odoo bash -c "cd /mnt/ui_tests && python3 -m pytest -v --base-url=$BaseUrl -p no:cacheprovider $ExtraArgs"
