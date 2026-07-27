"""UI 自动化测试 fixtures（Playwright 驱动 Odoo 真实浏览器）。

架构说明：
- 纯黑盒：通过浏览器连被测 Odoo（默认 http://localhost:8069，即手工走查脚本所用实例），
  不 import odoo、不挂载 custom_addons，符合 supply-chain-odoo-tests 工程的黑盒原则。
- 运行环境：因宿主机代理仅放行白名单域名，浏览器驱动（Playwright + Chromium）安装在
  被测 Odoo 容器内（容器内可直连外网）。由主 docker-compose.yml 把本目录挂到容器内
  /mnt/ui_tests，再在容器内执行 pytest。
- 运行命令（在宿主机）：
    docker compose exec odoo bash -c "cd /mnt/ui_tests && python -m pytest -v"
"""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page

BASE_URL = os.getenv("UI_BASE_URL", "http://localhost:8069")
ADMIN_LOGIN = os.getenv("UI_ADMIN_LOGIN", "admin@example.com")
ADMIN_PASSWORD = os.getenv("UI_ADMIN_PASSWORD", "admin")


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """CI 容器内以 root 运行 Chromium 必须加 --no-sandbox（Chromium 安全限制：
    root + sandbox 直接拒启，导致 page fixture 初始化 ERROR）。本地非 root 运行不受影响。"""
    args = list(browser_type_launch_args.get("args", []))
    if "--no-sandbox" not in args:
        args.append("--no-sandbox")
    return {**browser_type_launch_args, "args": args}


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def logged_in(page: Page, base_url: str) -> Page:
    """打开被测实例并登录 admin，返回已登录的 page（可复用于后续用例）。"""
    page.goto(base_url)
    # 如果停在登录页，则填写并登录
    if page.locator("#login").count() > 0:
        page.fill("#login", ADMIN_LOGIN)
        page.fill("#password", ADMIN_PASSWORD)
        # 登录按钮兼容中文化「登录」或英文「Log in」：优先 primary 按钮
        page.locator("button.btn-primary, button[type=submit]").first.click()
    # 等待进入主页（出现顶部导航栏 = 已登录）
    page.wait_for_selector(".o_main_navbar", timeout=20000)
    return page


def open_menu(page: Page, *labels: str):
    """通过顶栏应用菜单(.o_navbar_apps_menu)逐级打开业务菜单。

    labels 为逐级菜单文本，如 open_menu(page, "库存", "产品")。
    第一步点击应用菜单按钮展开下拉，点一级菜单；后续层级在左侧侧边菜单中点开。
    """
    page.locator(".o_navbar_apps_menu").first.click()
    page.locator(".dropdown-menu").filter(has_text=labels[0]).first.wait_for(timeout=10000)
    dd = page.locator(".dropdown-menu").filter(has_text=labels[0]).first
    dd.locator("a, .dropdown-item, menuitem").filter(has_text=labels[0]).first.click()
    for label in labels[1:]:
        # 左侧 .o_menu_sections 的菜单组是 dropdown-toggle；点击展开后，
        # 子项浮层渲染在全局 .dropdown-menu 内，再点其中的子项链接
        group = page.locator(".o_menu_sections").get_by_text(label, exact=True).first
        group.wait_for(timeout=10000)
        group.click()
        page.wait_for_timeout(800)
        sub = page.locator(".dropdown-menu a").filter(has_text=label).first
        if sub.count() > 0:
            sub.click()
