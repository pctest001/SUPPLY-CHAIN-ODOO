"""Mutation 门禁（A2 反假绿）：注入 3 个变异点，期望对应用例变红。

每个变异点：精确替换源码 -> 重启 Odoo 重载 -> 只跑对应用例 -> 必须失败（变异被抓住）
-> finally 还原源码。任何变异未被抓住（用例仍绿）=> 测试过弱 => 退出码非 0。

跨平台（Windows 本地 / Linux CI）均可运行：
    python mutation_gate.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台 GBK 防护
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
COMPOSE = ["docker", "compose", "-f", "docker-compose.test.yml"]
ODOO_URL = "http://localhost:18069/web/login"

MUTANTS = [
    {
        "id": "M1-PR-SUBMIT",
        "desc": "action_submit 提交后不置 confirmed（状态机断裂）",
        "file": REPO_ROOT / "custom_addons/supply_chain_demo/models/purchase_request.py",
        "old": "self.write({'state': 'confirmed'})",
        "new": "self.write({'state': 'draft'})  # MUTANT",
        "pytest": ["tests/test_generated_business.py", "-k", "PR-SUBMIT"],
    },
    {
        "id": "M2-RCPT-NOLOT",
        "desc": "C3 收货批次守卫被绕过（流程制造无批次也放行）",
        "file": REPO_ROOT / "custom_addons/supply_chain_demo/models/stock_receipt_lot.py",
        "old": "if not (line.lot_id or line.lot_name):",
        "new": "if False and not (line.lot_id or line.lot_name):  # MUTANT",
        "pytest": ["tests/test_receipt_lot.py", "-k", "test_rcpt_nolot_rejected"],
    },
    {
        "id": "M3-RECIPE-QTY",
        "desc": "配方用量约束松动（<=0 变 <0，零用量放行）",
        "file": REPO_ROOT / "custom_addons/supply_chain_demo/models/recipe.py",
        "old": "if line.product_qty <= 0:",
        "new": "if line.product_qty < 0:  # MUTANT",
        "pytest": ["tests/test_generated_struct.py", "-k", "C-RECIPE-QTY"],
    },
]


def sh(args, **kw):
    return subprocess.run(args, cwd=TESTS_DIR, **kw)


def restart_odoo_and_wait(timeout_tries=50):
    sh(COMPOSE + ["restart", "odoo"], capture_output=True)
    for _ in range(timeout_tries):
        try:
            with urllib.request.urlopen(ODOO_URL, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def apply_patch(path: pathlib.Path, old: str, new: str):
    # 字节级替换：保留原文件换行符（write_text 在 Windows 会把 LF 写成 CRLF）
    data = path.read_bytes()
    ob, nb = old.encode("utf-8"), new.encode("utf-8")
    if data.count(ob) != 1:
        raise SystemExit(f"[gate] 变异锚点非唯一/不存在: {path.name} :: {old!r} (count={data.count(ob)})")
    path.write_bytes(data.replace(ob, nb, 1))


def run_mutant(m) -> bool:
    """返回 True = 变异被抓住（用例如期变红）。"""
    print(f"\n=== [{m['id']}] {m['desc']} ===", flush=True)
    apply_patch(m["file"], m["old"], m["new"])
    print(f"[gate] MUTANT APPLIED -> {m['file'].name}", flush=True)
    try:
        if not restart_odoo_and_wait():
            raise SystemExit("[gate] odoo 重启后未就绪")
        r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *m["pytest"]],
               capture_output=True, text=True)
        tail = "\n".join((r.stdout or "").splitlines()[-5:])
        print(tail, flush=True)
        if r.returncode == 0:
            print(f"[gate] [MISS] MUTATION NOT CAUGHT — {m['id']} 变异后用例仍绿，测试过弱", flush=True)
            return False
        if "failed" not in (r.stdout or "") and "error" not in (r.stdout or ""):
            print(f"[gate] [MISS] {m['id']} 非预期失败形态（环境异常？rc={r.returncode}）", flush=True)
            return False
        print(f"[gate] [OK] MUTATION CAUGHT — {m['id']} 用例如期变红", flush=True)
        return True
    finally:
        apply_patch(m["file"], m["new"], m["old"])
        print(f"[gate] MUTANT REVERTED <- {m['file'].name}", flush=True)


def main():
    caught, missed = [], []
    try:
        for m in MUTANTS:
            (caught if run_mutant(m) else missed).append(m["id"])
    finally:
        print("\n[gate] 还原完毕，恢复 odoo 至干净代码...", flush=True)
        if not restart_odoo_and_wait():
            print("[gate] 警告：odoo 恢复后未就绪，请手动检查", flush=True)
    print(f"\n[gate] 结果: caught={caught} missed={missed}")
    if missed:
        print(f"[gate] FAIL — {len(missed)} 个变异未被测试抓住")
        sys.exit(1)
    print(f"[gate] PASS — 全部 {len(caught)} 个变异均被抓住")


if __name__ == "__main__":
    main()
