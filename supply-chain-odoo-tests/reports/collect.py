"""报告加载：把各 JSON 产物读成统一 dict。

所有读取均为「尽力而为」——缺失文件返回 None/[]，不抛错，保证聚合永不因
单个报告缺失而崩。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # supply-chain-odoo-tests

EVAL_REPORT = ROOT / "eval" / "eval_report.json"
PROD_REPORT = ROOT / "prodmon" / "prod_report.json"
PROD_ALERT = ROOT / "prodmon" / "prod_alert.json"
BADCASES = ROOT / "prodmon" / "bad_cases.jsonl"
FENCE_DIFF = ROOT / "fence" / "captures" / "diff_report.json"
FENCE_VERDICT = ROOT / "fence" / "captures" / "verdict_report.json"

HISTORY = HERE / "metrics_history.jsonl"
DASHBOARD = HERE / "dashboard.html"
SUMMARY = HERE / "summary.md"


def _read_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _read_jsonl(path: Path) -> list:
    out = []
    try:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return out
    return out


def load_all() -> dict:
    """返回 {eval_report, prod_report, alert, bad_cases, bad_cases_count,
    fence_diff, fence_verdict}。"""
    alert = _read_json(PROD_ALERT) or {}
    bad_cases = _read_jsonl(BADCASES)
    return {
        "eval_report": _read_json(EVAL_REPORT),
        "prod_report": _read_json(PROD_REPORT),
        "alert": alert,
        "alerts": alert.get("alerts") or [],
        "alert_level": alert.get("level", "ok"),
        "bad_cases": bad_cases,
        "bad_cases_count": len(bad_cases),
        # 支柱一 · 行为围栏（缺失返回 None，仪表盘显示「未运行」）
        "fence_diff": _read_json(FENCE_DIFF),
        "fence_verdict": _read_json(FENCE_VERDICT),
    }
