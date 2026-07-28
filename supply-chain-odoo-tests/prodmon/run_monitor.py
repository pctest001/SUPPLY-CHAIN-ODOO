"""L6 生产监控与治理 —— 运行器。

用法：
  # 离线验证监控链路（默认，无需 Odoo）
  python -m prodmon.run_monitor --mode sim

  # 驱动真实生产（需 Odoo 容器 + ai.config 已启用）
  python -m prodmon.run_monitor --mode live

  # CI 门禁：生产综合准确率低于阈值 / 安全违规 / 相对 L4 基线退化即失败退出
  python -m prodmon.run_monitor --mode sim --fail-under 80

产物（默认写 prodmon/ 下）：
  prod_report.json    本次指标 + 基线差异 + 告警 + 版本分布 + 摘要
  prod_alert.json     告警明细（level=ok/warning/critical）
  bad_cases.jsonl     被判有问题的会话（回流 L4 的种子）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .types import ProdSession
from .collector import MockCollector, RpcCollector
from .sampler import sample
from .judge_prod import ProductionJudge
from .metrics import compute_prod_metrics, compare_to_baseline
from .alerting import evaluate_alerts, write_alert, DEFAULT_THRESHOLDS
from .badcase import capture_bad_cases
from defects.emit import emit_from_sessions
from .versioning import analyze_versions
from .notify import dispatch as notify_dispatch

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURES = HERE / "prod_fixtures.json"
DEFAULT_REPORT = HERE / "prod_report.json"
DEFAULT_ALERT = HERE / "prod_alert.json"
DEFAULT_BADCASES = HERE / "bad_cases.jsonl"
DEFAULT_NOTIFY_LOG = HERE / "notify.log"
EVAL_BASELINE = HERE.parent / "eval" / "eval_baseline.json"


def _load_baseline() -> dict:
    if EVAL_BASELINE.exists():
        try:
            return json.loads(EVAL_BASELINE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"accuracy": 100, "hallucination_rate": 0,
            "safety_violation_rate": 0, "quality_score": 100,
            "refusal_accuracy": 100}


def _summarize(metrics: dict, alerts: list, n_bad: int, vrep: dict,
               n_defects_created: int = 0, n_defects_updated: int = 0) -> str:
    lines = ["=== L6 生产监控与治理 (prodmon) ===",
             f"采样会话数: {metrics['total']}",
             f"  安全违规率 : {metrics['safety_violation_rate']}%",
             f"  拒答准确率 : {metrics['refusal_accuracy']}%",
             f"  幻觉率     : {metrics['hallucination_rate']}%",
             f"  综合准确率 : {metrics['prod_accuracy']}%",
             f"  工具执行准确率 : {metrics.get('tool_exec_acc') if metrics.get('tool_exec_acc') is not None else 'N/A(无工具调用)'}",
             f"  版本分布   : {vrep['distribution']}"]
    if alerts:
        lines.append(f"[ALERT] {len(alerts)} 条告警")
        for a in alerts:
            lines.append(f"  - {a.level} {a.metric}: {a.detail}")
    else:
        lines.append("[OK] 无告警")
    if n_bad:
        lines.append(f"[BAD CASE] 回流 {n_bad} 条问题会话 → bad_cases.jsonl")
    if n_defects_created or n_defects_updated:
        lines.append(f"[DEFECT] 缺陷闭环：新建 {n_defects_created} / 合并 {n_defects_updated} "
                     f"→ defects/defects.jsonl")
    return "\n".join(lines)


def run(mode: str = "sim", fixtures_path: Path = DEFAULT_FIXTURES, fixtures: list | None = None,
        since_days: int = 7, sample_size: int = 0, strategy: str = "recent",
        fail_under: float = 80.0, thresholds: dict | None = None,
        notify: bool = False, webhook: str | None = None,
        at_mobiles: list | None = None, emit_defects: bool = False) -> int:
    """执行一次生产监控，返回退出码（0=通过，1=门禁失败）。

    fixtures: 直接传入会话列表（测试/退化场景用）；为 None 时从 fixtures_path 读取。
    """
    if mode == "live":
        from src.odoo_client import OdooClient
        cli = OdooClient(
            os.getenv("ODOO_URL", "http://localhost"),
            os.getenv("ODOO_DB", "test_supplychain"),
            os.getenv("ODOO_ADMIN_LOGIN", "admin@example.com"),
            os.getenv("ODOO_ADMIN_PASSWORD", "admin"),
            int(os.getenv("ODOO_PORT", "18069")),
        )
        cli.authenticate()
        collector = RpcCollector(cli, since_days=since_days)
    else:
        collector = MockCollector(fixtures=fixtures, fixtures_path=fixtures_path)

    sessions = collector.collect(since_days=since_days)
    if sample_size > 0:
        sessions = sample(sessions, sample_size, strategy=strategy)

    judge = ProductionJudge()
    results = [judge.judge(s) for s in sessions]
    metrics = compute_prod_metrics(results)
    baseline = _load_baseline()
    comparison = compare_to_baseline(metrics, baseline)
    alerts = evaluate_alerts(metrics, comparison, thresholds or DEFAULT_THRESHOLDS)
    n_bad = capture_bad_cases(sessions, results, DEFAULT_BADCASES)
    # 缺陷闭环层：把问题会话沉淀为 defect（live 自动开启；sim 需显式 --emit-defects）
    n_defects_created = n_defects_updated = 0
    if emit_defects or mode == "live":
        n_defects_created, n_defects_updated = emit_from_sessions(sessions, results)
    vrep = analyze_versions(sessions)

    # 门禁判定：致命告警 / 综合准确率不达标 / 相对 L4 基线退化 → 失败
    hard_fail = (any(a.level == "critical" for a in alerts)
                 or metrics["prod_accuracy"] < fail_under
                 or comparison["degraded"])

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "metrics": metrics,
        "baseline_diff": comparison["diff"],
        "degraded": comparison["degraded"],
        "alerts": [a.__dict__ for a in alerts],
        "bad_cases_captured": n_bad,
        "version_distribution": vrep,
        "summary": _summarize(metrics, alerts, n_bad, vrep,
                              n_defects_created, n_defects_updated),
    }
    DEFAULT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_alert(report, alerts, DEFAULT_ALERT)
    print(report["summary"])

    # L6 闭环出口：有告警时推送 IM/值班渠道（webhook 由 --webhook 或
    # PROD_ALERT_WEBHOOK 提供；否则 dry-run 落盘 notify.log 审计）。
    if alerts:
        notify_dispatch(report, webhook=webhook, at_mobiles=at_mobiles,
                        dry_run=not (notify or os.getenv("PROD_ALERT_WEBHOOK")))

    if hard_fail:
        print(f"\n[FAIL] prod_accuracy {metrics['prod_accuracy']} < {fail_under} "
              f"或存在致命告警/退化")
        return 1
    print(f"\n[PASS] prod_accuracy {metrics['prod_accuracy']} >= {fail_under}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="L6 生产监控与治理")
    ap.add_argument("--mode", choices=["sim", "live"], default="sim")
    ap.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--strategy", default="recent",
                    choices=["recent", "random", "stratified"])
    ap.add_argument("--fail-under", type=float, default=80.0,
                    help="生产综合准确率低于此值则退出码 1（CI 门禁）")
    ap.add_argument("--notify", action="store_true",
                    help="有告警时推送 IM/值班渠道（需配 PROD_ALERT_WEBHOOK 或 --webhook；否则 dry-run 落盘 notify.log）")
    ap.add_argument("--webhook", type=str, default=None,
                    help="告警 webhook 地址（钉钉/企微/Slack 兼容）；缺省读 env PROD_ALERT_WEBHOOK")
    ap.add_argument("--at-mobiles", dest="at_mobiles", type=str, default=None,
                    help="逗号分隔手机号，告警时 @；缺省取 env PROD_ALERT_AT_MOBILES 或内置默认 18658159309")
    ap.add_argument("--emit-defects", action="store_true",
                    help="把问题会话沉淀为缺陷记录(defects/defects.jsonl)。live 模式默认开启；"
                         "sim 需显式指定以免 CI 噪声")
    args = ap.parse_args()
    # 注意：run() 的形参顺序为 (mode, fixtures_path, fixtures, since_days, ...)，
    # 必须用关键字传参，避免 since_days(整数) 误入 fixtures 位导致 self._data 变 int。
    sys.exit(run(mode=args.mode, fixtures_path=args.fixtures,
                 since_days=args.since_days, sample_size=args.sample,
                 strategy=args.strategy, fail_under=args.fail_under,
                 notify=args.notify, webhook=args.webhook,
                 at_mobiles=(args.at_mobiles.split(",") if args.at_mobiles else None),
                 emit_defects=args.emit_defects))


if __name__ == "__main__":
    main()
