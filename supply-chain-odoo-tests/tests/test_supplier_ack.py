"""供应商确认单（E1 供应商协同）业务动作断言 —— 覆盖率盲区补测。

此前 supplier_ack.py 仅 66.7%（23 行未覆盖）：已有两个生成用例
（G-ACK-CONF / ACK-CONFIRM）覆盖了 create 与 action_confirm 两条路径，
但下列业务逻辑从未被 RPC 驱动：

- SupplierAck.action_reject                         -> 置 rejected
- PurchaseOrder._compute_supplier_ack               -> 从 ack_ids 实时算协同状态
- PurchaseOrder._create_or_update_ack（创建/更新两分支）
- PurchaseOrder.action_register_supplier_ack       -> 返回登记向导 action
- SupplierAckWizard.action_confirm / action_reject -> 向导两条入口

约束（Odoo RPC 黑盒）：
- `_create_or_update_ack` 是私有方法（下划线开头），不可经 XML-RPC 直调；
  其覆盖由向导的 public action 间接触发（向导 action_confirm/action_reject 内部调用它）。
- 向导 `committed_date` 为 required 字段，创建向导记录时必须给值（即便 reject 不用）。

本文件用独立 PO 隔离状态，逐条驱动上述路径并断言真实状态/字段
（期望值来源：验收清单.md §2 E1 / 作品说明.md E 供应商协同语义）。
若断言失败，说明 SUT 行为偏离 PRD —— 真实缺陷信号，绝不自愈掩盖。
"""
import xmlrpc.client

import pytest

pytestmark = pytest.mark.supplierack

from src.healer.audit import get_audit


def _make_po(client, ctx):
    """新建一张独立采购单，隔离状态避免与其他用例纠缠。"""
    return client.create("purchase.order", {
        "partner_id": ctx["supplier_id"],
        "order_line": [(0, 0, {
            "product_id": ctx["ingredient_id"],
            "product_uom": ctx["ingredient_uom_id"],
            "product_qty": 1.0,
            "price_unit": 10.0,
        })],
    })


def _cleanup_ack_of_po(client, po_id):
    try:
        ack_ids = client.read("purchase.order", [po_id], ["ack_ids"])[0].get("ack_ids") or []
        for aid in ack_ids:
            try:
                client.unlink("sc.supplier.ack", [aid])
            except Exception:  # noqa: BLE001 - 清理失败不影响判定
                pass
    except Exception:  # noqa: BLE001
        pass


def _call_action(client, model, method, ids, kwargs=None):
    """调用 action 方法；容忍 Odoo 因返回值 None 导致的 XML-RPC 序列化报错。

    部分 action 方法无显式返回值（返回 None），而 Odoo XML-RPC 默认
    allow_none=False 会抛 'cannot marshal None'。但本工程 odoo_client 的
    models proxy 已设 allow_none=True，故此处仅作兜底容错。
    """
    try:
        client.execute(model, method, ids, **(kwargs or {}))
    except xmlrpc.client.Fault as e:
        if "cannot marshal None" not in e.faultString:
            raise


