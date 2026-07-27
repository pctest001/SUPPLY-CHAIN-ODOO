"""增量止血门禁（支柱三）：新变更必须挂已登记的需求条目。

用法：
  python -m kb.gate --text "feat: 收货守卫调整 REQ-C3-LOT"     # 检查任意文本
  python -m kb.gate --text-env PR_TEXT                          # 从环境变量读（CI 防注入）
  python -m kb.gate --intents fence/intents.yml                 # 检查意图清单 REQ 存在性
  （三者可组合，全部通过才 exit 0）

规则：
  1. 文本检查：必须至少引用 1 个 REQ-xxx，且全部在 KB 中登记（status 非 deprecated）。
  2. intents 检查：每条意图的 req 必须在 KB 中登记。
  3. 引用了 KB 不存在的 REQ = 失败（防止随手编号绕过门禁——编号必须先 kb.store add）。
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from kb.store import load

try:
    import yaml
except ImportError:
    yaml = None

REQ_REF_RE = re.compile(r"\bREQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")


def check_text(text: str, reqs: dict) -> list[str]:
    errors = []
    found = sorted(set(REQ_REF_RE.findall(text)))
    if not found:
        errors.append("文本未引用任何 REQ-xxx（新变更必须关联需求条目；"
                      "无条目请先 python -m kb.store add，口头共识用 --provenance oral）")
        return errors
    for rid in found:
        r = reqs.get(rid)
        if not r:
            errors.append(f"{rid} 未在 KB 登记（kb/requirements.json）")
        elif r.status == "deprecated":
            errors.append(f"{rid} 已废弃（deprecated），不能作为新变更依据")
    if not errors:
        print(f"[kb.gate] 文本引用 REQ 校验通过: {', '.join(found)}")
    return errors


def check_intents(path: str, reqs: dict) -> list[str]:
    p = Path(path)
    if not p.exists():
        return [f"意图清单不存在: {p}"]
    if yaml is None:
        return ["缺少 PyYAML（pip install pyyaml）"]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    errors = []
    intents = data.get("intents") or []
    for i, it in enumerate(intents):
        rid = it.get("req", "")
        if rid not in reqs:
            errors.append(f"intents[{i}] req={rid or '(空)'} 未在 KB 登记")
    if not errors:
        print(f"[kb.gate] intents REQ 校验通过（{len(intents)} 条意图）")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="增量止血门禁")
    ap.add_argument("--text", help="待检查文本（PR 标题/描述/提交信息）")
    ap.add_argument("--text-env", help="从该环境变量读取待检查文本（CI 防注入）")
    ap.add_argument("--intents", help="意图清单路径")
    args = ap.parse_args()

    if not (args.text or args.text_env or args.intents):
        ap.error("至少提供 --text / --text-env / --intents 之一")

    reqs = load()
    errors = []
    if args.text is not None:
        errors += check_text(args.text, reqs)
    if args.text_env:
        errors += check_text(os.environ.get(args.text_env, ""), reqs)
    if args.intents:
        errors += check_intents(args.intents, reqs)

    if errors:
        print("[kb.gate] 门禁失败：")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print("[kb.gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
