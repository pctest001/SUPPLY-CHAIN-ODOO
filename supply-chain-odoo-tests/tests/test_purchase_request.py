"""采购申请 PR（C2 采购审批前置）业务动作断言 —— 覆盖率盲区补测。

此前 purchase_request.py 仅 76.7%（17 行未覆盖）。metagen 已生成
G-PR-SUBMIT / G-PR-GENPO / S-PR-STATE，并走通了
`action_submit` 正常+守卫、`action_generate_po` 正常建 PO 路径、以及
`action_generate_po` 的 state 守卫（G-PR-GENPO）。本文件补齐 metagen 未触达的
可达分支：

- `action_generate_po` 的『无供应商』守卫（有明细无 partner 的 PR 可正常提交）
- `action_cancel` 整段（置 cancel）
- `action_reset` 整段（confirmed 重置回 draft）
- `action_view_pos` 正常分支（返回 act_window + 预置 domain）
- `action_view_pos` 空 PO 分支（return None；Odoo 18 XML-RPC marshaller 不允许
  序列化 None，服务端执行该分支后由 marshaller 抛错——代码行仍被覆盖）

[不可达死区，已在文档标注，未在此驱动]
- `action_generate_po` 的『无明细』守卫（72-73）：`action_submit` 强制要求明细，
  任何已提交 PR 必有明细；且测试账号无删明细权限，无法「提交后删明细」绕过。
  该守卫是 submit 守卫的冗余防御，纯 RPC 不可达。
- `PurchaseRequestLine._onchange_product`（141-146）：Odoo 18 的 `onchange`
  在 BaseModel 上 `raise NotImplementedError`（实现于 web 模块，须经 HTTP web
  会话触发），纯 XML-RPC 无法驱动 onchange。留作已知 RPC 死区。

数据前置复用 healer 幂等提供的 supplier_id / company_id / warehouse_id /
ingredient_id / ingredient_uom_id / po_id。若断言失败说明 SUT 偏离 PRD ——
真实缺陷信号，绝不自愈掩盖。
"""
import xmlrpc.client

import pytest

pytestmark = pytest.mark.purchaserequest

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


def _make_pr(client, ctx, partner=True, with_line=True):
    """新建一张独立采购申请，隔离状态避免与其他用例纠缠。"""
    line = []
    if with_line:
        line = [(0, 0, {
            "product_id": ctx["ingredient_id"],
            "product_uom": ctx["ingredient_uom_id"],
            "product_uom_qty": 1.0,
        })]
    vals = {
        "name": "__pr_test__",
        "company_id": ctx["company_id"],
        "warehouse_id": ctx["warehouse_id"],
        "line_ids": line,
    }
    if partner:
        vals["partner_id"] = ctx["supplier_id"]
    return client.create("sc.purchase.request", vals)


def test_pr_generate_po_no_partner(odoo_client, healed_env):
    """[Unwanted] 已提交但无供应商，生成 PO 应抛『请先选择供应商』。"""
    audit = get_audit()
    rid = _make_pr(odoo_client, healed_env, partner=False)
    try:
        _call_action(odoo_client, "sc.purchase.request", "action_submit", [rid])
        msg = _fault_of(lambda: _call_action(
            odoo_client, "sc.purchase.request", "action_generate_po", [rid]))
        assert msg and "供应商" in msg, f"genpo 无供应商守卫未拦截: {msg}"
        audit.log("data", "info", "test_pr_generate_po_no_partner", "guard hit")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001
            pass


def test_pr_cancel(odoo_client, healed_env):
    """action_cancel 应将 PR 置为 cancel。"""
    audit = get_audit()
    rid = _make_pr(odoo_client, healed_env)
    try:
        _call_action(odoo_client, "sc.purchase.request", "action_cancel", [rid])
        rec = odoo_client.read("sc.purchase.request", [rid], ["state"])[0]
        assert rec["state"] == "cancel", f"action_cancel 未置 cancel: {rec}"
        audit.log("data", "info", "test_pr_cancel", f"state={rec['state']}")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001
            pass


def test_pr_reset(odoo_client, healed_env):
    """action_reset 应将已提交 PR 重置回 draft。"""
    audit = get_audit()
    rid = _make_pr(odoo_client, healed_env)
    try:
        _call_action(odoo_client, "sc.purchase.request", "action_submit", [rid])
        _call_action(odoo_client, "sc.purchase.request", "action_reset", [rid])
        rec = odoo_client.read("sc.purchase.request", [rid], ["state"])[0]
        assert rec["state"] == "draft", f"action_reset 未置 draft: {rec}"
        audit.log("data", "info", "test_pr_reset", f"state={rec['state']}")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001
            pass


def test_pr_view_pos_with_po(odoo_client, healed_env):
    """action_view_pos 在有关联 PO 时应返回打开 purchase.order 的 act_window + 预置 domain。"""
    audit = get_audit()
    rid = _make_pr(odoo_client, healed_env)
    po_id = healed_env["po_id"]
    try:
        odoo_client.write("sc.purchase.request", [rid], {"po_ids": [(4, po_id)]})
        res = odoo_client.execute("sc.purchase.request", "action_view_pos", [rid])
        assert res, f"action_view_pos 未返回 action: {res}"
        assert res.get("res_model") == "purchase.order", f"res_model 不符: {res}"
        domain = res.get("domain") or []
        ids_in_domain = domain[0][2] if domain else []
        assert po_id in ids_in_domain, f"domain 未含关联 PO {po_id}: {domain}"
        audit.log("data", "info", "test_pr_view_pos_with_po", f"res_model={res.get('res_model')}")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001
            pass


def test_pr_view_pos_no_po(odoo_client, healed_env):
    """action_view_pos 在无关联 PO 时 return None；Odoo 18 XML-RPC marshaller 不允许序列化 None，
    故服务端执行该分支后由 marshaller 抛错——这恰好证明走了 return None 分支（115-116 行被覆盖）。"""
    audit = get_audit()
    rid = _make_pr(odoo_client, healed_env)
    try:
        msg = _fault_of(lambda: odoo_client.execute(
            "sc.purchase.request", "action_view_pos", [rid]))
        assert msg, f"无 PO 时 action_view_pos 应触发 return None 分支: {msg}"
        assert "None" in msg or "marshall" in msg.lower(), \
            f"无 PO 应走 return None 分支(致 marshaller 失败): {msg}"
        audit.log("data", "info", "test_pr_view_pos_no_po", "return None branch (marshaller hit)")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001
            pass
