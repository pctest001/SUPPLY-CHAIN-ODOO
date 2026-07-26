"""收货/批次/出库守卫用例（stock_receipt_lot.py，补测覆盖率 10% 洼地）。

黑盒 RPC 驱动 stock.picking.button_validate 上的 5 类守卫：
  - C3 收货：流程制造物料必须录入批次号(Lot)        -> RCPT-NOLOT
  - C3 收货：流程制造物料必须录入效期               -> RCPT-NOEXP
  - 正向：批次+效期齐全可验证，stock.lot 记录效期    -> RCPT-OK
  - D4 收货：PO 关联收货超订购量拦截                -> RCPT-OVER
  - D1 出库：流程制造物料必须指定批次               -> OUT-NOLOT
  - D3 出库：过期批次禁止出库                       -> OUT-EXPIRED
  - D4 出库：超出现有库存(负库存)拦截               -> OUT-NEG

期望消息权威来源：PRD 验收清单 C3/D1/D3/D4（与 SUT 中 EARS 注释一致）。
"""
from __future__ import annotations

import uuid
import xmlrpc.client
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.receipt


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _fault_of(fn):
    """执行 fn，期望抛 xmlrpc Fault，返回其消息文本；若未抛则返回 None。"""
    try:
        fn()
        return None
    except xmlrpc.client.Fault as f:
        return str(f)


def _call_action(client, model, method, ids):
    """调用 action 方法，容忍『返回 None 无法 marshal』的 XML-RPC 噪声。"""
    try:
        return client.execute(model, method, ids)
    except xmlrpc.client.Fault as f:
        if "cannot marshal None" in str(f):
            return None
        raise


