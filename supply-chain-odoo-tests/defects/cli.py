"""缺陷闭环层 —— CLI。

子命令：
  list                      列出缺陷（--status/--source/--category 过滤）
  show <id>                 查看单条缺陷详情
  emit-ci                   CI 门禁命中真实缺陷时建单（可配合 CI 失败步骤调用）
  transition <id> <to>      状态机转移，可挂 --owner/--fix-ref/--verified-by
  summary                   打印本地汇总 md 路径

端到端示例（用已知真 bug：mutation 抓到「查过期批次用了不存在字段」）：
  python -m defects.cli emit-ci --source mutation --key M5 \\
      --title "查过期批次查询引用未定义字段" --severity high --category mutation \\
      --evidence '{"mutation_point":"M5","detected_by":"mutation_gate"}'
  python -m defects.cli transition DEF-001 Fixing --owner alice
  python -m defects.cli transition DEF-001 Verifying --fix-ref <commit>
  python -m defects.cli transition DEF-001 Closed \\
      --verified-by "新增用例 po_expiry_field 通过 + mutation M5 注入失败=守卫生效"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .registry import DefectRegistry
from .sink import LocalSink
from .emit import emit_from_ci
from . import STATUSES


def _reg(args) -> DefectRegistry:
    return DefectRegistry(path=Path(args.store)) if args.store else DefectRegistry()


def _sink(reg, args) -> LocalSink:
    p = Path(args.summary) if args.summary else None
    return LocalSink(reg, summary_path=p)


def _cmd_list(args):
    reg = _reg(args)
    rows = reg.query(status=args.status, source=args.source, category=args.category)
    if not rows:
        print("（无匹配缺陷）")
        return 0
    for d in sorted(rows, key=lambda x: (STATUSES.index(x.status), x.id)):
        print(f"{d.id} [{d.status}] {d.severity}/{d.category} src={d.source} "
              f"x{d.occurrences} {d.title}")
    print(f"\n共 {len(rows)} 条")
    return 0


def _cmd_show(args):
    reg = _reg(args)
    d = reg.get(args.id)
    if d is None:
        print(f"未知缺陷 {args.id}", file=sys.stderr)
        return 1
    print(json.dumps(d.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_emit_ci(args):
    reg = _reg(args)
    sink = _sink(reg, args)
    evidence = json.loads(args.evidence) if args.evidence else {}
    d, is_new = emit_from_ci(args.source, args.key, args.title,
                              severity=args.severity, category=args.category,
                              evidence=evidence, registry=reg, sink=sink)
    print(f"{'新建' if is_new else '合并(已存在)'} -> {d.id} [{d.status}] {d.title}")
    return 0


def _cmd_transition(args):
    reg = _reg(args)
    sink = _sink(reg, args)
    try:
        d = reg.transition(args.id, args.to, owner=args.owner,
                           fix_ref=args.fix_ref, verified_by=args.verified_by)
    except (KeyError, ValueError) as e:
        print(f"转移失败：{e}", file=sys.stderr)
        return 1
    sink.emit(d, False)
    print(f"{d.id}: {args.to} (owner={d.owner or '-'} fix_ref={d.fix_ref or '-'} "
          f"verified_by={d.verified_by or '-'})")
    return 0


def _cmd_summary(args):
    reg = _reg(args)
    sink = _sink(reg, args)
    sink._write_summary()
    print(f"汇总已写出：{sink.summary_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="缺陷闭环层 CLI")
    ap.add_argument("--store", default=None, help="defects.jsonl 路径(默认包内)")
    ap.add_argument("--summary", default=None, help="汇总 md 路径(默认同目录 defects_summary.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出缺陷")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--source")
    p.add_argument("--category")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show", help="查看详情")
    p.add_argument("id")
    p.set_defaults(func=_cmd_show)

    p = sub.add_parser("emit-ci", help="CI 门禁命中真实缺陷时建单")
    p.add_argument("--source", required=True, help="ci_gate 子源：mutation/behavior_fence/rpc/ui/ai_eval/prod_monitor")
    p.add_argument("--key", required=True, help="去重键(如变异点 M5 / 用例名)")
    p.add_argument("--title", required=True)
    p.add_argument("--severity", default="high", choices=["critical", "high", "medium", "low"])
    p.add_argument("--category", default="other")
    p.add_argument("--evidence", default=None, help="JSON 字符串，溯源信息")
    p.set_defaults(func=_cmd_emit_ci)

    p = sub.add_parser("transition", help="状态机转移")
    p.add_argument("id")
    p.add_argument("to", choices=STATUSES)
    p.add_argument("--owner")
    p.add_argument("--fix-ref")
    p.add_argument("--verified-by")
    p.set_defaults(func=_cmd_transition)

    p = sub.add_parser("summary", help="写出汇总 md")
    p.set_defaults(func=_cmd_summary)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
