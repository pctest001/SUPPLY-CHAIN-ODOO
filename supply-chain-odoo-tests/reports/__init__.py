"""QA 报告聚合（L4 评测 + L6 监控 统一呈现）。

把分散的 JSON 报告（eval/eval_report.json、prodmon/prod_report.json、
prodmon/prod_alert.json、prodmon/bad_cases.jsonl）聚合为两种人/机可读形态：
  - 自包含 HTML 仪表盘 reports/dashboard.html（内联 CSS + 内联 SVG 趋势图，离线可看）
  - Markdown 汇总 reports/summary.md（给人读的周/日报，CI 可写入 $GITHUB_STEP_SUMMARY）
指标历史累积到 reports/metrics_history.jsonl 供趋势图（按 source+timestamp 去重）。
"""
from __future__ import annotations

from .collect import load_all, ROOT, HERE, HISTORY, DASHBOARD, SUMMARY
from .history import append_run, load_history
from .render_html import build_dashboard_html
from .render_markdown import build_markdown

__all__ = [
    "load_all", "append_run", "load_history",
    "build_dashboard_html", "build_markdown",
    "ROOT", "HERE", "HISTORY", "DASHBOARD", "SUMMARY",
]
