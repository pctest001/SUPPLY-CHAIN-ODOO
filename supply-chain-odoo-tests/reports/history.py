"""指标历史累积（供趋势图）。

每条记录：{source, timestamp, quality_score, accuracy, hallucination_rate,
refusal_accuracy, safety_violation_rate, prod_accuracy}
按 (source, timestamp) 去重——同一份报告重复 build 不会重复计入。
"""
from __future__ import annotations

import json
from pathlib import Path


def append_run(source: str, timestamp: str, metrics: dict, history_path: Path) -> None:
    """累积一条指标记录；按 (source, timestamp) 去重。"""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                existing.add((r.get("source"), r.get("timestamp")))
            except Exception:
                continue
    key = (source, timestamp)
    if key in existing:
        return  # 已记录，去重
    rec = {
        "source": source,
        "timestamp": timestamp,
        "quality_score": metrics.get("quality_score"),
        "accuracy": metrics.get("accuracy"),
        "hallucination_rate": metrics.get("hallucination_rate"),
        "refusal_accuracy": metrics.get("refusal_accuracy"),
        "safety_violation_rate": metrics.get("safety_violation_rate"),
        "prod_accuracy": metrics.get("prod_accuracy"),
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_history(history_path: Path) -> list:
    out = []
    if not history_path.exists():
        return out
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def series(history: list, source: str, field: str) -> list:
    """取出某 source 的某指标时间序列（按 timestamp 升序），每项 (ts, value)。"""
    pts = [(r.get("timestamp"), r.get(field)) for r in history
           if r.get("source") == source and r.get(field) is not None]
    pts.sort(key=lambda x: x[0] or "")
    return pts
