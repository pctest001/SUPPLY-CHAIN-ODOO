"""元数据驱动的结构型断言生成器。

红线（见技术方案 v2.1 P0#3）：业务数值/行为期望仅以 PRD/验收清单为权威；
本生成器只产出『结构型断言』——是否报错/拦截/存在，绝不从代码反推数值再断言代码。

用例类型：
- GuardCase            ：在已有记录上调用 action 方法，期望抛异常（状态机守卫）。
- CreateViolationCase  ：create 即应抛异常（constrains 守卫，create 路径触发）。
- WriteViolationCase   ：先建合法记录再 write 改写，期望抛异常（constrains 守卫，write 路径触发；
                         因为 Odoo constrains 对 create 时未提供的字段不校验，『至少一种原料』走此路径）。
- CreateThenActionCase ：先 create 再调用 action 方法，期望抛异常（如 action_confirm 守卫）。
- SelectionViolationCase：写非法 selection 值，期望抛异常。
"""
from __future__ import annotations

import xmlrpc.client
from dataclasses import dataclass
from typing import Dict, List, Tuple

TARGET_MODELS = ["sc.purchase.request", "sc.recipe", "sc.supplier.ack"]


@dataclass
class Case:
    cid: str
    title: str
    kind: str
    model: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:  # pragma: no cover - 抽象
        raise NotImplementedError


@dataclass
class GuardCase(Case):
    """状态机守卫：在已有记录上调用 action 方法，期望抛异常（被拒）。"""
    method: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        rid = ctx.get("pr_id")
        if not rid:
            return False, "缺少测试 PR 记录（数据层自愈未完成）"
        try:
            client.execute(self.model, self.method, [rid])
            return False, f"调用 {self.method} 未抛异常（守卫缺失？）"
        except xmlrpc.client.Fault as e:
            return True, f"已按预期拦截: {e.faultString[:60]}"


@dataclass
class CreateViolationCase(Case):
    """constrains 守卫（create 路径触发）：create 应抛异常。"""
    build: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        try:
            client.create(self.model, _build_vals(self.build, ctx))
            return False, "create 未抛异常（constrains 守卫缺失？）"
        except xmlrpc.client.Fault as e:
            return True, f"已按预期拦截: {e.faultString[:60]}"


@dataclass
class WriteViolationCase(Case):
    """constrains 守卫（write 路径触发）：先建合法记录，再 write 改写应抛异常。"""
    build_create: str
    field: str
    write_kind: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        rid = client.create(self.model, _build_vals(self.build_create, ctx))
        try:
            client.write(self.model, [rid], _build_write(self.field, self.write_kind))
            return False, "write 未抛异常（守卫缺失？）"
        except xmlrpc.client.Fault as e:
            return True, f"已按预期拦截: {e.faultString[:60]}"
        finally:
            try:
                client.unlink(self.model, [rid])
            except Exception:  # noqa: BLE001 - 清理失败不影响守卫判定
                pass


@dataclass
class CreateThenActionCase(Case):
    """先 create 再调用 action 方法，期望抛异常（如 action_confirm 守卫）。"""
    build: str
    method: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        rid = client.create(self.model, _build_vals(self.build, ctx))
        try:
            client.execute(self.model, self.method, [rid])
            return False, f"{self.method} 未抛异常（守卫缺失？）"
        except xmlrpc.client.Fault as e:
            return True, f"已按预期拦截: {e.faultString[:60]}"
        finally:
            try:
                client.unlink(self.model, [rid])
            except Exception:  # noqa: BLE001 - 清理失败不影响守卫判定
                pass


@dataclass
class SelectionViolationCase(Case):
    """非法 selection 值：对记录写非法 selection，期望抛异常（被拒）。"""
    field: str
    bad: str

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        rid = ctx.get("pr_id")
        if not rid:
            return False, "缺少测试 PR 记录（数据层自愈未完成）"
        try:
            client.write(self.model, [rid], {self.field: self.bad})
            return False, f"写非法 selection {self.field}={self.bad} 未被拦截"
        except xmlrpc.client.Fault as e:
            return True, f"已按预期拦截: {e.faultString[:60]}"


