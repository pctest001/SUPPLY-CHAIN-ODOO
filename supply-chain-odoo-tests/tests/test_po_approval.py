"""采购订单审批流（C2）业务动作断言 —— 覆盖率盲区补测。

此前 purchase_order_approval.py 仅 71.9%（9 行未覆盖）：test_receipt_lot 的
D4 用例已走 submit→approve→button_confirm 正常路径（终态 approved），但下列
分支从未被 RPC 驱动：

- action_submit_for_approval 的两处守卫（无明细 / 金额为 0）
- action_approve 的「非 pending 禁止审批」守卫
- action_reject 整段（非 pending 守卫 + 置 rejected）
- action_reset_approval 整段（重置回 draft）
- button_confirm 的「未审批禁止确认」守卫（对应 [Unwanted] PRD 需求）

本文件用独立 PO 隔离状态，逐条驱动上述分支并断言真实状态 / 抛错
（期望值来源：验收清单.md §2 C2 / 作品说明.md C 采购审批）。
若断言失败，说明 SUT 行为偏离 PRD —— 真实缺陷信号，绝不自愈掩盖。
"""
import xmlrpc.client

import pytest

pytestmark = pytest.mark.poapproval

from src.healer.audit import get_audit


def _call_action(client, model, method, ids, kwargs=None):
    """调用 action 方法；容忍 Odoo 因返回值 None 导致的 XML-RPC 序列化报错。"""
    try:
        client.execute(model, method, ids, **(kwargs or {}))
    except xmlrpc.client.Fault as e:
        if "cannot marshal None" not in e.faultString:
            raise


def _fault_of(fn):
    """执行 fn，捕获任意异常返回其消息；无异常返回 None。"""
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - 我们就是要抓异常文本做断言
        return str(e)
    return None


def _make_po(client, ctx, price_unit=10.0, with_line=True):
    """新建一张独立采购单，隔离状态避免与其他用例纠缠。"""
    line = []
    if with_line:
        line = [(0, 0, {
            "product_id": ctx["ingredient_id"],
            "product_uom": ctx["ingredient_uom_id"],
            "product_qty": 1.0,
            "price_unit": price_unit,
        })]
    return client.create("purchase.order", {
        "partner_id": ctx["supplier_id"],
        "order_line": line,
    })


def test_po_approval_reject(odoo_client, healed_env):
    """action_reject 应将 pending 状态的 PO 置为 rejected。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        _call_action(odoo_client, "purchase.order", "action_submit_for_approval", [po_id])
        _call_action(odoo_client, "purchase.order", "action_reject", [po_id])
        rec = odoo_client.read("purchase.order", [po_id], ["approval_state"])[0]
        assert rec["approval_state"] == "rejected", f"action_reject 未置 rejected: {rec}"
        audit.log("data", "info", "test_po_approval_reject", f"approval_state={rec['approval_state']}")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001 - 已确认 PO 不可删，忽略不影响判定
            pass


def test_po_approval_reset(odoo_client, healed_env):
    """action_reset_approval 应将 approved 状态的 PO 重置回 draft。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        _call_action(odoo_client, "purchase.order", "action_submit_for_approval", [po_id])
        _call_action(odoo_client, "purchase.order", "action_approve", [po_id])
        _call_action(odoo_client, "purchase.order", "action_reset_approval", [po_id])
        rec = odoo_client.read("purchase.order", [po_id], ["approval_state"])[0]
        assert rec["approval_state"] == "draft", f"action_reset_approval 未置 draft: {rec}"
        audit.log("data", "info", "test_po_approval_reset", f"approval_state={rec['approval_state']}")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_approve_guard_not_pending(odoo_client, healed_env):
    """[Unwanted] 非 pending 状态（draft）调用 action_approve 应抛 UserError。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        msg = _fault_of(lambda: _call_action(
            odoo_client, "purchase.order", "action_approve", [po_id]))
        assert msg and "待审批" in msg, f"action_approve 守卫未拦截非 pending: {msg}"
        audit.log("data", "info", "test_po_approve_guard_not_pending", "guard hit")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_reject_guard_not_pending(odoo_client, healed_env):
    """[Unwanted] draft 状态直接调用 action_reject 应抛 UserError。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        msg = _fault_of(lambda: _call_action(
            odoo_client, "purchase.order", "action_reject", [po_id]))
        assert msg and "待审批" in msg, f"action_reject 守卫未拦截非 pending: {msg}"
        audit.log("data", "info", "test_po_reject_guard_not_pending", "guard hit")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_submit_guard_no_line(odoo_client, healed_env):
    """[Unwanted] 无明细提交审批应抛『请先添加采购明细』。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env, with_line=False)
    try:
        msg = _fault_of(lambda: _call_action(
            odoo_client, "purchase.order", "action_submit_for_approval", [po_id]))
        assert msg and "采购明细" in msg, f"submit 无明细守卫未拦截: {msg}"
        audit.log("data", "info", "test_po_submit_guard_no_line", "guard hit")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_submit_guard_zero_amount(odoo_client, healed_env):
    """[Unwanted] 金额为 0 提交审批应抛『采购订单金额为 0』。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env, price_unit=0.0)
    try:
        msg = _fault_of(lambda: _call_action(
            odoo_client, "purchase.order", "action_submit_for_approval", [po_id]))
        assert msg and "金额为 0" in msg, f"submit 金额为0守卫未拦截: {msg}"
        audit.log("data", "info", "test_po_submit_guard_zero_amount", "guard hit")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_confirm_guard_not_approved(odoo_client, healed_env):
    """[Unwanted] 未审批（draft）调用 button_confirm 应抛『尚未通过审批』。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        msg = _fault_of(lambda: _call_action(
            odoo_client, "purchase.order", "button_confirm", [po_id]))
        assert msg and "尚未通过审批" in msg, f"button_confirm 守卫未拦截未审批: {msg}"
        audit.log("data", "info", "test_po_confirm_guard_not_approved", "guard hit")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass
