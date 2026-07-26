"""product_ext.py 补测：流程制造标记自动启用批次+效期追溯（C3 前置）。

覆盖 create / write 两条自动化路径（onchange 属 UI 层行为，黑盒 RPC 不驱动）。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.struct

FIELDS = ["tracking", "use_expiration_date", "is_storable", "expiration_time", "is_process_mfg"]


def _uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_create_process_mfg_auto_tracking(odoo_client, healed_env):
    """create 时标记流程制造 -> 自动 lot 追踪 + 效期 + 可库存 + 默认保质期 365。"""
    tid = odoo_client.create("product.template",
                             {"name": _uniq("__pext_c"), "is_process_mfg": True})
    t = odoo_client.read("product.template", [tid], fields=FIELDS)[0]
    assert t["tracking"] == "lot", "未自动启用批次追踪"
    assert t["use_expiration_date"] is True, "未自动启用效期管理"
    assert t["is_storable"] is True, "未自动置为可库存"
    assert t["expiration_time"] == 365, "默认保质期应为 365 天"


def test_create_normal_not_affected(odoo_client, healed_env):
    """create 普通物料 -> 不应被强制开启批次追踪。"""
    tid = odoo_client.create("product.template", {"name": _uniq("__pext_n")})
    t = odoo_client.read("product.template", [tid], fields=FIELDS)[0]
    assert t["tracking"] != "lot", "普通物料不应被强制 lot 追踪"
    assert not t["is_process_mfg"]


def test_write_upgrade_to_process_mfg(odoo_client, healed_env):
    """后补标记（write 路径，含 filtered 分支）：批量升级两个普通物料。"""
    ids = [
        odoo_client.create("product.template", {"name": _uniq("__pext_w1")}),
        odoo_client.create("product.template", {"name": _uniq("__pext_w2")}),
    ]
    odoo_client.write("product.template", ids, {"is_process_mfg": True})
    for t in odoo_client.read("product.template", ids, fields=FIELDS):
        assert t["tracking"] == "lot" and t["use_expiration_date"] is True \
            and t["is_storable"] is True, f"write 路径未自动启用追溯: {t}"
