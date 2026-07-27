"""考古工具箱 · 首件：Odoo 视图 XML 逆向（支柱二 · 按需考古）。

用法（在 supply-chain-odoo-tests 目录下）：
  python -m kb.reverse_views                       # 扫默认 ../custom_addons/*/views/*.xml
  python -m kb.reverse_views --addons path/to/custom_addons
  python -m kb.reverse_views --model purchase.order   # 只看某个模型

做什么：
  从自定义模块的视图 XML 里提取「行为需求的代码痕迹」：
  1. 工作流按钮 + 守卫条件（button@name + invisible）→ 状态守卫类候选需求
  2. 状态机（widget="statusbar" + statusbar_visible）    → 生命周期类候选需求
  3. readonly="1" 字段                                   → 系统生成/不可手改类候选需求
  并与 fence/scenarios/*.json 交叉验证：按钮方法名出现在某场景里 → 标注
  covered_by 该场景的 REQ；没出现 → 未覆盖候选（考古最有价值的产出）。

不做什么（设计红线）：
  - 不自动写入 kb/requirements.json。产出是「候选清单」kb/candidates_views.json，
    必须人审后用 `python -m kb.store add` 逐条登记（provenance=code-inferred，
    置信度 0.6，正是需要人工确认的档位）。
  - 不解析继承合并后的最终视图（那需要运行实例）。这里逆向的是
    「自定义模块自己声明了什么」，即我们自己代码承载的需求，噪声最小。
  - 属性级中文化覆盖（position="attributes" 改 string）天然被跳过：
    只提取 <button> 元素节点，不提取 <attribute> 文本。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # supply-chain-odoo-tests
DEFAULT_ADDONS = ROOT.parent / "custom_addons"
SCENARIOS_DIR = ROOT / "fence" / "scenarios"
OUT_FILE = HERE / "candidates_views.json"

# 明显是纯 UI/装饰的按钮方法名前缀，不构成行为需求
UI_NOISE_BUTTONS = {"action_open_form", "action_view_pos"}


def _iter_view_records(xml_path: Path):
    """yield (view_id, model, arch_element)。解析失败跳过该文件并告警。"""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"[reverse_views] WARN 解析失败跳过 {xml_path}: {e}", file=sys.stderr)
        return
    for rec in tree.getroot().iter("record"):
        if rec.get("model") != "ir.ui.view":
            continue
        model, arch = None, None
        for f in rec.findall("field"):
            if f.get("name") == "model":
                model = (f.text or "").strip()
            elif f.get("name") == "arch":
                arch = f
        if model and arch is not None:
            yield rec.get("id", "?"), model, arch


def _extract_buttons(view_id: str, model: str, arch, src: str) -> list[dict]:
    out = []
    for btn in arch.iter("button"):
        name = btn.get("name")
        if not name or btn.get("special"):          # special=cancel 等纯 UI
            continue
        if btn.get("type") != "object":             # 只关心业务方法按钮
            continue
        out.append({
            "kind": "workflow-button",
            "model": model,
            "method": name,
            "label": btn.get("string", ""),
            "guard_invisible": btn.get("invisible", ""),
            "statement": _button_statement(model, name, btn.get("string", ""),
                                           btn.get("invisible", "")),
            "evidence": {"file": src, "view_id": view_id},
        })
    return out


def _button_statement(model: str, method: str, label: str, invisible: str) -> str:
    base = f"{model} 提供「{label or method}」操作（{method}）"
    if invisible:
        return f"{base}，当 {invisible} 时不可用（状态守卫）"
    return f"{base}，无状态守卫（任何状态可用——请人工确认这是否符合预期）"


def _extract_statusbars(view_id: str, model: str, arch, src: str) -> list[dict]:
    out = []
    for f in arch.iter("field"):
        if f.get("widget") != "statusbar":
            continue
        states = f.get("statusbar_visible", "")
        out.append({
            "kind": "state-machine",
            "model": model,
            "field": f.get("name", ""),
            "states": [s.strip() for s in states.split(",") if s.strip()],
            "statement": (f"{model}.{f.get('name')} 是生命周期状态机，"
                          f"可见状态序列：{states or '(未声明)'}"),
            "evidence": {"file": src, "view_id": view_id},
        })
    return out


def _extract_readonly(view_id: str, model: str, arch, src: str) -> list[dict]:
    out = []
    for f in arch.iter("field"):
        if f.get("readonly") != "1":
            continue
        name = f.get("name", "")
        out.append({
            "kind": "readonly-field",
            "model": model,
            "field": name,
            "statement": (f"{model}.{name} 界面只读——由系统生成/流程写入，"
                          f"不允许用户手改"),
            "evidence": {"file": src, "view_id": view_id},
        })
    return out


def _load_scenario_index() -> list[tuple[str, str, str]]:
    """[(scenario_id, req, 全文)]，用于按钮方法名交叉验证。"""
    idx = []
    if not SCENARIOS_DIR.exists():
        return idx
    for p in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("scenarios", [])
        for sc in items:
            if isinstance(sc, dict):
                idx.append((sc.get("id", "?"), sc.get("req", ""),
                            json.dumps(sc, ensure_ascii=False)))
    return idx


def _cross_check(candidates: list[dict], scen_idx) -> None:
    """就地为每个候选补 covered_by（去重的 REQ 列表）。

    匹配要求「模型名 AND 方法名」同时出现在场景全文里——只按方法名匹配会把
    sc.supplier.ack.wizard.action_reject 误判为被 PO 审批场景覆盖（同名方法）。
    """
    for c in candidates:
        key = c.get("method") or ""
        model = c.get("model") or ""
        reqs = []
        if key:
            for _sid, req, text in scen_idx:
                if key in text and model in text and req and req not in reqs:
                    reqs.append(req)
        c["covered_by"] = reqs
        c["provenance"] = "code-inferred"
        c["confidence"] = 0.6


def collect(addons: Path, model_filter: str | None = None) -> dict:
    xml_files = sorted(addons.glob("*/views/*.xml"))
    candidates: list[dict] = []
    for xml in xml_files:
        src = str(xml.relative_to(addons.parent))
        for view_id, model, arch in _iter_view_records(xml):
            if model_filter and model != model_filter:
                continue
            candidates += _extract_buttons(view_id, model, arch, src)
            candidates += _extract_statusbars(view_id, model, arch, src)
            candidates += _extract_readonly(view_id, model, arch, src)

    # 去噪 + 去重（同模型同方法/字段只留首个证据）
    seen, deduped = set(), []
    for c in candidates:
        if c.get("method") in UI_NOISE_BUTTONS:
            continue
        key = (c["kind"], c["model"], c.get("method") or c.get("field"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    _cross_check(deduped, _load_scenario_index())
    uncovered = [c for c in deduped if c["kind"] == "workflow-button"
                 and not c["covered_by"]]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "addons_dir": str(addons),
        "source_files": [str(p.relative_to(addons.parent)) for p in xml_files],
        "total": len(deduped),
        "uncovered_buttons": len(uncovered),
        "candidates": deduped,
    }


def main():
    ap = argparse.ArgumentParser(description="视图 XML 逆向 → 候选需求清单")
    ap.add_argument("--addons", default=str(DEFAULT_ADDONS),
                    help=f"custom_addons 目录（默认 {DEFAULT_ADDONS}）")
    ap.add_argument("--model", default=None, help="只提取指定模型")
    ap.add_argument("--out", default=str(OUT_FILE))
    args = ap.parse_args()

    addons = Path(args.addons)
    if not addons.exists():
        raise SystemExit(f"[reverse_views] addons 目录不存在: {addons}")

    report = collect(addons, args.model)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[reverse_views] 候选 {report['total']} 条 -> {args.out}", file=sys.stderr)
    # 摘要：未覆盖的工作流按钮（考古最有价值的输出）
    for c in report["candidates"]:
        if c["kind"] == "workflow-button" and not c["covered_by"]:
            print(f"  [未覆盖] {c['model']}.{c['method']}"
                  f"（{c['label']}）guard={c['guard_invisible'] or '无'}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
