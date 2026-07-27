"""报告聚合 CLI。

用法（在 supply-chain-odoo-tests 目录下）：
  python -m reports.build            # 生成 dashboard.html + summary.md，并累积指标历史
  python -m reports.build --ci       # 同上，并把 Markdown 汇总打印到 stdout（供 CI 写入 $GITHUB_STEP_SUMMARY）

前置：先跑 python -m eval.run_eval --mode sim 与 python -m prodmon.run_monitor --mode sim
（二者产出 eval_report.json / prod_report.json / prod_alert.json / bad_cases.jsonl）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .collect import load_all, HISTORY, DASHBOARD, SUMMARY
from .history import append_run, load_history
from .render_html import build_dashboard_html
from .render_markdown import build_markdown


def main():
    ap = argparse.ArgumentParser(description="QA 报告聚合（L4+L6 统一呈现）")
    ap.add_argument("--ci", action="store_true",
                    help="把 Markdown 汇总打印到 stdout（供 CI 写入 $GITHUB_STEP_SUMMARY）")
    args = ap.parse_args()

    data = load_all()
    history = load_history(HISTORY)

    # 累积指标历史（按 source+timestamp 去重）
    er = data.get("eval_report") or {}
    if er.get("metrics") and er.get("timestamp"):
        append_run("eval", er["timestamp"], er["metrics"], HISTORY)
    pr = data.get("prod_report") or {}
    if pr.get("metrics") and pr.get("timestamp"):
        append_run("prod", pr["timestamp"], pr["metrics"], HISTORY)
    history = load_history(HISTORY)  # 重新载入含本次

    html = build_dashboard_html(data, history)
    DASHBOARD.write_text(html, encoding="utf-8")
    md = build_markdown(data, history)
    SUMMARY.write_text(md, encoding="utf-8")

    print(f"[reports] dashboard -> {DASHBOARD}", file=sys.stderr)
    print(f"[reports] summary   -> {SUMMARY}", file=sys.stderr)

    if args.ci:
        # 供 CI 聚合：直接落到 step summary
        print(md)


if __name__ == "__main__":
    main()
