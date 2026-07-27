"""QA 报告聚合（L4 评测 + L6 监控）的 pytest 门禁 —— 离线可跑。

验证：collect 尽力而为加载、history 去重与序列、HTML 仪表盘含关键标记、
Markdown 汇总含各章节。不依赖真实评测/监控产物。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # supply-chain-odoo-tests
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from reports.collect import load_all  # noqa: E402
from reports.history import append_run, load_history, series  # noqa: E402
from reports.render_html import build_dashboard_html  # noqa: E402
from reports.render_markdown import build_markdown  # noqa: E402


# 与 load_all() 返回结构一致的合成数据（无需真实产物）
FAKE_DATA = {
    "eval_report": {
        "metrics": {"total": 15, "accuracy": 100.0, "hallucination_rate": 0.0,
                    "refusal_accuracy": 100.0, "safety_violation_rate": 0.0,
                    "quality_score": 100.0, "passed": 15},
        "regression": False, "baseline_diff": {},
        "timestamp": "2026-07-27T05:12:19+00:00",
    },
    "prod_report": {
        "metrics": {"total": 5, "safety_violation_rate": 0.0,
                    "refusal_accuracy": 100.0, "hallucination_rate": 0.0,
                    "prod_accuracy": 100.0},
        "degraded": False,
        "version_distribution": {"total_sampled": 5, "distribution": [
            {"prompt_version": "v2", "model_used": "deepseek-chat", "count": 65}]},
        "timestamp": "2026-07-27T05:13:00+00:00",
    },
    "alert": {"level": "ok", "alerts": [], "summary": "x"},
    "alerts": [], "alert_level": "ok", "bad_cases": [], "bad_cases_count": 0,
}


def test_collect_missing_files_is_safe(tmp_path, monkeypatch):
    """在空目录下 load_all 不抛错，返回 None/[] 占位。"""
    monkeypatch.setattr("reports.collect.ROOT", tmp_path)
    monkeypatch.setattr("reports.collect.EVAL_REPORT", tmp_path / "eval_report.json")
    monkeypatch.setattr("reports.collect.PROD_REPORT", tmp_path / "prod_report.json")
    monkeypatch.setattr("reports.collect.PROD_ALERT", tmp_path / "prod_alert.json")
    monkeypatch.setattr("reports.collect.BADCASES", tmp_path / "bad_cases.jsonl")
    d = load_all()
    assert d["eval_report"] is None
    assert d["prod_report"] is None
    assert d["bad_cases"] == []
    assert d["bad_cases_count"] == 0


def test_history_dedup(tmp_path):
    hist = tmp_path / "h.jsonl"
    m = {"quality_score": 100, "accuracy": 100}
    append_run("eval", "T1", m, hist)
    append_run("eval", "T1", m, hist)  # 同 source+timestamp → 去重
    append_run("eval", "T2", m, hist)  # 不同 → 计入
    rows = load_history(hist)
    assert len(rows) == 2
    assert all(r["source"] == "eval" for r in rows)


def test_history_series_sorted(tmp_path):
    hist = tmp_path / "h.jsonl"
    append_run("prod", "2026-07-27T01:00:00", {"prod_accuracy": 90}, hist)
    append_run("prod", "2026-07-27T03:00:00", {"prod_accuracy": 95}, hist)
    append_run("prod", "2026-07-27T02:00:00", {"prod_accuracy": 80}, hist)
    s = series(load_history(hist), "prod", "prod_accuracy")
    assert [v for _, v in s] == [90, 80, 95]  # 按 timestamp 升序


def test_render_html_contains_markers():
    html = build_dashboard_html(FAKE_DATA, history=[])
    assert "QA 报告仪表盘" in html
    assert "L4 · AI 评测" in html
    assert "L6 · 生产监控" in html
    assert "<svg" in html  # 趋势图（即使无数据也有占位 svg）
    assert "100.0%" in html or "100%" in html  # 指标卡


def test_render_html_handles_missing_data():
    """无评测/监控数据时也不崩，给出占位提示。"""
    html = build_dashboard_html({"alerts": [], "alert_level": "ok",
                                  "bad_cases": [], "bad_cases_count": 0}, history=[])
    assert "QA 报告仪表盘" in html


def test_render_markdown_sections():
    md = build_markdown(FAKE_DATA, history=[])
    assert "## L4 · AI 评测" in md
    assert "## L6 · 生产监控" in md
    assert "## 告警与 Bad Case" in md
    assert "## 闭环建议" in md
    assert "100.0%" in md


def test_render_markdown_recommendations_on_regression():
    bad = dict(FAKE_DATA)
    bad["prod_report"] = dict(bad["prod_report"])
    bad["prod_report"]["metrics"] = dict(bad["prod_report"]["metrics"])
    bad["prod_report"]["metrics"]["safety_violation_rate"] = 12.0
    bad["prod_report"]["degraded"] = True
    md = build_markdown(bad, history=[])
    assert "安全违规" in md  # 自动建议命中


if __name__ == "__main__":
    # 直跑只覆盖不依赖 pytest fixture 的用例；tmp_path/monkeypatch 相关用例由 pytest 跑。
    test_render_html_contains_markers()
    test_render_html_handles_missing_data()
    test_render_markdown_sections()
    test_render_markdown_recommendations_on_regression()
    print("\n[PASS] test_reports 核心用例通过（离线）")
