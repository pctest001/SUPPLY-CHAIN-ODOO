# 让任何 python 进程（含 Odoo re-exec / 派生的子进程）自动开启 coverage 测量。
# 由环境变量 COVERAGE_PROCESS_START 指向同目录的 .coveragerc 触发。
try:
    import coverage
    coverage.process_startup()
except Exception:
    pass
