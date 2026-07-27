"""Markdown 汇总（给人读的周/日报，CI 可写入 $GITHUB_STEP_SUMMARY）。

结构：概览 → L4 评测 → L6 监控 → 告警与 Bad Case → 闭环建议。
全部「尽力而为」：任一报告缺失只跳过该段，不会整体崩。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .history import series


def _md_table(headers, rows) -> str:
    if not rows:
        return "_（无数据）_\n"
    head = "| " + " | ".join(headers) + " |\n"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |\n"
    body = ""
    for r in rows:
        body += "| " + " | ".join(str(c) for c in r) + " |\n"
    return head + sep + body


def build_markdown(data: dict, history: list | None = None) -> str:
    eval_r = data.get("eval_report") or {}
    prod_r = data.get("prod_report") or {}
    em = eval_r.get("metrics") or {}
    pm = prod_r.get("metrics") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alert_level = data.get("alert_level", "ok")
    parts = []
    parts.append(f"# 供应链 AI · QA 测试报告汇总\n")
    parts.append(f"> 生成于 {now} ｜ 告警等级：**{alert_level.upper()}**\n")

    # ---- 概览 ----
    parts.append("## 概览")
    ov = []
    if em:
        ov.append(["L4 综合质量分", f"{em.get('quality_score')}%", "≥80 通过" if em.get('quality_score', 0) >= 80 else "不达标"])
    if pm:
        ov.append(["L6 生产综合准确率", f"{pm.get('prod_accuracy')}%", "≥80 通过" if pm.get('prod_accuracy', 0) >= 80 else "不达标"])
    ov.append(["回流 Bad Case", f"{data.get('bad_cases_count', 0)} 条", "待回流 L4" if data.get('bad_cases_count', 0) else "无"])
    parts.append(_md_table(["指标", "数值", "状态"], ov))

    # ---- L4 ----
    parts.append("\n## L4 · AI 评测（研发期回归门禁）")
    if em:
        q = em.get("quality_score", 0)
        verdict = "✅ PASS" if q >= 80 and not eval_r.get("regression") else "❌ FAIL"
        parts.append(f"判定：**{verdict}** ｜ 用例数 {em.get('total')} ｜ 通过 {em.get('passed')}")
        parts.append(_md_table(
            ["准确率", "幻觉率", "拒答准确率", "安全违规率", "质量分"],
            [[f"{em.get('accuracy')}%", f"{em.get('hallucination_rate')}%",
              f"{em.get('refusal_accuracy')}%", f"{em.get('safety_violation_rate')}%",
              f"{em.get('quality_score')}%"]]))
        diff = eval_r.get("baseline_diff") or {}
        if diff:
            parts.append(f"\n基线差异：`{diff}` ｜ {'⚠ 退化' if eval_r.get('regression') else '✅ 稳定'}")
        if history is not None:
            ev = series(history, "eval", "quality_score")
            if len(ev) >= 2:
                parts.append(f"\n质量分趋势（近 {len(ev)} 次）：{' → '.join(f'{v:.0f}' for _, v in ev[-8:])}")
    else:
        parts.append("_未找到 eval_report.json（先跑 `python -m eval.run_eval --mode sim`）_")

    # ---- L6 ----
    parts.append("\n## L6 · 生产监控（治理）")
    if pm:
        parts.append(_md_table(
            ["生产综合准确率", "幻觉率", "安全违规率", "拒答准确率"],
            [[f"{pm.get('prod_accuracy')}%", f"{pm.get('hallucination_rate')}%",
              f"{pm.get('safety_violation_rate')}%", f"{pm.get('refusal_accuracy')}%"]]))
        _vraw = prod_r.get("version_distribution") or {}
        vrep = (_vraw.get("distribution") if isinstance(_vraw, dict)
                else _vraw if isinstance(_vraw, list) else [])
        if vrep:
            vs = "，".join(f"{d.get('prompt_version')}/{d.get('model_used')}×{d.get('count')}" for d in vrep)
            parts.append(f"\n版本分布：{vs}")
        if prod_r.get("degraded"):
            parts.append("\n⚠ 相对 L4 基线退化，详见 prod_report.json")
        if history is not None:
            pv = series(history, "prod", "prod_accuracy")
            if len(pv) >= 2:
                parts.append(f"\n生产准确率趋势（近 {len(pv)} 次）：{' → '.join(f'{v:.0f}' for _, v in pv[-8:])}")
    else:
        parts.append("_未找到 prod_report.json（先跑 `python -m prodmon.run_monitor --mode sim`）_")

    # ---- 告警与 bad case ----
    parts.append("\n## 告警与 Bad Case")
    alerts = data.get("alerts") or []
    if alerts:
        rows = [[a.get("level", ""), a.get("metric", ""), a.get("value", ""),
                 a.get("threshold", ""), a.get("detail", "")] for a in alerts]
        parts.append(_md_table(["等级", "指标", "值", "阈值", "说明"], rows))
    else:
        parts.append("✅ 本轮无告警")
    n = data.get("bad_cases_count", 0)
    parts.append(f"\n回流 L4 的 bad case：**{n}** 条（prodmon/bad_cases.jsonl）")
    for b in (data.get("bad_cases") or [])[:5]:
        sc = b.get("suggested_eval_case") or {}
        parts.append(f"- `{b.get('session_id','')}` · {sc.get('category','')} · refuse={sc.get('refuse')}")

    # ---- 闭环建议 ----
    parts.append("\n## 闭环建议（自动生成）")
    adv = []
    if pm.get("safety_violation_rate", 0) > 0:
        adv.append("- 🔴 生产出现安全违规（白名单外工具执行）：立即排查 `ai.chat.tool.log`，确认提示词/工具白名单是否被破坏。")
    if pm.get("hallucination_rate", 0) > 5:
        adv.append("- 🟡 生产幻觉率超 5%：抽取 bad case 回流 L4 评测集，强化事实性约束或升级 LLM-as-Judge 复查。")
    if em.get("regression"):
        adv.append("- ⚠ L4 评测较基线退化：定位退化的 case，优先修复对应能力或回滚相关 prompt 版本。")
    if n > 0 and not adv:
        adv.append(f"- 有 {n} 条 bad case：建议合入 L4 评测集，形成「监控→bad case→L4 回归→prompt 迭代」闭环。")
    if not adv:
        adv.append("- ✅ 当前指标健康，保持每日定时巡检与 push 触发的双通道监控即可。")
    parts.append("\n".join(adv))

    return "\n".join(parts) + "\n"
