"""三层自愈（环境 / 数据 / 配置）。

设计红线（见技术方案 v2.1 P0#2、P0#3）：
1. 自愈只发生在『用例执行之前』的环境准备阶段，绝不捕获用例断言失败去自愈；
   用例执行后若失败，一律交给 pytest 判定，绝不掩盖真实回归。
2. 自愈动作全量写审计（audit.log）。
3. 配置层自救（模块未装）只『检测并报告』，真正安装由 CI 受控脚本完成，
   不在运行时 RPC 自动执行（避免误装/误改 SUT 业务配置）。
"""
from __future__ import annotations

import time
import xmlrpc.client

from .audit import get_audit

# 测试用 PR 草稿的唯一标记，便于自愈幂等识别与清理
TEST_PR_REF = "__m2_test_pr__"
# 跨公司测试用户（与 conftest 约定一致）
CROSSCO_LOGIN = "test_crossco@example.com"


def ensure_environment(client, retries: int = 5, wait: float = 3.0) -> bool:
    """环境层自愈：被测实例不可达时等待重试（不擅自重启、不改业务）。"""
    audit = get_audit()
    for i in range(1, retries + 1):
        try:
            client.authenticate()
            audit.log("env", "info", "reachable", f"uid={client.uid}")
            return True
        except Exception as e:  # noqa: BLE001 - 环境未就绪属于预期可自愈情景
            audit.log("env", "heal", f"retry {i}/{retries}", str(e)[:200])
            time.sleep(wait)
    audit.log("env", "fail", "unreachable", "被测实例在重试后仍不可达")
    return False


def ensure_demo_data(client) -> dict:
    """数据层自愈：幂等确保测试前置数据存在。返回测试记录 id 映射。"""
    audit = get_audit()
    out: dict = {}

    # 公司 / 仓库（供 PR 构造复用）
    companies = client.search_read("res.company", [], fields=["id", "name"], limit=1)
    company_id = companies[0]["id"] if companies else None
    out["company_id"] = company_id
    wh = client.search_read("stock.warehouse", [("company_id", "=", company_id)],
                            fields=["id"], limit=1) if company_id else None
    out["warehouse_id"] = wh[0]["id"] if wh else None

    # 测试 PR 草稿（无明细、draft 态），供守卫/selection 用例复用
    existing = client.search("sc.purchase.request", [("name", "=", TEST_PR_REF)])
    if existing:
        out["pr_id"] = existing[0]
    elif company_id and out["warehouse_id"]:
        out["pr_id"] = client.create("sc.purchase.request", {
            "name": TEST_PR_REF,
            "company_id": company_id,
            "warehouse_id": out["warehouse_id"],
        })
        audit.log("data", "heal", "create_test_pr", f"id={out['pr_id']}")
    else:
        audit.log("data", "fail", "no_company_or_warehouse", "无公司/仓库，无法造测试 PR")
        return out

    # 跨公司测试用户（幂等）
    cru = client.search("res.users", [("login", "=", CROSSCO_LOGIN)])
    if cru:
        out["crossco_uid"] = cru[0]
    else:
        other = client.search_read("res.company", [], fields=["id", "name"])
        if len(other) < 2:
            audit.log("data", "fail", "need_2_companies", "跨公司测试需至少 2 家公司")
            return out
        gid = client.search_read(
            "ir.model.data",
            [("module", "=", "base"), ("name", "=", "group_user")],
            fields=["res_id"],
        )
        if not gid:
            audit.log("data", "fail", "no_group_user", "找不到 base.group_user")
            return out
        uid = client.create("res.users", {
            "name": "CrossCo",
            "login": CROSSCO_LOGIN,
            "password": "test123",
            "company_id": other[1]["id"],
            "company_ids": [(6, 0, [other[1]["id"]])],
            "groups_id": [(6, 0, [gid[0]["res_id"]])],
        })
        audit.log("data", "heal", "create_crossco_user", f"uid={uid}")
        out["crossco_uid"] = uid

    # 流程制造成品模板（is_process_mfg 自动置 is_storable / tracking=lot）
    proc = client.search("product.template", [("name", "=", "__m2_proc__")])
    out["proc_tmpl_id"] = proc[0] if proc else client.create(
        "product.template", {"name": "__m2_proc__", "is_process_mfg": True})
    proc_prod = client.search_read(
        "product.product", [("product_tmpl_id", "=", out["proc_tmpl_id"])], fields=["id"])
    out["proc_product_id"] = proc_prod[0]["id"] if proc_prod else None

    # 原料模板（可库存）
    ing = client.search("product.template", [("name", "=", "__m2_ing__")])
    out["ingredient_tmpl_id"] = ing[0] if ing else client.create(
        "product.template", {"name": "__m2_ing__", "is_storable": True})
    ing_prod = client.search_read(
        "product.product", [("product_tmpl_id", "=", out["ingredient_tmpl_id"])],
        fields=["id", "uom_id"])
    out["ingredient_id"] = ing_prod[0]["id"] if ing_prod else None
    out["ingredient_uom_id"] = None
    if ing_prod:
        uom = ing_prod[0]["uom_id"]
        out["ingredient_uom_id"] = uom[0] if isinstance(uom, (list, tuple)) else uom

    # 供应商
    sup = client.search("res.partner", [("name", "=", "__m2_sup__")])
    out["supplier_id"] = sup[0] if sup else client.create(
        "res.partner", {"name": "__m2_sup__", "supplier_rank": 1})

    # 采购单（用原料作为行），供 sc.supplier.ack 守卫用例。
    # 测试库为专用空库（仅自愈造的数据），按 supplier_id 查我们造的 PO 即可（幂等）。
    po = client.search("purchase.order", [("partner_id", "=", out["supplier_id"])])
    if po:
        out["po_id"] = po[0]
    elif out["ingredient_id"]:
        out["po_id"] = client.create("purchase.order", {
            "partner_id": out["supplier_id"],
            "order_line": [(0, 0, {"product_id": out["ingredient_id"], "product_qty": 1.0})],
        })
        audit.log("data", "heal", "create_test_po", f"id={out['po_id']}")

    return out


def check_modules_installed(client, modules) -> list:
    """配置层检测：返回未安装的模块（不自装，交由 CI 受控脚本）。

    注意：模块技术名（如 supply_chain_demo）≠ 模型名，必须查 ir.module.module.state，
    不能复用查 ir.model 的 model_exists。
    """
    audit = get_audit()
    missing = []
    for m in modules:
        installed = client.execute(
            "ir.module.module", "search_count",
            [("name", "=", m), ("state", "in", ["installed", "to upgrade"])],
        )
        if not installed:
            missing.append(m)
    if missing:
        audit.log("config", "fail", "modules_missing", ",".join(missing))
    else:
        audit.log("config", "info", "modules_ok", ",".join(modules))
    return missing
