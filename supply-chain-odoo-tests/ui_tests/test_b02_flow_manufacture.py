"""TC-B02 流程制造物料（UI 自动化）。

对应 演示走查脚本.md 的 TC-B02：新建库存产品并勾选「流程制造」，
验证系统自动开启制造相关能力与追溯页签（这正是之前文档修正过的字段标签点）。

注意：本用例不保存，结束后点「放弃」清理，避免污染演示数据。
"""
import time

from playwright.sync_api import expect

from conftest import open_menu


def test_b02_product_flow_manufacture(logged_in):
    open_menu(logged_in, "库存", "产品")
    # 产品列表默认看板视图，「新建」按钮为 .o-kanban-button-new
    new_btn = logged_in.locator(".o-kanban-button-new")
    if new_btn.count() == 0:
        new_btn = logged_in.locator(".o_list_button_add")
    if new_btn.count() == 0:
        new_btn = logged_in.get_by_text("新建", exact=False)
    new_btn.first.click()

    ts = int(time.time())
    name_box = logged_in.locator(".o_form_view input.o_input").first
    name_box.fill("UI测试流程制造_%d" % ts)

    # 「流程制造」字段在「基本信息」页签，标签文本为「流程制造」
    # Odoo 18 OWL 字段 input 无 name 属性，用标签文本定位并点击（label 关联 checkbox）
    flow_label = logged_in.locator(
        ".o_form_label:has-text('流程制造'), label:has-text('流程制造')"
    ).first
    flow_label.click()

    # 切到「库存」页签，验证惰性渲染（按批次 / 有效期等字段出现）
    inv_tab = logged_in.locator(".o_form_notebook_headers li, .nav-tabs li").filter(has_text="库存").first
    inv_tab.click()
    expect(
        logged_in.locator(".o_form_view").filter(has_text="有效期").first
    ).to_be_visible()

    # 放弃（不污染演示数据）
    cancel = logged_in.locator(".o_form_button_cancel")
    if cancel.count() == 0:
        cancel = logged_in.get_by_text("放弃", exact=False)
    if cancel.count() > 0:
        cancel.first.click()
