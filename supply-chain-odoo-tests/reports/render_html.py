"""自包含 HTML 仪表盘（内联 CSS + 内联 SVG 趋势图，零外部依赖，离线可看）。

形态：顶栏概览 → L4 AI 评测指标卡 + quality_score 趋势 → L6 生产监控指标卡 +
prod_accuracy 趋势 → 告警与 bad case 面板。所有样式/图表内联，双击即可打开。
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .history import series
from .collect import HISTORY


def _esc(s) -> str:
    return html.escape(str(s))


def _svg_line(points, color, width=680, height=170):
    """points: list[(label, value)]，画出内联折线图。value 落在 [0,100] 左右。"""
    if not points:
        return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
                f'height="{height}" xmlns="http://www.w3.org/2000/svg">'
                f'<text x="{width//2}" y="{height//2}" fill="#9ca3af" '
                f'text-anchor="middle" font-size="13">暂无趋势数据（先跑一次评测/监控）</text>'
                f'</svg>')
    vals = [v for _, v in points]
    lo = max(0, min(vals) - 5)
    hi = max(vals) + 5
    if hi <= lo:
        hi = lo + 10
    pad_l, pad_r, pad_t, pad_b = 34, 14, 14, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(points)

    def xpos(i):
        return pad_l + (plot_w * i / (n - 1)) if n > 1 else pad_l + plot_w / 2

    def ypos(v):
        return pad_t + plot_h * (1 - (v - lo) / (hi - lo))

    # 网格线（lo / 中 / hi）
    grid = ""
    for gv in (lo, (lo + hi) / 2, hi):
        gy = ypos(gv)
        grid += (f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width-pad_r}" y2="{gy:.1f}" '
                 f'stroke="#eceff3" stroke-width="1"/>'
                 f'<text x="{pad_l-6}" y="{gy+4:.1f}" fill="#9ca3af" '
                 f'font-size="10" text-anchor="end">{gv:.0f}</text>')

    poly = " ".join(f"{xpos(i):.1f},{ypos(v):.1f}" for i, (_, v) in enumerate(points))
    dots = ""
    last_i, last_v = n - 1, vals[-1]
    for i, (lbl, v) in enumerate(points):
        cx, cy = xpos(i), ypos(v)
        dots += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{color}"/>'
        if i == last_i:  # 末端标注最新值
            dots += (f'<text x="{min(cx+6, width-30):.1f}" y="{cy-6:.1f}" '
                     f'fill="{color}" font-size="11" font-weight="600">{last_v:.0f}</text>')
            # x 轴末端日期
            short = str(lbl)[:10]
            dots += (f'<text x="{min(cx, width-pad_r):.1f}" y="{height-6}" '
                     f'fill="#9ca3af" font-size="10" text-anchor="middle">{_esc(short)}</text>')

    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'{grid}'
            f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{poly}"/>'
            f'{dots}</svg>')


def _card(label, value, good, suffix="%"):
    color = "#16a34a" if good else "#dc2626"
    vstr = (f"{value:.1f}{suffix}") if isinstance(value, (int, float)) else str(value)
    return (f'<div class="card"><div class="card-val" style="color:{color}">{_esc(vstr)}'
            f'</div><div class="card-label">{_esc(label)}</div></div>')


def _status_good(name, value):
    """判断指标是否健康（用于卡片配色）。"""
    if value is None:
        return True
    if name in ("quality_score", "accuracy", "prod_accuracy", "refusal_accuracy"):
        return value >= 80
    if name in ("hallucination_rate", "safety_violation_rate"):
        return value <= 0
    return True


def build_dashboard_html(data: dict, history: list | None = None,
                         history_path=HISTORY) -> str:
    if history is None:
        from .history import load_history
        history = load_history(history_path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alert_level = data.get("alert_level", "ok")
    alert_color = {"critical": "#dc2626", "warning": "#d97706", "ok": "#16a34a"}.get(
        alert_level, "#16a34a")

    eval_r = data.get("eval_report") or {}
    prod_r = data.get("prod_report") or {}
    em = eval_r.get("metrics") or {}
    pm = prod_r.get("metrics") or {}

    # ---- L4 卡片 ----
    l4_cards = ""
    for name, label in (("quality_score", "综合质量分"),
                        ("accuracy", "工具准确率"),
                        ("hallucination_rate", "幻觉率"),
                        ("refusal_accuracy", "拒答准确率"),
                        ("safety_violation_rate", "安全违规率")):
        if name in em:
            l4_cards += _card(label, em[name], _status_good(name, em[name]))

    # ---- L6 卡片 ----
    l6_cards = ""
    for name, label in (("prod_accuracy", "生产综合准确率"),
                        ("hallucination_rate", "生产幻觉率"),
                        ("safety_violation_rate", "生产安全违规率"),
                        ("refusal_accuracy", "生产拒答准确率")):
        if name in pm:
            l6_cards += _card(label, pm[name], _status_good(name, pm[name]))

    # ---- 趋势 ----
    l4_trend = _svg_line(series(history, "eval", "quality_score"), "#2563eb")
    l6_trend = _svg_line(series(history, "prod", "prod_accuracy"), "#7c3aed")

    # ---- 版本分布 ----
    _vraw = prod_r.get("version_distribution") or {}
    vrep = (_vraw.get("distribution") if isinstance(_vraw, dict)
            else _vraw if isinstance(_vraw, list) else [])
    if vrep:
        vdist = " · ".join(
            f'{_esc(d.get("prompt_version"))}/{_esc(d.get("model_used"))}×{d.get("count")}'
            for d in vrep)
    else:
        vdist = "无数据"

    # ---- 告警 ----
    alerts_html = ""
    for a in data.get("alerts") or []:
        lvl = a.get("level", "warning")
        c = "#dc2626" if lvl == "critical" else "#d97706"
        icon = "🔴" if lvl == "critical" else "🟡"
        alerts_html += (f'<div class="alert"><span style="color:{c}">{icon} '
                        f'{_esc(lvl.upper())}</span> · {_esc(a.get("metric",""))} = '
                        f'{_esc(a.get("value",""))}（阈值 {_esc(a.get("threshold",""))}）<br>'
                        f'<span class="muted">{_esc(a.get("detail",""))}</span></div>')
    if not alerts_html:
        alerts_html = '<div class="alert ok">✅ 本轮无告警</div>'

    bad_n = data.get("bad_cases_count", 0)
    bc_html = (f'<div class="muted">回流 L4 的 bad case：<b>{bad_n}</b> 条'
               f'（prodmon/bad_cases.jsonl）</div>')
    if bad_n:
        sample = data.get("bad_cases") or []
        rows = ""
        for b in sample[:5]:
            sc = b.get("suggested_eval_case") or {}
            rows += (f'<li>{_esc(b.get("session_id",""))} — '
                     f'{_esc(sc.get("category",""))} '
                     f'refuse={sc.get("refuse")}</li>')
        bc_html += f'<ul class="badlist">{rows}</ul>'

    regression = em.get("regression") if isinstance(em, dict) else None
    degrade_note = ""
    if prod_r.get("degraded"):
        degrade_note = '<div class="alert" style="color:#d97706">⚠ 相对 L4 基线退化，详见 prod_report.json</div>'
    elif regression:
        degrade_note = '<div class="alert" style="color:#d97706">⚠ L4 评测相对基线退化</div>'

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>供应链 AI QA 报告仪表盘</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f7fa; color: #1f2937; }}
  .wrap {{ max-width: 1040px; margin: 0 auto; padding: 24px 20px 48px; }}
  header {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }}
  h1 {{ font-size: 20px; margin: 0; }}
  .sub {{ color: #6b7280; font-size: 13px; }}
  .pill {{ display: inline-block; padding: 3px 10px; border-radius: 999px; color: #fff;
          font-size: 12px; font-weight: 600; background: {alert_color}; }}
  section {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
            padding: 18px 20px; margin-top: 16px; }}
  h2 {{ font-size: 15px; margin: 0 0 12px; color: #374151; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .card {{ flex: 1 1 140px; min-width: 130px; background: #f9fafb; border: 1px solid #eef1f5;
          border-radius: 10px; padding: 14px 16px; }}
  .card-val {{ font-size: 26px; font-weight: 700; }}
  .card-label {{ font-size: 12px; color: #6b7280; margin-top: 4px; }}
  .chart {{ margin-top: 14px; border: 1px solid #eef1f5; border-radius: 10px; padding: 8px 10px; background: #fff; }}
  .alert {{ padding: 8px 10px; border-radius: 8px; background: #fff7ed; border: 1px solid #fed7aa;
           margin: 6px 0; font-size: 13px; }}
  .alert.ok {{ background: #f0fdf4; border-color: #bbf7d0; color: #166534; }}
  .muted {{ color: #6b7280; font-size: 12px; }}
  .badlist {{ margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: #4b5563; }}
  .vdist {{ font-size: 13px; color: #374151; margin-top: 6px; }}
</style></head>
<body><div class="wrap">
  <header>
    <div><h1>供应链 AI · QA 报告仪表盘</h1>
      <div class="sub">生成于 {now} ｜ L4 评测 + L6 生产监控统一呈现</div></div>
    <div><span class="pill">告警等级：{alert_level.upper()}</span></div>
  </header>

  <section>
    <h2>L4 · AI 评测（研发期回归门禁）</h2>
    <div class="cards">{l4_cards or '<div class="muted">未找到 eval_report.json（先跑 python -m eval.run_eval）</div>'}</div>
    <div class="chart">{l4_trend}</div>
  </section>

  <section>
    <h2>L6 · 生产监控（治理）</h2>
    <div class="cards">{l6_cards or '<div class="muted">未找到 prod_report.json（先跑 python -m prodmon.run_monitor）</div>'}</div>
    <div class="vdist">版本分布：{vdist}</div>
    <div class="chart">{l6_trend}</div>
  </section>

  <section>
    <h2>告警与 Bad Case</h2>
    {alerts_html}
    {bc_html}
    {degrade_note}
  </section>
</div></body></html>"""