@dataclass
class BusinessCase(Case):
    """正向业务数值断言：执行 action，断言达到 PRD 规定的业务状态/字段。

    期望值（expect_state / expect_field）来自 prd/rules.py，其唯一权威为
    验收清单.md / 作品说明.md（见 P0#3 红线：业务数值期望仅以 PRD 为权威，
    严禁从代码反推 state 字符串再断言代码）。
    """
    mode: str
    expect_state: str
    expect_field: str = ""

    def run(self, client, ctx: Dict) -> Tuple[bool, str]:
        if self.mode == "submit":
            rid = self._make_pr(client, ctx)
            try:
                self._call_action(client, self.model, "action_submit", [rid])
                return self._check(client, rid)
            finally:
                self._cleanup(client, rid)
        if self.mode == "genpo":
            rid = self._make_pr(client, ctx)
            po_ids = []
            try:
                client.write(self.model, [rid], {"partner_id": ctx["supplier_id"]})
                self._call_action(client, self.model, "action_submit", [rid])
                self._call_action(client, self.model, "action_generate_po", [rid])
                rec = client.read(self.model, [rid], ["state", "po_ids"])[0]
                ok = rec["state"] == self.expect_state
                detail = f"state={rec['state']}"
                if self.expect_field:
                    ok = ok and bool(rec.get(self.expect_field))
                    detail += f", {self.expect_field}={rec.get(self.expect_field)}"
                # B6 深度断言：生成的原生采购单字段正确（供应商/明细/公司）
                po_ids = rec.get("po_ids") or []
                if not po_ids:
                    ok = False
                    detail += ", 未生成PO"
                else:
                    po = client.read(
                        "purchase.order", [po_ids[0]],
                        ["partner_id", "order_line", "company_id", "origin"],
                    )[0]
                    if not po.get("partner_id") or po["partner_id"][0] != ctx["supplier_id"]:
                        ok = False
                        detail += ", PO供应商不匹配"
                    if not po.get("order_line"):
                        ok = False
                        detail += ", PO明细为空"
                    else:
                        detail += f", PO明细={len(po['order_line'])}行"
                    if po.get("company_id") and po["company_id"][0] != ctx["company_id"]:
                        ok = False
                        detail += ", PO公司不匹配"
                return ok, detail
            finally:
                try:
                    client.unlink(self.model, [rid])
                except Exception:  # noqa: BLE001 - 清理失败不影响判定
                    pass
                for pid in po_ids:
                    try:
                        client.unlink("purchase.order", [pid])
                    except Exception:  # noqa: BLE001 - 清理失败不影响判定
                        pass
        if self.mode == "po_approve":
            # B3 / 验收清单 C2：PO 审批流 草稿→待审→已批，未批禁止确认
            po_id = client.create("purchase.order", {
                "partner_id": ctx["supplier_id"],
                "order_line": [(0, 0, {
                    "product_id": ctx["ingredient_id"],
                    "product_uom": ctx["ingredient_uom_id"],
                    "product_qty": 1.0,
                    "price_unit": 10.0,  # 金额>0 才能进入审批
                })],
            })
            try:
                # 未审批禁止确认（[Unwanted] 守卫）
                try:
                    client.execute("purchase.order", "button_confirm", [po_id])
                    blocked = False
                    block_detail = "未审批却允许确认(守卫缺失)"
                except xmlrpc.client.Fault:
                    blocked = True
                    block_detail = "未审批确认被正确拦截"
                # 提交审批 -> pending（action 返回 None，经 _call_action 吞掉 marshal None）
                self._call_action(client, "purchase.order", "action_submit_for_approval", [po_id])
                st1 = client.read("purchase.order", [po_id], ["approval_state"])[0]["approval_state"]
                # 审批通过 -> approved，并记录审批人
                self._call_action(client, "purchase.order", "action_approve", [po_id])
                rec = client.read("purchase.order", [po_id],
                                  ["approval_state", "approved_by"])[0]
                ok = (blocked and st1 == "pending"
                      and rec["approval_state"] == self.expect_state
                      and bool(rec["approved_by"]))
                detail = (f"{block_detail}; submit={st1}; "
                          f"approve={rec['approval_state']}; approver={rec['approved_by']}")
                return ok, detail
            finally:
                try:
                    client.unlink("purchase.order", [po_id])
                except Exception:  # noqa: BLE001 - 清理失败不影响判定
                    pass

        if self.mode == "ack_confirm":
            aid = client.create("sc.supplier.ack", {"po_id": ctx["po_id"]})
            try:
                # committed_date 是 action_confirm 的方法参数（非记录字段）
                self._call_action(client, "sc.supplier.ack", "action_confirm", [aid],
                                  {"committed_date": "2026-12-31"})
                st = client.read("sc.supplier.ack", [aid], ["state"])[0]["state"]
                ok = st == self.expect_state
                return ok, f"state={st}"
            finally:
                try:
                    client.unlink("sc.supplier.ack", [aid])
                except Exception:  # noqa: BLE001 - 清理失败不影响业务判定
                    pass
        return False, f"unknown mode: {self.mode}"

    @staticmethod
    def _call_action(client, model, method, ids, kwargs=None):
        """调用 action 方法；容忍 Odoo 因返回值 None 导致的 XML-RPC 序列化报错。

        Odoo 部分 action 方法（action_submit / action_confirm 等）无显式返回值
        （返回 None），而 Odoo XML-RPC 默认 allow_none=False，会在序列化响应时抛
        'cannot marshal None'。但方法的副作用（write 状态）已在服务端执行并提交，
        因此以被测记录的实际状态为准，不依赖返回值。
        """
        try:
            client.execute(model, method, ids, **(kwargs or {}))
        except xmlrpc.client.Fault as e:
            if "cannot marshal None" not in e.faultString:
                raise

    def _make_pr(self, client, ctx: Dict) -> int:
        return client.create("sc.purchase.request", {
            "name": "__m2_biz__",
            "company_id": ctx["company_id"],
            "warehouse_id": ctx["warehouse_id"],
            "line_ids": [(0, 0, {"product_id": ctx["ingredient_id"],
                                 "product_uom": ctx["ingredient_uom_id"],
                                 "product_uom_qty": 1.0})],
        })

    def _check(self, client, rid: int) -> Tuple[bool, str]:
        fields = ["state"]
        if self.expect_field:
            fields.append(self.expect_field)
        rec = client.read(self.model, [rid], fields)[0]
        ok = rec["state"] == self.expect_state
        detail = f"state={rec['state']}"
        if self.expect_field:
            ok = ok and bool(rec.get(self.expect_field))
            detail += f", {self.expect_field}={rec.get(self.expect_field)}"
        return ok, detail

    def _cleanup(self, client, rid: int) -> None:
        try:
            client.unlink(self.model, [rid])
        except Exception:  # noqa: BLE001 - 清理失败不影响业务判定
            pass


