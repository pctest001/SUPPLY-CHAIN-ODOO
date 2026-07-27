"""围栏执行上下文：连接目标实例 + 幂等数据前置。

base / head 双实例通过环境无关的 Target 描述连接；
数据前置完全复用 healer.ensure_demo_data（幂等），保证双端上下文语义对齐
（id 可能不同——场景引用一律用符号名，不用裸 id）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.healer.heal import ensure_demo_data, ensure_environment  # noqa: E402
from src.odoo_client import OdooClient  # noqa: E402


@dataclass
class Target:
    """一个被测实例的连接描述。"""

    name: str          # "base" | "head"
    port: int
    url: str = "http://localhost"
    db: str = "test_supplychain"
    username: str = "admin@example.com"
    password: str = "admin"

    def connect(self) -> OdooClient:
        client = OdooClient(self.url, self.db, self.username, self.password, self.port)
        if not ensure_environment(client):
            raise ConnectionError(f"[fence] target={self.name} port={self.port} 不可达或未初始化")
        return client


HEAD = Target(name="head", port=int(os.getenv("FENCE_HEAD_PORT", "18069")))
BASE = Target(name="base", port=int(os.getenv("FENCE_BASE_PORT", "28069")))

TARGETS = {"head": HEAD, "base": BASE}


def build_context(client: OdooClient) -> dict:
    """构建场景可引用的符号上下文（双端各自执行，语义对齐）。

    键即场景 JSON 中 "$ctx.xxx" 可引用的符号名。
    """
    ctx = dict(ensure_demo_data(client))

    # 库存上下文（与 tests/test_receipt_lot.py 的 stock_ctx 保持一致口径）
    user = client.read("res.users", [client.authenticated_uid], fields=["company_id"])[0]
    company_id = user["company_id"][0]
    wh_ids = client.search("stock.warehouse", [("company_id", "=", company_id)], limit=1)
    if wh_ids:
        wh = client.read(
            "stock.warehouse", wh_ids, fields=["lot_stock_id", "in_type_id", "out_type_id"]
        )[0]
        ctx["stock_loc"] = wh["lot_stock_id"][0]
        ctx["in_type"] = wh["in_type_id"][0]
        ctx["out_type"] = wh["out_type_id"][0]
    supplier_loc = client.search(
        "stock.location", [("usage", "=", "supplier"), ("company_id", "in", [False, company_id])],
        limit=1,
    )
    customer_loc = client.search(
        "stock.location", [("usage", "=", "customer"), ("company_id", "in", [False, company_id])],
        limit=1,
    )
    ctx["supplier_loc"] = supplier_loc[0] if supplier_loc else None
    ctx["customer_loc"] = customer_loc[0] if customer_loc else None
    return ctx
