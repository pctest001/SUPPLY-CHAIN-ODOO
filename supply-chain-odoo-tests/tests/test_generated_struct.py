"""M2 端到端验证：由 generator 生成的结构型断言用例，经 healer 准备好的环境执行。

这些用例是『结构型断言』：期望 SUT 拒绝非法输入/非法状态转换。
- 若按预期被拒绝 → 用例通过；
- 若未被拒绝 → 说明守卫缺失，用例失败（真实缺陷信号，绝不自愈掩盖）。
"""
import xmlrpc.client

import pytest

from src.generator.metagen import all_cases
from src.healer.audit import get_audit

CASES = all_cases()


@pytest.mark.parametrize("case", CASES, ids=[c.cid for c in CASES])
def test_generated_struct(case, odoo_client, healed_env):
    audit = get_audit()
    passed, detail = case.run(odoo_client, healed_env)
    audit.log("data", "info", f"case:{case.cid}", detail)
    # 结构型断言：期望被拦截（passed=True）。未被拦截 = 真实守卫缺失。
    assert passed, detail
