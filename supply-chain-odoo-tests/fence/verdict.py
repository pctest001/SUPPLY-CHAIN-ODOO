"""裁决器：diff_report − intents = 回归嫌疑（支柱一 P2）。

用法：
  python -m fence.verdict fence/captures/diff_report.json [--intents fence/intents.yml]

判定规则：
  1. diff 中每处差异逐条与意图匹配（场景命中 + 路径 glob 命中 + req 非空）。
  2. 未被任何意图覆盖的差异 = 回归嫌疑（suspect）-> exit 1，禁止合并。
  3. 未消费任何差异的意图 = stale intent -> 告警不拦截（改动未生效/意图写错的信号）。
  4. 意图清单缺失 / 意图缺 req 或 reason -> 直接报错退出（放行必须留痕，
     格式错误不进入裁决；文件缺失不允许静默当作空清单）。

输出 fence/captures/verdict_report.json：intended / suspects / stale_intents 三段。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import time
from pathlib import Path

try:
    import yaml
except ImportError:  # CI 需 pip install pyyaml
    yaml = None


def load_intents(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        # 静默返回空会让配错路径的 CI 永远"没有意图"，看似更严实则不可审计——必须显式失败
        raise SystemExit(f"[fence.verdict] 意图清单不存在: {p}（无意图请提供 intents: [] 的文件）")
    if yaml is None:
        raise SystemExit("[fence.verdict] 缺少 PyYAML（pip install pyyaml）")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    intents = data.get("intents") or []
    errors = []
    for i, it in enumerate(intents):
        if not it.get("req"):
            errors.append(f"intents[{i}] 缺 req（放行必须挂需求条目）")
        if not it.get("reason"):
            errors.append(f"intents[{i}] 缺 reason")
        if not it.get("scenarios"):
            errors.append(f"intents[{i}] 缺 scenarios")
    if errors:
        raise SystemExit("[fence.verdict] 意图清单格式错误：\n  " + "\n  ".join(errors))
    return intents


def _intent_matches(intent: dict, scenario: str, path: str) -> bool:
    scs = intent["scenarios"]
    if "*" not in scs and scenario not in scs:
        return False
    paths = intent.get("paths")
    if not paths:
        return True  # 未声明路径 = 场景内所有差异均预期
    return any(fnmatch.fnmatch(path, pat) for pat in paths)


def judge(report: dict, intents: list[dict]) -> dict:
    intended, suspects = [], []
    consumed = [False] * len(intents)

    for sc in report["scenarios"]:
        if sc["verdict"] == "same":
            continue
        # 场景级差异（新增/删除场景）：路径记为 head_only / base_only
        units = sc["diffs"] or [{"path": sc["verdict"], "base": None, "head": None}]
        for d in units:
            hit = None
            for i, it in enumerate(intents):
                if _intent_matches(it, sc["scenario"], d["path"]):
                    hit = i
                    consumed[i] = True
                    break
            entry = {"scenario": sc["scenario"], "req_scenario": sc.get("req", ""),
                     "path": d["path"], "base": d.get("base"), "head": d.get("head")}
            if hit is not None:
                entry["intent_req"] = intents[hit]["req"]
                entry["intent_reason"] = intents[hit]["reason"]
                intended.append(entry)
            else:
                suspects.append(entry)

    stale = [it for i, it in enumerate(intents) if not consumed[i]]
    return {
        "diff_report": {k: report.get(k) for k in
                        ("base_meta", "head_meta", "scenario_total", "diff_total")},
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "intended": intended,
        "suspects": suspects,
        "stale_intents": stale,
        "verdict": "PASS" if not suspects else "BLOCK",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="行为围栏裁决器")
    ap.add_argument("diff_report")
    ap.add_argument("--intents", default=str(Path(__file__).resolve().parent / "intents.yml"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    report = json.loads(Path(args.diff_report).read_text(encoding="utf-8"))
    intents = load_intents(args.intents)
    result = judge(report, intents)

    out = Path(args.out) if args.out else \
        Path(__file__).resolve().parent / "captures" / "verdict_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fence.verdict] 差异 {report['diff_total']} 处："
          f"预期 {len(result['intended'])} / 嫌疑 {len(result['suspects'])} "
          f"/ 失效意图 {len(result['stale_intents'])}")
    for e in result["intended"]:
        print(f"  [预期] {e['scenario']} :: {e['path']}  <- {e['intent_req']}（{e['intent_reason']}）")
    for e in result["suspects"]:
        print(f"  [嫌疑] {e['scenario']} :: {e['path']}")
        print(f"         base={json.dumps(e['base'], ensure_ascii=False)[:110]}")
        print(f"         head={json.dumps(e['head'], ensure_ascii=False)[:110]}")
    for it in result["stale_intents"]:
        print(f"  [警告] 失效意图 {it['req']}：声明了变更但围栏未观测到（改动未生效或意图写错）")
    print(f"[fence.verdict] {result['verdict']} -> {out}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
