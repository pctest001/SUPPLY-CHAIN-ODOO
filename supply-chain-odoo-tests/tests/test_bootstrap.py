"""M1 验收冒烟：验证被测实例可达、可登录、核心模块已安装、多公司前置就绪。"""
import pytest


def test_odoo_reachable(odoo_client):
    assert odoo_client.authenticated_uid


def test_core_models_installed(odoo_client):
    for model in ("sc.purchase.request", "sc.recipe", "sc.supplier.ack", "ai.config"):
        assert odoo_client.model_exists(model), f"模型缺失（模块未安装?）: {model}"


def test_two_companies_exist(company_pair):
    a, b = company_pair
    assert a["id"] != b["id"]


def test_cross_company_user_ready(cross_company_user):
    assert isinstance(cross_company_user, int) and cross_company_user > 0
