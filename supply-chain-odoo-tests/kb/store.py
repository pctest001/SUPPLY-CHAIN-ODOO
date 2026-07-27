"""KB 存储：kb/requirements.json 读写 + CLI。

用法：
  python -m kb.store list [--status active] [--provenance oral]
  python -m kb.store show REQ-C2-GUARD-ZERO
  python -m kb.store add --id REQ-X --title "..." [--statement "..."]
                         [--provenance oral --notes "2026-07-27 与测试/开发口头确认"]
  python -m kb.store validate          # 全库校验（CI 可用）
  python -m kb.store link REQ-X --scenario s_xxx   # 挂围栏场景

存储为单一 JSON（版本控制友好，PR diff 里逐条可见——这本身就是评审载体）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kb.model import Requirement

STORE_FILE = Path(__file__).resolve().parent / "requirements.json"


def load() -> dict[str, Requirement]:
    if not STORE_FILE.exists():
        return {}
    data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    return {r["id"]: Requirement.from_dict(r) for r in data.get("requirements", [])}


def save(reqs: dict[str, Requirement]) -> None:
    payload = {
        "version": 1,
        "requirements": [reqs[k].to_dict() for k in sorted(reqs)],
    }
    STORE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="需求 KB 薄存储")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("--status")
    p.add_argument("--provenance")

    p = sub.add_parser("show")
    p.add_argument("req_id")

    p = sub.add_parser("add")
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--statement", default="")
    p.add_argument("--provenance", default="current-prd")
    p.add_argument("--status", default="active")
    p.add_argument("--confidence", type=float, default=-1.0)
    p.add_argument("--notes", default="")

    sub.add_parser("validate")

    p = sub.add_parser("link")
    p.add_argument("req_id")
    p.add_argument("--scenario", action="append", default=[])

    args = ap.parse_args()
    reqs = load()

    if args.cmd == "list":
        rows = [r for r in reqs.values()
                if (not args.status or r.status == args.status)
                and (not args.provenance or r.provenance == args.provenance)]
        for r in sorted(rows, key=lambda x: x.id):
            scs = len(r.links.get("scenarios", []))
            print(f"{r.id:28s} [{r.status:10s}] [{r.provenance:13s}] "
                  f"conf={r.confidence:.1f} 场景×{scs}  {r.title}")
        print(f"共 {len(rows)} 条")
        return 0

    if args.cmd == "show":
        r = reqs.get(args.req_id)
        if not r:
            print(f"不存在: {args.req_id}")
            return 1
        print(json.dumps(r.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "add":
        if args.id in reqs:
            print(f"已存在: {args.id}（如需修改请直接编辑 requirements.json 并跑 validate）")
            return 1
        r = Requirement(id=args.id, title=args.title, statement=args.statement,
                        provenance=args.provenance, status=args.status,
                        confidence=args.confidence, notes=args.notes)
        errs = r.validate()
        if errs:
            print("校验失败：\n  " + "\n  ".join(errs))
            return 1
        reqs[r.id] = r
        save(reqs)
        print(f"已添加 {r.id}（provenance={r.provenance}, confidence={r.confidence}）")
        return 0

    if args.cmd == "validate":
        errs = []
        for r in reqs.values():
            errs.extend(r.validate())
        if errs:
            print("KB 校验失败：\n  " + "\n  ".join(errs))
            return 1
        print(f"KB 校验通过（{len(reqs)} 条）")
        return 0

    if args.cmd == "link":
        r = reqs.get(args.req_id)
        if not r:
            print(f"不存在: {args.req_id}")
            return 1
        scs = set(r.links.get("scenarios", [])) | set(args.scenario)
        r.links["scenarios"] = sorted(scs)
        save(reqs)
        print(f"{r.id} 已挂场景: {r.links['scenarios']}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
