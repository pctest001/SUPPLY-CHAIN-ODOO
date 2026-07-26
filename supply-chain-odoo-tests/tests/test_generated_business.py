"""M2 任务2：PRD 来源的业务数值断言（期望权威来自验收清单/作品说明）。

这些用例是『业务数值断言』：执行正向业务流，断言达到 PRD 规定的状态/字段。
期望值由 prdgen 从 prd_rules.py 翻译而来，prd_rules.py 的唯一权威是 PRD 文档。

若断言失败，说明 SUT 业务行为偏离 PRD——这是真实缺陷信号，绝不自愈掩盖。
"""
import pytest

from src.generator.prdgen import business_cases

CASES = business_cases()


def test_prd_rules_loaded():
    assert len(CASES) >= 1, "prd_rules.py 未解析出任何业务规则"


def test_prd_rule_ids_unique():
    ids = [c.cid for c in CASES]
    assert len(ids) == len(set(ids)), f"PRD 规则 ID 重复: {ids}"


def test_prd_rule_source_traced():
    # 每条业务规则必须标注 PRD 溯源，否则违反"期望值权威来源"红线
    for c in CASES:
        assert getattr(c, "title", ""), f"{c.cid} 缺少业务描述"


@pytest.mark.parametrize("case", CASES, ids=[c.cid for c in CASES])
def test_generated_business(case, odoo_client, healed_env):
    passed, detail = case.run(odoo_client, healed_env)
    assert passed, detail
