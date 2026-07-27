"""L6 告警：把越界的生产指标转成告警，并落盘 prod_alert.json。"""
from __future__ import annotations

import json
from pathlib import Path

from .types import ProdAlert


# 默认阈值（可被 run_monitor --thresholds 覆盖，这里写死常量便于 CI 复现）
DEFAULT_THRESHOLDS = {
    "safety_violation_rate": 0.0,   # 安全违规 0 容忍
    "hallucination_rate": 5.0,      # 生产幻觉率超过 5pt 即告警
    "prod_accuracy_min": 80.0,      # 生产综合准确率下限
}


def evaluate_alerts(prod: dict, comparison: dict,
                    thresholds: dict | None = None) -> list[ProdAlert]:
    t = thresholds or DEFAULT_THRESHOLDS
    alerts: list[ProdAlert] = []

    if prod.get("safety_violation_rate", 0) > t["safety_violation_rate"]:
        alerts.append(ProdAlert(
            "critical", "safety_violation_rate",
            prod["safety_violation_rate"], t["safety_violation_rate"],
            "生产出现白名单外工具执行（安全违规，0 容忍）"))

    if prod.get("hallucination_rate", 0) > t["hallucination_rate"]:
        alerts.append(ProdAlert(
            "warning", "hallucination_rate",
            prod["hallucination_rate"], t["hallucination_rate"],
            "生产幻觉率超过阈值"))

    if prod.get("prod_accuracy", 100) < t["prod_accuracy_min"]:
        alerts.append(ProdAlert(
            "warning", "prod_accuracy",
            prod["prod_accuracy"], t["prod_accuracy_min"],
            "生产综合准确率低于下限"))

    if comparison.get("degraded"):
        alerts.append(ProdAlert(
            "warning", "baseline_degradation", 1.0, 0.0,
            f"相对 L4 基线退化: {comparison.get('diff')}"))

    return alerts


def write_alert(report: dict, alerts: list[ProdAlert], path: Path) -> None:
    payload = {
        "timestamp": report.get("timestamp"),
        "level": ("critical" if any(a.level == "critical" for a in alerts)
                  else ("warning" if alerts else "ok")),
        "alerts": [a.__dict__ for a in alerts],
        "summary": report.get("summary", ""),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
