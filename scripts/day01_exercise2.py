# -*- coding: utf-8 -*-
"""
练习 2：解析 JSON 采购订单
==========================
需求：输入 JSON 格式的采购订单字符串，返回物料明细列表。

采购订单 JSON 结构示例：
    {
        "order_no":  "PO-2026-001",
        "supplier":  "华东五金有限公司",
        "order_date":"2026-07-23",
        "status":    "pending",
        "items": [
            {"material_name": "螺丝M8",   "quantity": 500, "unit_price": 0.50,  "unit": "个"},
            {"material_name": "电机750W", "quantity": 10,  "unit_price": 320.0, "unit": "台"}
        ]
    }

目标：从 JSON 字符串中解析出 items，返回物料明细列表。
"""

import json


# ------------------------------------------------------------------
# 基础版：解析 JSON → 返回 items 列表
# ------------------------------------------------------------------
def parse_purchase_order(json_str):
    """
    解析 JSON 采购订单，返回物料明细列表。

    参数
    ----
    json_str : str
        JSON 格式的采购订单字符串。

    返回
    ----
    list[dict]
        物料明细列表（即 JSON 中的 items 字段）。
    """
    order = json.loads(json_str)        # 字符串 → 字典
    return order["items"]               # 取出物料明细


# ------------------------------------------------------------------
# 进阶版：解析 + 计算每行小计（quantity × unit_price）
# ------------------------------------------------------------------
def parse_purchase_order_with_total(json_str):
    """
    解析采购订单，并为每条明细补充 line_total（小计金额）。

    返回
    ----
    list[dict]
        每条明细增加一个 line_total 字段 = quantity * unit_price。
    """
    order = json.loads(json_str)
    items = order["items"]

    for item in items:
        item["line_total"] = round(item["quantity"] * item["unit_price"], 2)

    return items


# ------------------------------------------------------------------
# 健壮版：处理异常情况
#   - JSON 字符串非法        → 返回 []
#   - 缺少 items 字段         → 返回 []
    #   - items 为空             → 返回 []
#   - 某条明细缺 quantity/price → 该字段补 0
#   - quantity/price 为 None   → 视为 0
# ------------------------------------------------------------------
def parse_purchase_order_safe(json_str):
    """
    健壮版解析：容错处理各种异常数据。

    返回
    ----
    list[dict]
        物料明细列表，每条含 material_name / quantity / unit_price / unit / line_total。
        出错时返回空列表，不抛异常。
    """
    # 1. JSON 解析失败 → 返回空列表
    try:
        order = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return []

    # 2. 没有 items 字段 → 返回空列表
    items = order.get("items")
    if not items or not isinstance(items, list):
        return []

    # 3. 逐条处理明细，补全缺失字段
    result = []
    for item in items:
        name   = item.get("material_name", "未知物料")
        qty    = item.get("quantity") or 0
        price  = item.get("unit_price") or 0
        unit   = item.get("unit", "")

        result.append({
            "material_name": name,
            "quantity":      qty,
            "unit_price":    price,
            "unit":          unit,
            "line_total":    round(qty * price, 2),
        })

    return result


# ==================================================================
# 测试
# ==================================================================
if __name__ == "__main__":

    # ---- 正常采购订单 JSON ----
    po_json = json.dumps({
        "order_no":   "PO-2026-001",
        "supplier":   "华东五金有限公司",
        "order_date": "2026-07-23",
        "status":     "pending",
        "items": [
            {"material_name": "螺丝M8",    "quantity": 500,  "unit_price": 0.50,  "unit": "个"},
            {"material_name": "电机750W",  "quantity": 10,   "unit_price": 320.0, "unit": "台"},
            {"material_name": "电缆10m",   "quantity": 30,   "unit_price": 45.0,  "unit": "根"},
            {"material_name": "继电器24V", "quantity": 100,  "unit_price": 12.0,  "unit": "只"},
        ]
    }, ensure_ascii=False)

    # ---- 基础版 ----
    print("=== 基础版 ===")
    items = parse_purchase_order(po_json)
    for i in items:
        print(f"  {i['material_name']:10s}  {i['quantity']:>4} {i['unit']}  ¥{i['unit_price']}")
    print(f"  共 {len(items)} 条明细")

    # ---- 进阶版（含小计）----
    print("\n=== 进阶版（含小计）===")
    items_with_total = parse_purchase_order_with_total(po_json)
    grand_total = 0
    for i in items_with_total:
        print(f"  {i['material_name']:10s}  {i['quantity']:>4} × ¥{i['unit_price']:<7} = ¥{i['line_total']:<10}")
        grand_total += i["line_total"]
    print(f"  {'订单合计':>10s}  {'':>4}   {'':<8}   ¥{grand_total:.2f}")

    # ---- 健壮版：异常数据测试 ----
    print("\n=== 健壮版：非法 JSON ===")
    print("  结果：", parse_purchase_order_safe("这不是JSON"))

    print("\n=== 健壮版：缺少 items 字段 ===")
    no_items_json = json.dumps({"order_no": "PO-001", "supplier": "测试"}, ensure_ascii=False)
    print("  结果：", parse_purchase_order_safe(no_items_json))

    print("\n=== 健壮版：items 为空 ===")
    empty_items_json = json.dumps({"order_no": "PO-002", "items": []}, ensure_ascii=False)
    print("  结果：", parse_purchase_order_safe(empty_items_json))

    print("\n=== 健壮版：明细缺字段 ===")
    dirty_json = json.dumps({
        "order_no": "PO-003",
        "items": [
            {"material_name": "螺丝M8",   "quantity": 100, "unit_price": 0.5},  # 缺 unit
            {"material_name": "电机",     "quantity": 5},                        # 缺 unit_price
            {"quantity": 20},                                                     # 缺 material_name
        ]
    }, ensure_ascii=False)
    dirty_result = parse_purchase_order_safe(dirty_json)
    for i in dirty_result:
        print(f"  {i['material_name']:10s}  qty={i['quantity']:>4}  price={i['unit_price']}  total={i['line_total']}")

    # ---- 断言验证 ----
    print("\n=== 断言验证 ===")
    assert len(parse_purchase_order(po_json)) == 4, "基础版应返回 4 条明细"
    assert parse_purchase_order_with_total(po_json)[0]["line_total"] == 250.0, "螺丝M8小计应为250.0"
    assert parse_purchase_order_safe("bad json") == [], "非法JSON应返回空列表"
    assert parse_purchase_order_safe(no_items_json) == [], "缺items应返回空列表"
    assert parse_purchase_order_safe(empty_items_json) == [], "空items应返回空列表"
    assert len(parse_purchase_order_safe(dirty_json)) == 3, "脏数据应返回3条"
    print("✓ 所有断言通过！")