def test_ack_reject(odoo_client, healed_env):
    """供应商确认单 action_reject 应置 rejected 并写入驳回原因。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    aid = odoo_client.create("sc.supplier.ack", {"po_id": po_id})
    try:
        _call_action(odoo_client, "sc.supplier.ack", "action_reject", [aid],
                     {"remark": "产能不足，无法按期交付"})
        rec = odoo_client.read("sc.supplier.ack", [aid], ["state", "remark"])[0]
        assert rec["state"] == "rejected", f"action_reject 未置 rejected: {rec}"
        assert rec["remark"] == "产能不足，无法按期交付", f"remark 未写入: {rec}"
        audit.log("data", "info", "test_ack_reject", f"state={rec['state']} remark={rec['remark']}")
    finally:
        try:
            odoo_client.unlink("sc.supplier.ack", [aid])
        except Exception:  # noqa: BLE001
            pass
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_supplier_ack_compute(odoo_client, healed_env):
    """确认交期后，PO 上的 supplier_ack_state / supplier_committed_date 应被 compute 出。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    aid = odoo_client.create("sc.supplier.ack", {"po_id": po_id})
    try:
        _call_action(odoo_client, "sc.supplier.ack", "action_confirm", [aid],
                     {"committed_date": "2026-12-31", "remark": "准时交付"})
        po = odoo_client.read(
            "purchase.order", [po_id],
            ["supplier_ack_state", "supplier_committed_date", "ack_ids"],
        )[0]
        assert po["supplier_ack_state"] == "confirmed", \
            f"PO compute 未得 confirmed: {po}"
        assert po["supplier_committed_date"] == "2026-12-31", \
            f"committed_date 未回写 PO: {po}"
        assert po.get("ack_ids"), "PO 未关联 ack"
        audit.log("data", "info", "test_po_supplier_ack_compute",
                  f"state={po['supplier_ack_state']} date={po['supplier_committed_date']}")
    finally:
        _cleanup_ack_of_po(odoo_client, po_id)
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_po_register_supplier_ack_action(odoo_client, healed_env):
    """PO.action_register_supplier_ack 应返回打开登记向导的 act_window。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    try:
        action = odoo_client.execute("purchase.order", "action_register_supplier_ack", [po_id])
        assert isinstance(action, dict), f"应返回 action dict: {action}"
        assert action.get("res_model") == "sc.supplier.ack.wizard", \
            f"应打开登记向导: {action}"
        ctx = action.get("context") or {}
        assert ctx.get("default_po_id") == po_id, f"应预置 default_po_id: {ctx}"
        audit.log("data", "info", "test_po_register_supplier_ack_action",
                  f"res_model={action.get('res_model')}")
    finally:
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_ack_wizard_confirm_update(odoo_client, healed_env):
    """向导 action_confirm（PO 已有 ack）应经 _create_or_update_ack 更新为 confirmed。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    aid = odoo_client.create("sc.supplier.ack", {"po_id": po_id})
    wid = odoo_client.create("sc.supplier.ack.wizard", {
        "po_id": po_id,
        "committed_date": "2026-11-11",
        "remark": "向导确认",
    })
    try:
        _call_action(odoo_client, "sc.supplier.ack.wizard", "action_confirm", [wid])
        po = odoo_client.read("purchase.order", [po_id], ["supplier_ack_state"])[0]
        assert po["supplier_ack_state"] == "confirmed", f"向导确认(更新分支)未生效: {po}"
        audit.log("data", "info", "test_ack_wizard_confirm_update",
                  f"state={po['supplier_ack_state']}")
    finally:
        try:
            odoo_client.unlink("sc.supplier.ack.wizard", [wid])
        except Exception:  # noqa: BLE001
            pass
        _cleanup_ack_of_po(odoo_client, po_id)
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_ack_wizard_confirm_create(odoo_client, healed_env):
    """向导 action_confirm（PO 无 ack）应经 _create_or_update_ack 新建为 confirmed。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    wid = odoo_client.create("sc.supplier.ack.wizard", {
        "po_id": po_id,
        "committed_date": "2026-11-11",
        "remark": "向导新建确认",
    })
    try:
        _call_action(odoo_client, "sc.supplier.ack.wizard", "action_confirm", [wid])
        po = odoo_client.read("purchase.order", [po_id], ["supplier_ack_state"])[0]
        assert po["supplier_ack_state"] == "confirmed", f"向导确认(创建分支)未生效: {po}"
        audit.log("data", "info", "test_ack_wizard_confirm_create",
                  f"state={po['supplier_ack_state']}")
    finally:
        try:
            odoo_client.unlink("sc.supplier.ack.wizard", [wid])
        except Exception:  # noqa: BLE001
            pass
        _cleanup_ack_of_po(odoo_client, po_id)
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_ack_wizard_reject_create(odoo_client, healed_env):
    """向导 action_reject（PO 无 ack）应经 _create_or_update_ack 新建为 rejected。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    wid = odoo_client.create("sc.supplier.ack.wizard", {
        "po_id": po_id,
        "committed_date": "2026-12-31",  # 向导字段 required，reject 内部会忽略
        "remark": "向导拒绝",
    })
    try:
        _call_action(odoo_client, "sc.supplier.ack.wizard", "action_reject", [wid])
        po = odoo_client.read("purchase.order", [po_id], ["supplier_ack_state"])[0]
        assert po["supplier_ack_state"] == "rejected", f"向导拒绝(创建分支)未生效: {po}"
        audit.log("data", "info", "test_ack_wizard_reject_create",
                  f"state={po['supplier_ack_state']}")
    finally:
        try:
            odoo_client.unlink("sc.supplier.ack.wizard", [wid])
        except Exception:  # noqa: BLE001
            pass
        _cleanup_ack_of_po(odoo_client, po_id)
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass


def test_ack_wizard_reject_update(odoo_client, healed_env):
    """向导 action_reject（PO 已有 ack）应经 _create_or_update_ack 更新为 rejected。"""
    audit = get_audit()
    po_id = _make_po(odoo_client, healed_env)
    aid = odoo_client.create("sc.supplier.ack", {"po_id": po_id})
    wid = odoo_client.create("sc.supplier.ack.wizard", {
        "po_id": po_id,
        "committed_date": "2026-12-31",  # 向导字段 required，reject 内部会忽略
        "remark": "向导拒绝更新",
    })
    try:
        _call_action(odoo_client, "sc.supplier.ack.wizard", "action_reject", [wid])
        po = odoo_client.read("purchase.order", [po_id], ["supplier_ack_state"])[0]
        assert po["supplier_ack_state"] == "rejected", f"向导拒绝(更新分支)未生效: {po}"
        audit.log("data", "info", "test_ack_wizard_reject_update",
                  f"state={po['supplier_ack_state']}")
    finally:
        try:
            odoo_client.unlink("sc.supplier.ack.wizard", [wid])
        except Exception:  # noqa: BLE001
            pass
        _cleanup_ack_of_po(odoo_client, po_id)
        try:
            odoo_client.unlink("purchase.order", [po_id])
        except Exception:  # noqa: BLE001
            pass