# ---------- vals 构造（校验所需测试数据由 healer 幂等提供） ----------
def _build_vals(build: str, ctx: Dict) -> Dict:
    if build == "recipe_zero_qty":
        return {"name": "__m2_rt__", "finished_product_tmpl_id": ctx["proc_tmpl_id"],
                "line_ids": [(0, 0, {"product_id": ctx["ingredient_id"], "product_qty": 0.0})]}
    if build == "recipe_comp_eq_prod":
        return {"name": "__m2_rt__", "finished_product_tmpl_id": ctx["proc_tmpl_id"],
                "line_ids": [(0, 0, {"product_id": ctx["proc_product_id"], "product_qty": 1.0})]}
    if build == "recipe_valid":
        return {"name": "__m2_rt__", "finished_product_tmpl_id": ctx["proc_tmpl_id"],
                "line_ids": [(0, 0, {"product_id": ctx["ingredient_id"], "product_qty": 1.0})]}
    if build == "ack_confirm":
        return {"po_id": ctx["po_id"]}
    raise ValueError(f"unknown build: {build}")


def _build_write(field: str, kind: str) -> Dict:
    if field == "line_ids" and kind == "remove_all_lines":
        return {"line_ids": [(5, 0, 0)]}
    raise ValueError(f"unknown write: {field}/{kind}")


# ---------- 用例集合 ----------
def guard_cases() -> List[Case]:
    return [
        GuardCase("G-PR-SUBMIT", "无明细 PR 提交应被拒", "guard",
                  "sc.purchase.request", "action_submit"),
        GuardCase("G-PR-GENPO", "草稿态 PR 生成 PO 应被拒", "guard",
                  "sc.purchase.request", "action_generate_po"),
    ]


def create_violation_cases() -> List[Case]:
    return [
        CreateViolationCase("C-RECIPE-QTY", "配方用量必须大于0应被拒", "create",
                            "sc.recipe", "recipe_zero_qty"),
        CreateViolationCase("C-RECIPE-CMP", "原料不能与成品为同一物料应被拒", "create",
                            "sc.recipe", "recipe_comp_eq_prod"),
    ]


def write_violation_cases() -> List[Case]:
    return [
        WriteViolationCase("W-RECIPE-LINE", "配方至少需一种原料应被拒", "write",
                           "sc.recipe", "recipe_valid", "line_ids", "remove_all_lines"),
    ]


def action_guard_cases() -> List[Case]:
    return [
        CreateThenActionCase("G-ACK-CONF", "供应商确认交期缺失应被拒", "action",
                             "sc.supplier.ack", "ack_confirm", "action_confirm"),
    ]


def selection_violation_cases() -> List[Case]:
    return [
        SelectionViolationCase("S-PR-STATE", "PR 非法 state 应被拒", "selection",
                               "sc.purchase.request", "state", "__invalid__"),
    ]


def all_cases() -> List[Case]:
    return (guard_cases() + create_violation_cases() + write_violation_cases()
            + action_guard_cases() + selection_violation_cases())
