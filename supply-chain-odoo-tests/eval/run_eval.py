"""AI 评测运行器 (L4)。

用法：
  # 离线验证评测链路（默认，无需 Odoo）
  python -m eval.run_eval --mode sim

  # 驱动真实 SUT（需 Odoo 容器 + ai.config 已启用）
  python -m eval.run_eval --mode live

  # CI 门禁：quality_score 低于阈值即失败退出
  python -m eval.run_eval --mode sim --fail-under 80

产物：
  eval_report.json   本次明细 + 指标 + 与基线差异
  eval_baseline.json 当前指标（作为下次回归基线）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .judge import RuleJudge, MockLLMJudge, compute_metrics, summarize
from .engine import MockAIEngine

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "eval_set.json"
DEFAULT_REPORT = HERE / "eval_report.json"
DEFAULT_BASELINE = HERE / "eval_baseline.json"


def _load_cases(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["cases"]


def _run(mode: str, cases: list, judge):
    if mode == "live":
        from engine import LiveAIClient
        from src.odoo_client import OdooClient
        import os
        cli = OdooClient(
            os.getenv("ODOO_URL", "http://localhost"),
            os.getenv("ODOO_DB", "test_supplychain"),
            os.getenv("ODOO_ADMIN_LOGIN", "admin@example.com"),
            os.getenv("ODOO_ADMIN_PASSWORD", "admin"),
            int(os.getenv("ODOO_PORT", "18069")),
        )
        cli.authenticate()
        engine = LiveAIClient(cli)
    else:
        engine = MockAIEngine()

    rule = RuleJudge()
    results = []
    for case in cases:
        trace = engine.run(case)
        r = rule.judge(case, trace)
        if judge is not None:
            score, reason = judge.grade(case, trace)
            r.reasons.append(f"[LLMJudge={score:.2f}] {reason}")
        results.append(r)
    return results


def _load_baseline(path: Path) -> dict | None:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def main():
    ap = argparse.ArgumentParser(description="AI 评测运行器 (L4)")
    ap.add_argument("--mode", choices=["sim", "live"], default="sim")
    ap.add_argument("--eval-set", type=Path, default=DEFAULT_SET)
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--fail-under", type=float, default=80.0,
                    help="quality_score 低于此值则退出码 1（CI 门禁）")
    ap.add_argument("--judge", choices=["rule", "mock", "remote"], default="rule")
    args = ap.parse_args()

    cases = _load_cases(args.eval_set)
    judge = None
    judge_name = "RuleJudge"
    if args.judge == "mock":
        judge = MockLLMJudge()
        judge_name = "MockLLMJudge"
    elif args.judge == "remote":
        from judge import RemoteLLMJudge
        judge = RemoteLLMJudge()
        judge_name = "RemoteLLMJudge"

    results = _run(args.mode, cases, judge)
    metrics = compute_metrics(results)
    print(summarize(results, metrics, judge_name))

    # ---- 回归基线对比 ----
    baseline = _load_baseline(args.baseline)
    regression = False
    diff = {}
    if baseline:
        for k in ["accuracy", "hallucination_rate", "refusal_accuracy",
                  "safety_violation_rate", "quality_score"]:
            b = baseline.get(k)
            if b is None:
                continue
            d = round(metrics[k] - b, 1)
            diff[k] = d
            if k == "quality_score" and d < 0:
                regression = True
            if k == "hallucination_rate" and d > 0:
                regression = True
            if k == "safety_violation_rate" and d > 0:
                regression = True
        if regression:
            print(f"\n[REGRESSION] 较基线退化: {diff}")
        else:
            print(f"\n[BASELINE OK] 与基线对比: {diff}")

    # ---- 写产物 ----
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "judge": judge_name,
        "metrics": metrics,
        "baseline_diff": diff,
        "regression": regression,
        "per_case": [
            {"id": r.case_id, "category": r.category, "passed": r.passed,
             "reasons": r.reasons} for r in results
        ],
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.baseline.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出: {args.report.name} / {args.baseline.name}")

    # ---- 门禁判定 ----
    if metrics["quality_score"] < args.fail_under:
        print(f"\n[FAIL] quality_score {metrics['quality_score']} < {args.fail_under}")
        sys.exit(1)
    if regression:
        sys.exit(1)
    print(f"\n[PASS] quality_score {metrics['quality_score']} >= {args.fail_under}")
    sys.exit(0)


if __name__ == "__main__":
    main()
