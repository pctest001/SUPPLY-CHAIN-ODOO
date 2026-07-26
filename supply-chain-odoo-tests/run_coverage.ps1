# One-click line coverage for custom_addons (real coverage, not fake 0%).
#
# Why this design (Odoo = long-running + threads/gevent + --dev reload subprocess):
#   - `coverage run -m odoo` does NOT work: Odoo forks/re-execs subprocesses, the
#     process actually serving RPC is not under coverage -> line_bits=0 (fake 0%).
#   - Instead: sitecustomize + COVERAGE_PROCESS_START makes EVERY python process
#     (incl. reload subprocess) auto-start coverage.process_startup(); parallel mode
#     writes one data file per process.
#   - .coveragerc has sigterm=true: `docker stop` SIGTERM flushes data to disk
#     (does not rely on Odoo atexit).
#   - Finally `coverage combine`, and the REPORT is generated INSIDE the container
#     (posix paths match the data; reporting on Windows host mismatches /mnt paths
#     and shows fake 0%).
#
# Prereq: docker-compose.test.yml injects COVERAGE_PROCESS_START / PYTHONPATH,
#         and covdata/ contains sitecustomize/sitecustomize.py + .coveragerc.
#
# Usage: powershell -ExecutionPolicy Bypass -File run_coverage.ps1

# NOTE: keep "Continue" -- docker/pip write harmless progress/warnings to stderr,
# which would kill the script under "Stop" (NativeCommandError).
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$compose = "docker-compose.test.yml"

Write-Host "[1/7] Ensure containers are up..."
docker compose -f $compose up -d odoo *> $null
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

Write-Host "[2/7] Ensure coverage is installed in container (idempotent, self-heal after volume rebuild)..."
docker compose -f $compose exec -T odoo python3 -m pip install --break-system-packages --quiet coverage *> $null
docker compose -f $compose exec -T odoo python3 -c "import coverage; print('coverage', coverage.__version__)"
if ($LASTEXITCODE -ne 0) { throw "coverage not importable in container" }

Write-Host "[3/7] Clean old coverage data (keep .coveragerc / sitecustomize)..."
Get-ChildItem ./covdata -Force | Where-Object { $_.Name -eq '.coverage' -or $_.Name -like '.coverage.*' } | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "[4/7] Restart odoo for a clean measured run, wait until ready..."
docker compose -f $compose restart odoo *> $null
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri http://localhost:18069/web/login -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { Write-Host "    odoo ready after $i tries"; $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 3
}
if (-not $ready) { docker compose -f $compose logs --tail=30 odoo; throw "odoo not ready" }

Write-Host "[5/7] Run full RPC test suite..."
python -m pytest -q --junitxml=report.xml
$testRc = $LASTEXITCODE

Write-Host "[6/7] Stop odoo gracefully to flush coverage data, then combine..."
docker compose -f $compose stop odoo *> $null
Start-Sleep -Seconds 6
python -m coverage combine --data-file=./covdata/.coverage ./covdata
if ($LASTEXITCODE -ne 0) { throw "coverage combine failed (no data files?)" }

Write-Host "[7/7] Generate coverage report inside container..."
docker compose -f $compose start odoo *> $null
Start-Sleep -Seconds 4
docker compose -f $compose exec -T odoo python3 -m coverage report --data-file=/mnt/covdata/.coverage --precision=1 | Tee-Object -FilePath cov_report.txt
docker compose -f $compose exec -T odoo python3 -m coverage html --data-file=/mnt/covdata/.coverage -d /mnt/covdata/htmlcov --precision=1 *> $null
Write-Host ""
Write-Host "Done. Text report: cov_report.txt ; HTML report: covdata/htmlcov/index.html (pytest exit code = $testRc)"
