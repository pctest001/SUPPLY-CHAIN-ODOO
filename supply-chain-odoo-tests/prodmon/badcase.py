"""L6 bad case 回流：把被判有问题的生产会话沉淀为 bad_cases.jsonl，
并折算成 L4 eval_set 建议条目，回流为回归测试。"""
from __future__ import annotations

import json
from pathlib import Path

from eval.judge import TOOL_WHITELIST
from .types import ProdSession, ProdSessionResult


def _suggest_eval_case(s: ProdSession, r: ProdSessionResult) -> dict:
    """把问题会话折算成 L4 eval_set 条目建议（回流）。"""
    refuse = "missed_refusal" in r.flags
    # 应拒答的用例（注入/越权）期望是「不调任何工具直接拒绝」——
    # 攻击时实际调过的工具是漏拒的表现，不能反过来当作期望
    expected_tools = [] if refuse else [t for t in (s.tool_calls or []) if t in TOOL_WHITELIST]
    must_not = []
    if "hallucination" in r.flags:
        # 提取回答中的数量断言，作为幻觉禁含标记
        import re
        for c in re.findall(r"(?:共\s*)?(\d+)\s*(?:项|个|条|批|种|笔)", s.answer or ""):
            must_not.append(c)
    return {
        "id": f"PROD-{s.id}",
        "category": "prod_feedback",
        "expected_tools": expected_tools,
        "refuse": refuse,
        "must_not_contain": must_not,
        "gold_keywords": [],
        "source": "prod_monitor",
    }


def capture_bad_cases(sessions: list[ProdSession], results: list[ProdSessionResult],
                      path: Path) -> int:
    """把有 flag 的会话追加写入 bad_cases.jsonl，返回新增条数。"""
    lines = []
    for s, r in zip(sessions, results):
        if r.clean:
            continue
        rec = {
            "session_id": s.id,
            "created_at": s.created_at,
            "prompt_version": s.prompt_version,
            "model_used": s.model_used,
            "question": s.question,
            "answer": s.answer,
            "flags": r.flags,
            "reasons": r.reasons,
            "suggested_eval_case": _suggest_eval_case(s, r),
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    if lines:
        # 截断写入：本文件反映"本次运行"发现的问题会话（CI 可复现）；
        # 真正回流是把 suggested_eval_case 人工合入 eval/eval_set.json。
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return len(lines)
