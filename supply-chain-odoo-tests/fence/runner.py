"""围栏运行器 CLI：对指定目标实例跑场景库，输出 capture JSON。

用法（在 supply-chain-odoo-tests 目录下）：
  python -m fence.runner --target head                    # 全量场景
  python -m fence.runner --target head --scenario s_po_reject
  python -m fence.runner --target base --run-id 20260724a # 与 head 用同一 run_id 对齐 $uniq
  python -m fence.runner --target head --list             # 仅列场景

关键约定：
  base 与 head 必须用【同一个 --run-id】跑，$uniq 生成的业务名才双端一致，
  P1 的 diff 才能按业务名对齐记录。不传 run-id 时自动生成并打印。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fence.context import TARGETS, build_context  # noqa: E402
from fence.engine import run_scenario  # noqa: E402

FENCE_DIR = Path(__file__).resolve().parent
SCENARIO_DIR = FENCE_DIR / "scenarios"
CAPTURE_DIR = FENCE_DIR / "captures"


def load_scenarios() -> list[dict]:
    out: list[dict] = []
    for f in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = [data]
        for sc in data:
            sc["_file"] = f.name
            out.append(sc)
    ids = [sc["id"] for sc in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"[fence] 场景 id 重复: {dup}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="行为围栏场景运行器")
    ap.add_argument("--target", choices=list(TARGETS), default="head")
    ap.add_argument("--scenario", help="只跑指定 id 的场景")
    ap.add_argument("--run-id", help="双端对齐用运行 id（base/head 必须一致）")
    ap.add_argument("--list", action="store_true", help="仅列出场景不执行")
    args = ap.parse_args()

    scenarios = load_scenarios()
    if args.list:
        for sc in scenarios:
            print(f"{sc['id']:36s} [{sc.get('req','-'):24s}] {sc.get('title','')}")
        print(f"共 {len(scenarios)} 个场景")
        return 0

    if args.scenario:
        scenarios = [sc for sc in scenarios if sc["id"] == args.scenario]
        if not scenarios:
            raise SystemExit(f"[fence] 找不到场景: {args.scenario}")

    run_id = args.run_id or time.strftime("%Y%m%d%H%M%S")
    target = TARGETS[args.target]
    print(f"[fence] target={target.name} port={target.port} run_id={run_id} "
          f"scenarios={len(scenarios)}")

    client = target.connect()
    ctx = build_context(client)

    captures, t0 = [], time.time()
    for sc in scenarios:
        cap = run_scenario(client, ctx, sc, run_id)
        captures.append(cap)
        mark = "OK " if cap["status"] == "ok" else "ERR"
        print(f"  [{mark}] {sc['id']:36s} {cap['duration_ms']:6d}ms"
              + (f"  {cap['error']}" if cap["error"] else ""))

    CAPTURE_DIR.mkdir(exist_ok=True)
    out_file = CAPTURE_DIR / f"{target.name}_{run_id}.json"
    payload = {
        "target": target.name,
        "port": target.port,
        "run_id": run_id,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(captures),
        "errors": sum(1 for c in captures if c["status"] != "ok"),
        "captures": captures,
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[fence] 完成 {len(captures)} 场景 / {payload['errors']} 错误 "
          f"/ {time.time()-t0:.1f}s -> {out_file}")
    return 1 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
