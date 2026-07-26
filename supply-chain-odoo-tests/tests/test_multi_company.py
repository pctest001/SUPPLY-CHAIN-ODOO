"""B4：多公司隔离基础验证（验收清单 A 组『双模块+演示组织(华南/华东)』前置 / 作品说明 G4 权限继承）。

本组锁定多公司『公司域被正确写入』这一前置不变量：
- 跨公司测试用户确实归属第二家公司（fixture 正确）；
- 以显式 company_id 创建的采购申请，其 company_id 被如实记录（公司域机制生效）。

注：完整的 ir.rule 行级隔离（华东用户 AI 查询 0 条华南泄漏）属更深一层，依赖具体 ACL，
此处先锁定公司域写入不变量，避免对未实现的行级规则误报。
"""
from src.healer.audit import get_audit

import pytest

pytestmark = pytest.mark.multicompany


def test_crossco_user_in_other_company(odoo_client, company_pair, cross_company_user):
    """跨公司测试用户应归属第二家公司。"""
    _, other = company_pair
    rec = odoo_client.read("res.users", [cross_company_user], ["company_id"])[0]
    assert rec["company_id"] and rec["company_id"][0] == other["id"], \
        "跨公司测试用户应归属第二家公司"


def test_pr_company_scoped(odoo_client, company_pair, healed_env):
    """以显式 company_id 创建的采购申请，其 company_id 应被如实记录。"""
    _, other = company_pair
    # 取第二家公司的仓库，避免公司与仓库跨 company 的域冲突
    wh = odoo_client.search_read(
        "stock.warehouse", [("company_id", "=", other["id"])], fields=["id"], limit=1
    )
    wh_id = wh[0]["id"] if wh else healed_env["warehouse_id"]
    rid = odoo_client.create("sc.purchase.request", {
        "name": "__m2_mc__",
        "company_id": other["id"],
        "warehouse_id": wh_id,
    })
    try:
        rec = odoo_client.read("sc.purchase.request", [rid], ["company_id"])[0]
        assert rec["company_id"] and rec["company_id"][0] == other["id"], \
            "显式指定 company_id 的采购申请应归属该公司"
        get_audit().log("data", "info", "case:PR-COMPANY-SCOPED", f"rid={rid}")
    finally:
        try:
            odoo_client.unlink("sc.purchase.request", [rid])
        except Exception:  # noqa: BLE001 - 清理失败不影响判定
            pass
