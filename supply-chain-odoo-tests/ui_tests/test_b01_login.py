"""TC-B01 登录与界面语言（UI 自动化）。

对应 演示走查脚本.md 的 TC-B01。注意：当前数据库界面语言为 en_US，
登录页按钮显示英文「Log in」（已用诊断确认），故登录按钮断言兼容中英文。
登录后 admin 用户语言为 zh_CN，主页为中文，应用菜单含中文业务菜单。

覆盖点：
  - 登录页具备账号/密码输入框与登录按钮（兼容中英文）
  - 登录后进入主页（非数据库选择页）
  - 打开应用菜单能找到中文业务菜单「采购」「库存」
"""
from playwright.sync_api import expect


def _goto_login(page):
    page.goto("/web/login")
    page.wait_for_selector("#login", timeout=15000)


def test_b01_login_form_present(logged_in):
    """步骤1：登录页具备账号/密码输入框与登录按钮（兼容中英文界面）。

    注：当前数据库未中文化，登录页按钮显示英文「Log in」（已诊断确认）；
    登录后 admin 用户语言为 zh_CN，主页为中文。本用例对登录按钮做中英文兼容。
    """
    _goto_login(logged_in)
    expect(logged_in.locator("#login")).to_be_visible()
    expect(logged_in.locator("#password")).to_be_visible()
    # 登录按钮：兼容「登录」或「Log in」
    expect(
        logged_in.locator("button:has-text('登录'), button:has-text('Log in')")
    ).to_be_visible()


def test_b01_login_enters_home_not_db_picker(logged_in):
    """步骤2：登录后直接进主页，而非数据库选择页。"""
    expect(logged_in.locator(".o_main_navbar")).to_be_visible()
    # 不应停留在数据库选择页
    expect(logged_in.locator("text=Select a database")).to_have_count(0)


def test_b01_search_chinese_menus(logged_in):
    """步骤3：打开应用菜单，能找到中文业务菜单「采购」「库存」。"""
    logged_in.locator(".o_navbar_apps_menu").first.click()
    dd = logged_in.locator(".dropdown-menu").filter(has_text="采购").first
    expect(dd).to_be_visible()
    expect(dd).to_contain_text("库存")