def _uniq(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _product_of_tmpl(client, tmpl_id):
    rows = client.search_read(
        "product.product", [("product_tmpl_id", "=", tmpl_id)], fields=["id", "uom_id"]
    )
    assert rows, f"模板 {tmpl_id} 没有变体"
    uom = rows[0]["uom_id"]
    return rows[0]["id"], (uom[0] if isinstance(uom, (list, tuple)) else uom)


def _make_proc_product(client):
    """流程制造物料（tracking=lot + 效期），每次唯一，测试间零共享。"""
    tmpl = client.create("product.template", {"name": _uniq("__rcpt_proc"), "is_process_mfg": True})
    return _product_of_tmpl(client, tmpl)


def _make_plain_product(client):
    """普通可库存物料（无批次追踪）。"""
    tmpl = client.create("product.template", {"name": _uniq("__rcpt_plain"), "is_storable": True})
    return _product_of_tmpl(client, tmpl)


# ---------------------------------------------------------------------------
# 库位 / 作业类型（session 级只读上下文）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def stock_ctx(odoo_client, healed_env):
    # 多公司环境：一律锚定 admin 当前公司，避免仓库/库位/作业类型跨公司混用
    user = odoo_client.read("res.users", [odoo_client.authenticated_uid],
                            fields=["company_id"])[0]
    company_id = user["company_id"][0]
    wh_ids = odoo_client.search("stock.warehouse", [("company_id", "=", company_id)], limit=1)
    assert wh_ids, f"公司 {company_id} 无仓库"
    wh = odoo_client.read("stock.warehouse", wh_ids,
                          fields=["lot_stock_id", "in_type_id", "out_type_id"])[0]
    supplier_loc = odoo_client.search(
        "stock.location",
        [("usage", "=", "supplier"), ("company_id", "in", [False, company_id])], limit=1)
    customer_loc = odoo_client.search(
        "stock.location",
        [("usage", "=", "customer"), ("company_id", "in", [False, company_id])], limit=1)
    assert supplier_loc and customer_loc, "缺 supplier/customer 库位"
    return {
        "stock_loc": wh["lot_stock_id"][0],
        "in_type": wh["in_type_id"][0],
        "out_type": wh["out_type_id"][0],
        "supplier_loc": supplier_loc[0],
        "customer_loc": customer_loc[0],
    }


# ---------------------------------------------------------------------------
# 作业编排 helpers
# ---------------------------------------------------------------------------
def _make_picking(client, ctx, direction, product_id, uom_id, qty):
    """建一张已确认的收/发货作业，返回 (picking_id, move_id)。"""
    if direction == "in":
        type_id, src, dst = ctx["in_type"], ctx["supplier_loc"], ctx["stock_loc"]
    else:
        type_id, src, dst = ctx["out_type"], ctx["stock_loc"], ctx["customer_loc"]
    pid = client.create("stock.picking", {
        "picking_type_id": type_id,
        "location_id": src,
        "location_dest_id": dst,
        "move_ids": [(0, 0, {
            "name": f"test move {product_id}",
            "product_id": product_id,
            "product_uom_qty": qty,
            "product_uom": uom_id,
            "location_id": src,
            "location_dest_id": dst,
        })],
    })
    client.execute("stock.picking", "action_confirm", [pid])
    move = client.search("stock.move", [("picking_id", "=", pid)], limit=1)
    return pid, move[0]


def _force_line(client, pid, move_id, vals):
    """强制作业明细为唯一一行且字段精确等于 vals（覆盖 Odoo 自动生成的行）。"""
    picking = client.read("stock.picking", [pid], fields=["move_line_ids"])[0]
    line_ids = picking["move_line_ids"]
    if line_ids:
        client.write("stock.move.line", [line_ids[0]], vals)
        if len(line_ids) > 1:
            client.unlink("stock.move.line", line_ids[1:])
        return line_ids[0]
    move = client.read("stock.move", [move_id],
                       fields=["location_id", "location_dest_id", "product_id", "product_uom"])[0]
    base = {
        "move_id": move_id,
        "picking_id": pid,
        "product_id": move["product_id"][0],
        "product_uom_id": move["product_uom"][0],
        "location_id": move["location_id"][0],
        "location_dest_id": move["location_dest_id"][0],
    }
    base.update(vals)
    return client.create("stock.move.line", base)


def _validate(client, pid):
    return client.execute("stock.picking", "button_validate", [pid])


def _receive(client, ctx, product_id, uom_id, qty, lot_name, exp):
    """走完一张收货：录批次+效期并验证，返回 stock.lot id。"""
    pid, move = _make_picking(client, ctx, "in", product_id, uom_id, qty)
    _force_line(client, pid, move, {
        "quantity": qty, "lot_name": lot_name,
        "expiration_date": exp + " 12:00:00",
    })
    _validate(client, pid)
    lots = client.search("stock.lot", [("name", "=", lot_name), ("product_id", "=", product_id)])
    assert lots, f"验证后未生成批次 {lot_name}"
    return lots[0]


FUTURE = (date.today() + timedelta(days=180)).isoformat()
PAST = (date.today() - timedelta(days=10)).isoformat()


# ---------------------------------------------------------------------------
# C3 收货守卫
# ---------------------------------------------------------------------------
def test_rcpt_nolot_rejected(odoo_client, healed_env, stock_ctx):
    """RCPT-NOLOT：流程制造物料收货未录批次 -> 拒绝验证（C3）。"""
    prod, uom = _make_proc_product(odoo_client)
    pid, move = _make_picking(odoo_client, stock_ctx, "in", prod, uom, 5)
    _force_line(odoo_client, pid, move,
                {"quantity": 5, "lot_id": False, "lot_name": False, "expiration_date": False})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "必须录入批次号" in msg, f"C3 批次守卫未生效: {msg}"


def test_rcpt_noexp_rejected(odoo_client, healed_env, stock_ctx):
    """RCPT-NOEXP：录了批次但没录效期 -> 拒绝验证（C3）。"""
    prod, uom = _make_proc_product(odoo_client)
    pid, move = _make_picking(odoo_client, stock_ctx, "in", prod, uom, 5)
    _force_line(odoo_client, pid, move,
                {"quantity": 5, "lot_name": _uniq("LOT"), "expiration_date": False})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "必须录入效期" in msg, f"C3 效期守卫未生效: {msg}"


def test_rcpt_ok_lot_traceable(odoo_client, healed_env, stock_ctx):
    """RCPT-OK：批次+效期齐全 -> 验证通过，stock.lot 落效期（可追溯）。"""
    prod, uom = _make_proc_product(odoo_client)
    lot_name = _uniq("LOT")
    lot_id = _receive(odoo_client, stock_ctx, prod, uom, 5, lot_name, FUTURE)
    lot = odoo_client.read("stock.lot", [lot_id], fields=["name", "expiration_date"])[0]
    assert lot["name"] == lot_name
    assert lot["expiration_date"], "批次效期未被记录，追溯断裂"
    onhand = odoo_client.search_read(
        "stock.quant",
        [("product_id", "=", prod), ("location_id", "=", stock_ctx["stock_loc"]), ("lot_id", "=", lot_id)],
        fields=["quantity"])
    assert onhand and abs(onhand[0]["quantity"] - 5) < 1e-6, "收货后按批次的在库量不等于 5"


# ---------------------------------------------------------------------------
# D4 超额收货（走 PO 审批 -> 确认 -> 收货链路）
# ---------------------------------------------------------------------------
def test_rcpt_over_po_qty_rejected(odoo_client, healed_env, stock_ctx):
    """RCPT-OVER：PO 订 5 收 8 -> 拒绝（D4 超额收货拦截）。"""
    prod, uom = _make_plain_product(odoo_client)
    po_id = odoo_client.create("purchase.order", {
        "partner_id": healed_env["supplier_id"],
        "order_line": [(0, 0, {"product_id": prod, "product_qty": 5, "price_unit": 10})],
    })
    _call_action(odoo_client, "purchase.order", "action_submit_for_approval", [po_id])
    _call_action(odoo_client, "purchase.order", "action_approve", [po_id])
    _call_action(odoo_client, "purchase.order", "button_confirm", [po_id])
    po = odoo_client.read("purchase.order", [po_id], fields=["picking_ids", "state"])[0]
    assert po["state"] == "purchase" and po["picking_ids"], "PO 确认后未生成收货作业"
    pid = po["picking_ids"][0]
    move = odoo_client.search("stock.move", [("picking_id", "=", pid)], limit=1)[0]
    _force_line(odoo_client, pid, move, {"quantity": 8})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "超出订购量" in msg, f"D4 超额收货拦截未生效: {msg}"


# ---------------------------------------------------------------------------
# D1 / D3 / D4 出库守卫
# ---------------------------------------------------------------------------
def test_out_nolot_rejected(odoo_client, healed_env, stock_ctx):
    """OUT-NOLOT：先收 5 在库，出库不指定批次 -> 拒绝（D1）。"""
    prod, uom = _make_proc_product(odoo_client)
    _receive(odoo_client, stock_ctx, prod, uom, 5, _uniq("LOT"), FUTURE)
    pid, move = _make_picking(odoo_client, stock_ctx, "out", prod, uom, 3)
    _force_line(odoo_client, pid, move, {"quantity": 3, "lot_id": False, "lot_name": False})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "必须指定批次" in msg, f"D1 出库批次守卫未生效: {msg}"


def test_out_expired_lot_rejected(odoo_client, healed_env, stock_ctx):
    """OUT-EXPIRED：批次效期已过 -> 出库拒绝（D3）。"""
    prod, uom = _make_proc_product(odoo_client)
    lot_id = _receive(odoo_client, stock_ctx, prod, uom, 5, _uniq("LOT"), PAST)
    pid, move = _make_picking(odoo_client, stock_ctx, "out", prod, uom, 2)
    _force_line(odoo_client, pid, move, {"quantity": 2, "lot_id": lot_id})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "禁止出库" in msg, f"D3 效期拦截未生效: {msg}"


def test_out_negative_stock_rejected(odoo_client, healed_env, stock_ctx):
    """OUT-NEG：零库存物料直接出 5 -> 拒绝（D4 负库存拦截）。"""
    prod, uom = _make_plain_product(odoo_client)
    pid, move = _make_picking(odoo_client, stock_ctx, "out", prod, uom, 5)
    _force_line(odoo_client, pid, move, {"quantity": 5})
    msg = _fault_of(lambda: _validate(odoo_client, pid))
    assert msg and "负库存" in msg, f"D4 负库存拦截未生效: {msg}"
