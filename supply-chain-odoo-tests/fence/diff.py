"""差分引擎：归一化后对比 base / head 两份 capture，产出 diff_report.json。

用法：
  python -m fence.diff fence/captures/base_X.json fence/captures/head_Y.json
  python -m fence.diff A.json B.json --out fence/captures/diff_report.json

判定语义（P1 阶段，未接 intents）：
  - 有 diff -> exit 1（回归嫌疑，全部差异原样列出）
  - 零 diff -> exit 0
P2 的 verdict.py 会在本模块之上扣除 intents.yml 声明的预期变更。

浮点比较容差 1e-6（金额/数量的存储精度噪声）。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fence.normalize import normalize_capture

_EPS = 1e-6


def _neq(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) > _EPS
    return a != b


def deep_diff(a, b, path: str = "") -> list[dict]:
    """递归对比，返回 [{path, base, head}]。类型不同/值不同均记差异。"""
    if isinstance(a, dict) and isinstance(b, dict):
        diffs = []
        for k in sorted(set(a) | set(b)):
            p = f"{path}.{k}" if path else k
            if k not in a:
                diffs.append({"path": p, "base": "«缺失»", "head": b[k]})
            elif k not in b:
                diffs.append({"path": p, "base": a[k], "head": "«缺失»"})
            else:
                diffs.extend(deep_diff(a[k], b[k], p))
        return diffs
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [{"path": f"{path}#len", "base": len(a), "head": len(b),
                     "base_value": a, "head_value": b}]
        diffs = []
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(deep_diff(x, y, f"{path}[{i}]"))
        return diffs
    if _neq(a, b):
        return [{"path": path, "base": a, "head": b}]
    return []


def diff_captures(base_file: str | Path, head_file: str | Path) -> dict:
    base_raw = json.loads(Path(base_file).read_text(encoding="utf-8"))
    head_raw = json.loads(Path(head_file).read_text(encoding="utf-8"))
    base = normalize_capture(base_raw)
    head = normalize_capture(head_raw)

    scenarios, total_diffs = [], 0
    for sid in sorted(set(base) | set(head)):
        if sid not in base:
            scenarios.append({"scenario": sid, "req": head[sid]["req"],
                              "verdict": "head_only", "diffs": []})
            total_diffs += 1
            continue
        if sid not in head:
            scenarios.append({"scenario": sid, "req": base[sid]["req"],
                              "verdict": "base_only", "diffs": []})
            total_diffs += 1
            continue
        diffs = deep_diff(
            {"status": base[sid]["status"], "error": base[sid]["error"],
             "observations": base[sid]["observations"]},
            {"status": head[sid]["status"], "error": head[sid]["error"],
             "observations": head[sid]["observations"]},
        )
        total_diffs += len(diffs)
        scenarios.append({
            "scenario": sid,
            "req": head[sid]["req"] or base[sid]["req"],
            "verdict": "same" if not diffs else "diff",
            "diffs": diffs,
        })

    return {
        "base_file": str(base_file),
        "head_file": str(head_file),
        "base_meta": {k: base_raw.get(k) for k in ("target", "port", "run_id", "generated_at")},
        "head_meta": {k: head_raw.get(k) for k in ("target", "port", "run_id", "generated_at")},
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenario_total": len(scenarios),
        "scenario_diff": sum(1 for s in scenarios if s["verdict"] != "same"),
        "diff_total": total_diffs,
        "scenarios": scenarios,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="行为围栏差分引擎")
    ap.add_argument("base_file")
    ap.add_argument("head_file")
    ap.add_argument("--out", default=None, help="diff_report.json 输出路径")
    args = ap.parse_args()

    report = diff_captures(args.base_file, args.head_file)
    out = Path(args.out) if args.out else \
        Path(__file__).resolve().parent / "captures" / "diff_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fence.diff] base={report['base_meta']['target']}:{report['base_meta']['run_id']} "
          f"head={report['head_meta']['target']}:{report['head_meta']['run_id']}")
    for s in report["scenarios"]:
        if s["verdict"] == "same":
            continue
        print(f"  [DIFF] {s['scenario']} ({s['verdict']}, {len(s['diffs'])} 处)")
        for d in s["diffs"][:5]:
            print(f"     {d['path']}: base={json.dumps(d['base'], ensure_ascii=False)[:120]} "
                  f"| head={json.dumps(d['head'], ensure_ascii=False)[:120]}")
        if len(s["diffs"]) > 5:
            print(f"     ... 其余 {len(s['diffs']) - 5} 处见报告")
    print(f"[fence.diff] {report['scenario_diff']}/{report['scenario_total']} 场景有差异，"
          f"共 {report['diff_total']} 处 -> {out}")
    return 1 if report["diff_total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
