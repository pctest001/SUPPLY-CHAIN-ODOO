# verify.ps1 - supply-chain-odoo-tests 一键验证
# 起实例 -> 装模块 -> 跑 pytest -> 打印自愈审计
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

function Wait-Odoo {
    for ($i = 1; $i -le 40; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:18069/web/login" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { Write-Host "odoo ready"; return }
        } catch { }
        Start-Sleep -Seconds 3
    }
    Write-Error "odoo 未在超时内就绪"
    exit 1
}

# 1) 起数据库
docker compose -f docker-compose.test.yml up -d db

# 2) 若主 odoo 在跑则先停，避免与初始化抢建表
docker compose -f docker-compose.test.yml stop odoo 2>$null

# 3) 初始化测试库并安装模块（幂等）
docker compose -f docker-compose.test.yml run --rm odoo odoo `
    -i supply_chain_demo,sc_ai,sc_log_trace -d test_supplychain --stop-after-init

# 4) 启动主 odoo 并等待就绪
docker compose -f docker-compose.test.yml up -d odoo
Wait-Odoo

# 5) 跑测试
python -m pytest -v --junitxml=report.xml
$rc = $LASTEXITCODE

# 6) 展示自愈审计（UTF-8，避免控制台乱码）
Write-Host "`n=== healer_audit.jsonl ==="
if (Test-Path healer_audit.jsonl) { Get-Content healer_audit.jsonl -Encoding utf8 }

Pop-Location
exit $rc
