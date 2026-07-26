"""pytest 全局 fixtures：连接被测实例、多公司账号、演示数据。

对应技术方案 v2.1：
  - odoo_client / admin_uid：session 级连接，认证失败给出初始化提示；
  - company_pair / cross_company_user：多公司测试前置（被测实例已含华南/华东两公司）。
"""
from __future__ import annotations

import os

import pytest

from src.healer.audit import get_audit
from src.healer.heal import check_modules_installed, ensure_demo_data, ensure_environment
from src.odoo_client import OdooClient

URL = os.getenv("ODOO_URL", "http://localhost")
PORT = int(os.getenv("ODOO_PORT", "18069"))
DB = os.getenv("ODOO_DB", "test_supplychain")
ADMIN_LOGIN = os.getenv("ODOO_ADMIN_LOGIN", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ODOO_ADMIN_PASSWORD", "admin")

# 跨公司测试用户的固定凭据（归属第二家公司）
CROSSCO_LOGIN = "test_crossco@example.com"
CROSSCO_PASSWORD = "test123"


def _make_client() -> OdooClient:
    client = OdooClient(URL, DB, ADMIN_LOGIN, ADMIN_PASSWORD, PORT)
    client.authenticate()
    return client


@pytest.fixture(scope="session")
def odoo_client() -> OdooClient:
    return _make_client()


@pytest.fixture(scope="session")
def admin_uid(odoo_client: OdooClient) -> int:
    return odoo_client.uid


# ---------- 三层自愈（M2） ----------
@pytest.fixture(scope="session")
def healed_env(odoo_client: OdooClient) -> dict:
    """session 级前置：环境/数据/配置三层自愈 + 全量审计。

    红线：自愈只发生在用例执行『之前』，绝不捕获用例断言失败去自愈；
    自愈后仍不就绪则整个 session 失败（不掩盖真实回归）。审计写入 healer_audit.jsonl。
    """
    audit = get_audit()
    audit.reset()

    ok = ensure_environment(odoo_client)
    assert ok, "被测实例不可达，环境层自愈失败（见 healer_audit.jsonl）"

    missing = check_modules_installed(odoo_client, ["supply_chain_demo", "sc_ai", "sc_log_trace"])
    assert not missing, f"模块未安装，需 CI 受控安装: {missing}"

    data = ensure_demo_data(odoo_client)
    audit.log("data", "info", "ready", f"pr_id={data.get('pr_id')}, crossco_uid={data.get('crossco_uid')}")
    return data


# ---------- 多公司 ----------
@pytest.fixture(scope="session")
def company_pair(odoo_client: OdooClient):
    """返回 (主公司, 第二家公司) 两份 res.company 记录。"""
    companies = odoo_client.search_read("res.company", [], fields=["id", "name"])
    assert len(companies) >= 2, "被测实例需至少 2 个公司（华南/华东工厂）用于多公司测试"
    return companies[0], companies[1]


@pytest.fixture(scope="session")
def cross_company_user(odoo_client: OdooClient, company_pair):
    """创建（或复用）一个归属第二家公司的普通用户，用于权限/隔离测试。幂等。"""
    _, other = company_pair
    existing = odoo_client.search("res.users", [("login", "=", CROSSCO_LOGIN)])
    if existing:
        return existing[0]
    gid = odoo_client.search_read(
        "ir.model.data",
        [("module", "=", "base"), ("name", "=", "group_user")],
        fields=["res_id"],
    )[0]["res_id"]
    return odoo_client.create(
        "res.users",
        {
            "name": "CrossCo Tester",
            "login": CROSSCO_LOGIN,
            "password": CROSSCO_PASSWORD,
            "company_id": other["id"],
            "company_ids": [(6, 0, [other["id"]])],
            "groups_id": [(6, 0, [gid])],
        },
    )
