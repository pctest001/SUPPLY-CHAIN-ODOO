# -*- coding: utf-8 -*-
"""
练习 1：库存预警函数
===================
需求：输入物料列表，返回库存低于安全库存的物料名。

物料数据结构（字典）示例：
    {
        "name": "螺丝M8",      # 物料名称
        "stock": 120,           # 当前库存
        "safety_stock": 200     # 安全库存
    }

目标：写一个函数，把所有 stock < safety_stock 的物料名找出来。
"""


# ------------------------------------------------------------------
# 函数实现
# ------------------------------------------------------------------
def find_low_stock(materials):
    """
    找出库存低于安全库存的物料。

    参数
    ----
    materials : list[dict]
        物料列表，每个元素是包含 name / stock / safety_stock 的字典。

    返回
    ----
    list[str]
        库存不足的物料名称列表；若无则返回空列表。
    """
    low_stock_names = []
    for m in materials:
        # 当前库存 < 安全库存 → 预警
        if m["stock"] < m["safety_stock"]:
            low_stock_names.append(m["name"])
    return low_stock_names


# ------------------------------------------------------------------
# 进阶写法：列表推导式（一行搞定，效果一样）
# ------------------------------------------------------------------
def find_low_stock_v2(materials):
    """用列表推导式实现，更简洁。"""
    return [
        m["name"]
        for m in materials
        if m["stock"] < m["safety_stock"]
    ]


# ------------------------------------------------------------------
# 健壮性增强版：处理缺失字段 / 空列表
# ------------------------------------------------------------------
def find_low_stock_safe(materials):
    """
    健壮版本：
    - 空列表 → 返回 []
    - 缺少 stock / safety_stock 字段 → 跳过该物料（不报错）
    - stock 或 safety_stock 为 None → 视为 0
    """
    if not materials:
        return []

    result = []
    for m in materials:
        name = m.get("name", "未命名物料")
        stock = m.get("stock") or 0
        safety = m.get("safety_stock") or 0
        if stock < safety:
            result.append(name)
    return result


# ==================================================================
# 测试
# ==================================================================
if __name__ == "__main__":

    # ---- 测试数据 ----
    materials = [
        {"name": "螺丝M8",   "stock": 120,  "safety_stock": 200},   # 不足 ✓
        {"name": "垫片D10",  "stock": 500,  "safety_stock": 300},   # 充足
        {"name": "电机750W", "stock": 15,   "safety_stock": 20},    # 不足 ✓
        {"name": "电缆10m",  "stock": 800,  "safety_stock": 100},   # 充足
        {"name": "继电器24V","stock": 8,    "safety_stock": 50},    # 不足 ✓
    ]

    # ---- 运行函数 ----
    print("=== 基础版 ===")
    result = find_low_stock(materials)
    print("库存不足的物料：", result)

    print("\n=== 列表推导式版 ===")
    result2 = find_low_stock_v2(materials)
    print("库存不足的物料：", result2)

    # ---- 健壮性测试 ----
    print("\n=== 健壮版（含异常数据）===")
    dirty_data = [
        {"name": "螺丝M8",  "stock": 10, "safety_stock": 100},   # 不足
        {"name": "缺字段",  "stock": 5},                           # 缺 safety_stock → 跳过
        {"name": "None值",  "stock": None, "safety_stock": 50},   # stock=0 < 50 → 不足
        {},                                                     # 空字典 → 跳过
    ]
    result3 = find_low_stock_safe(dirty_data)
    print("库存不足的物料：", result3)

    # ---- 空列表测试 ----
    print("\n=== 空列表测试 ===")
    print("空列表结果：", find_low_stock_safe([]))

    # ---- 断言验证 ----
    print("\n=== 断言验证 ===")
    assert find_low_stock(materials) == ["螺丝M8", "电机750W", "继电器24V"], "基础版结果不对！"
    assert find_low_stock_v2(materials) == ["螺丝M8", "电机750W", "继电器24V"], "推导式版结果不对！"
    assert find_low_stock_safe([]) == [], "空列表应返回空列表！"
    print("✓ 所有断言通过！")
