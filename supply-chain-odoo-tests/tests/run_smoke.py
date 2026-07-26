"""零依赖冒烟（不依赖 pytest，纯标准库）。

当测试机无法安装 pytest 时，可用本脚本直接验证 M1：
    python tests/run_smoke.py

前置：被测实例已按 docker-compose.test.yml 注释 init + up（http://localhost:18069 可达）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.odoo_client import OdooClient

URL = os.getenv("ODOO_URL", "http://localhost")
PORT = int(os.getenv("ODOO_PORT", "18069"))
DB = os.getenv("ODOO_DB", "test_supplychain")
LOGIN = os.getenv("ODOO_ADMIN_LOGIN", "admin@example.com")
PWD = os.getenv("ODOO_ADMIN_PASSWORD", "admin")


def check(name: str, cond: bool) -> bool:
    print(("PASS" if cond else "FAIL"), "-", name)
    return cond


def main() -> int:
    try:
        client = OdooClient(URL, DB, LOGIN, PWD, PORT)
        client.authenticate()
    except Exception as exc:  # noqa: BLE001
        print("FAIL - 连接/认证失败:", exc)
        return 1

    ok = True
    ok &= check("admin 认证成功", client.uid is not None)
    for model in ("sc.purchase.request", "sc.recipe", "sc.supplier.ack", "ai.config"):
        ok &= check(f"核心模型已安装: {model}", client.model_exists(model))
    companies = client.search_read("res.company", [], fields=["id", "name"])
    ok &= check("被测实例含至少 2 个公司（多公司测试前置）", len(companies) >= 2)

    print("\n结果:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
