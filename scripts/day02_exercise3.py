# -*- coding: utf-8 -*-
"""
练习 3：按仓库分组物料
=====================

需求：写一个函数，接收「物料字典列表」，返回 {仓库名: [物料名]} 分组字典。

物料数据结构（字典）示例：
    {
        "name": "螺丝M8",      # 物料名称
        "warehouse": "A仓"      # 所属仓库
    }

目标：
    输入：[{"name": "MAT-001", "warehouse": "A仓"},
           {"name": "MAT-002", "warehouse": "A仓"},
           {"name": "MAT-003", "warehouse": "B仓"}]
    输出：{"A仓": ["MAT-001", "MAT-002"], "B仓": ["MAT-003"]}

对应学习计划 Day 2 上午内容：
    函数定义 / 参数 / 返回值 / lambda / 标准库 import
"""


# ------------------------------------------------------------------
# 函数实现 1：基础版（for 循环 + dict.setdefault）
# ------------------------------------------------------------------
def group_by_warehouse(materials):
    """
    按仓库分组物料名。

    参数
    ----
    materials : list[dict]
        物料列表，每个元素含 name / warehouse 字段。

    返回
    ----
    dict[str, list[str]]
        仓库名 -> 该仓库物料名列表。
    """
    result = {}
    for m in materials:
        wh = m["warehouse"]            # 仓库名
        name = m["name"]               # 物料名
        # setdefault：键不存在时先初始化 []，再 append
        result.setdefault(wh, []).append(name)
    return result


# ------------------------------------------------------------------
# 函数实现 2：进阶版（collections.defaultdict，更优雅）
# ------------------------------------------------------------------
from collections import defaultdict

def group_by_warehouse_v2(materials):
    """用 defaultdict 省去 setdefault 判断。"""
    result = defaultdict(list)
    for m in materials:
        result[m["warehouse"]].append(m["name"])
    return dict(result)               # 转回普通 dict，符合需求描述


# ------------------------------------------------------------------
# 函数实现 3：进阶版（字典推导式 + 借助 set 去重思路）
# 思路：先按仓库收集（保持顺序用 list），再一次性构建字典
# ------------------------------------------------------------------
def group_by_warehouse_v3(materials):
    """纯字典推导式实现（适合追求一行流，但可读性一般）。"""
    warehouses = {m["warehouse"] for m in materials}   # 所有仓库集合
    return {
        wh: [m["name"] for m in materials if m["warehouse"] == wh]
        for wh in warehouses
    }


# ------------------------------------------------------------------
# 函数实现 4：健壮版（处理缺字段、空列表、None）
# ------------------------------------------------------------------
def group_by_warehouse_safe(materials):
    """
    健壮版本：
    - 空列表 / None 输入 -> 返回 {}
    - 缺 name / warehouse 字段 -> 跳过该物料（不报错）
    - warehouse 为 None / 空串 -> 归入 "未分配仓库"
    """
    if not materials:
        return {}

    result = defaultdict(list)
    for m in materials:
        name = m.get("name")
        wh = m.get("warehouse") or "未分配仓库"
        if name is None:
            continue                       # 没名字的物料无法分组，跳过
        result[wh].append(name)
    return dict(result)


# ==================================================================
# 测试
# ==================================================================
if __name__ == "__main__":
    # ---- 测试数据 ----
    materials = [
        {"name": "MAT-001", "warehouse": "A仓"},
        {"name": "MAT-002", "warehouse": "A仓"},
        {"name": "MAT-003", "warehouse": "B仓"},
        {"name": "MAT-004", "warehouse": "B仓"},
        {"name": "MAT-005", "warehouse": "C仓"},
    ]

    expected = {
        "A仓": ["MAT-001", "MAT-002"],
        "B仓": ["MAT-003", "MAT-004"],
        "C仓": ["MAT-005"],
    }

    # ---- 运行各版本 ----
    print("=== 基础版（setdefault）===")
    r1 = group_by_warehouse(materials)
    print(r1)

    print("\n=== defaultdict 版 ===")
    r2 = group_by_warehouse_v2(materials)
    print(r2)

    print("\n=== 字典推导式版 ===")
    r3 = group_by_warehouse_v3(materials)
    print(r3)

    # ---- 健壮版测试（脏数据）----
    print("\n=== 健壮版（含异常数据）===")
    dirty = [
        {"name": "MAT-101", "warehouse": "A仓"},
        {"warehouse": "B仓"},                     # 缺 name -> 跳过
        {"name": "MAT-102", "warehouse": None},  # warehouse=None -> 未分配仓库
        {"name": "MAT-103"},                     # 缺 warehouse -> 未分配仓库
        {},                                       # 空字典 -> 跳过
    ]
    r4 = group_by_warehouse_safe(dirty)
    print(r4)

    print("\n=== 空列表测试 ===")
    print("空列表结果：", group_by_warehouse_safe([]))

    # ---- 断言验证 ----
    print("\n=== 断言验证 ===")
    assert group_by_warehouse(materials) == expected, "基础版结果不对！"
    assert group_by_warehouse_v2(materials) == expected, "defaultdict 版结果不对！"
    assert group_by_warehouse_v3(materials) == expected, "推导式版结果不对！"
    assert group_by_warehouse_safe([]) == {}, "空列表应返回空字典！"
    assert group_by_warehouse_safe(dirty) == {
        "A仓": ["MAT-101"],
        "未分配仓库": ["MAT-102", "MAT-103"],
    }, "健壮版分组结果不对！"
    print("✓ 所有断言通过！")
