# 让任何 python 进程（含 Odoo re-exec / 派生的子进程）自动开启 coverage 测量。
# 由环境变量 COVERAGE_PROCESS_START 指向同目录的 .coveragerc 触发。
# 注意：失败必须出声。2026-07-28 CI 首跑时 gevent 缺失导致 ConfigError 被
# 旧版的裸 except 静默吞掉，覆盖率零数据却无任何报错线索，排障绕了大弯。
try:
    import coverage
    coverage.process_startup()
except Exception as _e:  # noqa: BLE001
    import os
    import sys
    if os.environ.get("COVERAGE_PROCESS_START"):
        sys.stderr.write(f"[covdata/sitecustomize] coverage 未启动: {_e!r}\n")
