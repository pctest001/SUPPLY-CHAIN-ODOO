"""缺陷闭环层离线测试 —— pytest 不可用，直接 `python tests/test_defects.py` 自验。

覆盖：schema 状态机 / registry 追加·去重·查询·转移 / sink 本地汇总 / emit 两条来源。
每个测试用独立临时 store，避免串扰。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from defects.schema import (
    Defect, make_signature, flag_to_category, flag_to_severity,
    can_transition, STATUS_OPEN, STATUS_TRIAGE, STATUS_FIXING,
    STATUS_VERIFYING, STATUS_CLOSED,
)
from defects.registry import DefectRegistry
from defects.sink import LocalSink
from defects.emit import emit_from_sessions, emit_from_ci

_TMP = Path(tempfile.mkdtemp(prefix="defects_test_"))
_cnt = 0


def _mk_reg():
    global _cnt
    _cnt += 1
    return DefectRegistry(path=_TMP / f"defects_{_cnt}.jsonl")


def _mk_sink(reg):
    return LocalSink(reg, summary_path=_TMP / f"summary_{_cnt}.md")


def test_state_machine():
    assert can_transition(STATUS_OPEN, STATUS_TRIAGE)
    assert can_transition(STATUS_TRIAGE, STATUS_FIXING)
    assert can_transition(STATUS_FIXING, STATUS_VERIFYING)
    assert can_transition(STATUS_VERIFYING, STATUS_CLOSED)
    assert can_transition(STATUS_CLOSED, STATUS_OPEN)  # reopen
    assert can_transition(STATUS_OPEN, STATUS_CLOSED)
    assert not can_transition(STATUS_OPEN, STATUS_VERIFYING)  # 不允许跳级
    print("[ok] test_state_machine")


def test_flag_mapping():
    assert flag_to_category(["safety_violation"]) == "safety"
    assert flag_to_category(["hallucination"]) == "hallucination"
    assert flag_to_severity(["safety_violation"]) == "critical"
    assert flag_to_severity(["missed_refusal"]) == "high"
    print("[ok] test_flag_mapping")


def test_registry_add_and_dedupe():
    reg = _mk_reg()
    reg.add(Defect(source="ci_gate", signature=make_signature("ci_gate", "M5"),
                   title="bug A", severity="high", category="mutation"))
    # 同 signature → 合并
    d2, new2 = reg.add(Defect(source="ci_gate", signature=make_signature("ci_gate", "M5"),
                               title="bug A", severity="high", category="mutation"))
    assert new2 is False and d2.id == "DEF-001" and d2.occurrences == 2
    # 不同 signature → 新单
    d3, new3 = reg.add(Defect(source="ci_gate", signature=make_signature("ci_gate", "M6"),
                               title="bug B", severity="medium", category="mutation"))
    assert new3 is True and d3.id == "DEF-002"
    assert len(reg.all()) == 2
    print("[ok] test_registry_add_and_dedupe")


def test_registry_transition():
    reg = _mk_reg()
    d, _ = reg.add(Defect(source="ci_gate", signature=make_signature("ci_gate", "X1"),
                          title="t", severity="high", category="other"))
    try:
        reg.transition(d.id, STATUS_VERIFYING)
        raise AssertionError("应拒绝 Open->Verifying")
    except ValueError:
        pass
    reg.transition(d.id, STATUS_FIXING, owner="alice")
    assert reg.get(d.id).status == STATUS_FIXING and reg.get(d.id).owner == "alice"
    reg.transition(d.id, STATUS_VERIFYING, fix_ref="abc123")
    reg.transition(d.id, STATUS_CLOSED, verified_by="用例 po_x 通过")
    assert reg.get(d.id).verified_by == "用例 po_x 通过"
    try:
        reg.transition("DEF-999", STATUS_FIXING)
        raise AssertionError("应拒绝未知 id")
    except KeyError:
        pass
    print("[ok] test_registry_transition")


def test_sink_local_summary():
    reg = _mk_reg()
    reg.add(Defect(source="prod_monitor", signature=make_signature("prod_monitor", "s1|hallucination"),
                   title="[幻觉] 会话1", severity="high", category="hallucination",
                   evidence={"session_id": "s1"}))
    sink = _mk_sink(reg)
    sink.emit(reg.get("DEF-001"), True)
    assert sink.summary_path.exists()
    md = sink.summary_path.read_text(encoding="utf-8")
    assert "DEF-001" in md and "幻觉" in md
    print("[ok] test_sink_local_summary")


def test_emit_from_sessions():
    class S:
        def __init__(self, i, q):
            self.id = i; self.question = q
            self.prompt_version = "v3"; self.model_used = "deepseek-chat"
    class R:
        def __init__(self, flags):
            self.flags = flags; self.reasons = []; self.clean = not flags

    sessions = [S("sA", "负库存多少？"), S("sB", "正常查询")]
    results = [R(["hallucination"]), R([])]
    reg = _mk_reg()
    sink = _mk_sink(reg)
    created, updated = emit_from_sessions(sessions, results, registry=reg, sink=sink)
    assert created == 1 and updated == 0
    ds = [x for x in reg.all() if x.category == "hallucination"]
    assert len(ds) == 1 and ds[0].severity == "high"
    assert ds[0].evidence["session_id"] == "sA"
    print("[ok] test_emit_from_sessions")


def test_emit_from_ci_dedupe():
    reg = _mk_reg()
    sink = _mk_sink(reg)
    d1, n1 = emit_from_ci("mutation", "M5", "查过期批次用了不存在字段",
                           severity="high", category="mutation",
                           evidence={"mutation_point": "M5"}, registry=reg, sink=sink)
    assert n1 is True and d1.id == "DEF-001"
    d2, n2 = emit_from_ci("mutation", "M5", "查过期批次用了不存在字段",
                           registry=reg, sink=sink)
    assert n2 is False and d2.occurrences == 2
    print("[ok] test_emit_from_ci_dedupe")


def _run():
    test_state_machine()
    test_flag_mapping()
    test_registry_add_and_dedupe()
    test_registry_transition()
    test_sink_local_summary()
    test_emit_from_sessions()
    test_emit_from_ci_dedupe()
    print("\n[PASS] test_defects 全部通过（离线）")


if __name__ == "__main__":
    _run()
