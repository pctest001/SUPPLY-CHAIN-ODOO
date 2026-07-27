# 让任何 python 进程（含 Odoo re-exec / 派生的子进程）自动开启 coverage 测量。
# 由环境变量 COVERAGE_PROCESS_START 指向同目录的 .coveragerc 触发。
#
# 2026-07-28 排障注记（coverage>=7.x 自带 pth 的中毒链，本地复现 + 读源码定位）：
# coverage 7.x 的 wheel 自带 a1_coverage.pth，它在 site 初始化早期（此时
# /usr/lib/python3/dist-packages 尚未进 sys.path）抢先 process_startup()。
# odoo 官方镜像的 gevent 在系统目录、此刻不可见 → cov.start() 抛 ConfigError，
# 但 process_startup.coverage 属性已先被赋值（见 coverage/control.py）→
# 此后任何 process_startup() 都被 hasattr 检查静默跳过（返回 None）→
# sitecustomize 的 try/except 也感知不到 → 全进程零测量、No data to combine。
# 对策：以 Coverage.current() 是否真启动为准，未启动则 force=True 强制启动。
import os
import sys

try:
    import coverage
    if os.environ.get("COVERAGE_PROCESS_START") or os.environ.get("COVERAGE_PROCESS_CONFIG"):
        _cur = getattr(coverage.Coverage, "current", None)
        if _cur is None or _cur() is None:
            coverage.process_startup(force=True)
except Exception as _e:  # noqa: BLE001
    if os.environ.get("COVERAGE_PROCESS_START"):
        sys.stderr.write(f"[covdata/sitecustomize] coverage 未启动: {_e!r}\n")
