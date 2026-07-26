"""PRD 来源生成器：把 prd_rules.py（提炼自验收清单/作品说明）转为业务数值断言用例。

生成器的职责是『翻译』PRD 规则为可执行 Case，绝不读取 SUT 代码反推期望
（红线见 prd_rules.py / 技术方案 v2.1 P0#3）。
"""
from __future__ import annotations

from typing import List

from .metagen import BusinessCase
from .prd_rules import PRD_RULES


def business_cases() -> List[BusinessCase]:
    out: List[BusinessCase] = []
    for r in PRD_RULES:
        out.append(BusinessCase(
            r["id"], r["desc"], "business", r["model"],
            r["mode"], r["expect_state"], r.get("expect_field", ""),
        ))
    return out
