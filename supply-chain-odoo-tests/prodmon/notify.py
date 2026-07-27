"""L6 告警分发：把 prod_alert.json 推送到 IM / 值班渠道（钉钉/企微/Slack 兼容 webhook）。

设计：
  - 优先走 webhook（env PROD_ALERT_WEBHOOK 或 run_monitor --webhook）；
  - 无 webhook 时 dry-run：仅把告警落盘 notify.log，保证可审计、不报错；
  - 无论是否推送，都写 notify.log 审计轨迹（便于事后回溯「监控→bad case→L4 回归」闭环）。
  - 形成持续闭环的「出口」：监控发现异常 → 生产告警进 IM → 值班/治理介入 →
    回流 L4（bad_cases.jsonl 已含 suggested_eval_case）→ 提示词迭代（versioning 对比）。
"""
from __future__ import annotations

import json
import os
import datetime
from pathlib import Path

try:
    import requests
except Exception:  # 离线/最小化环境可能没有 requests（Odoo 自带，但 CI 基础镜像未必）
    requests = None


HERE = Path(__file__).resolve().parent
DEFAULT_ALERT = HERE / "prod_alert.json"
DEFAULT_NOTIFY_LOG = HERE / "notify.log"


def load_alert(path=DEFAULT_ALERT) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def format_markdown(alert: dict) -> str:
    """把告警明细拼成 IM 可读文本（兼容钉钉/企微 text 类型）。"""
    alerts = (alert.get("alerts") or []) if isinstance(alert, dict) else []
    if not alerts:
        return "✅ [供应链AI] 生产监控：本轮无告警"
    lines = [f"🚨 [供应链AI] 生产监控告警（共 {len(alerts)} 条）"]
    for a in alerts:
        icon = "🔴" if a.get("level") == "critical" else "🟡"
        lines.append(
            f"{icon} {a.get('level', '').upper()} · {a.get('metric', '')} = "
            f"{a.get('value')}（阈值 {a.get('threshold')}）\n   {a.get('detail', '')}"
        )
    return "\n".join(lines)


def dispatch(alert: dict, webhook: str | None = None,
             dry_run: bool = False, log_path=DEFAULT_NOTIFY_LOG) -> dict:
    """推送告警。

    返回 dict：{dispatched, status_code?, reason?, logged}。
    webhook 为空 或 dry_run=True（或无 requests）→ 仅落盘 notify.log。
    """
    webhook = webhook or os.getenv("PROD_ALERT_WEBHOOK")
    text = format_markdown(alert)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry = {"timestamp": ts, "target": webhook or "dry-run", "message": text}

    # 审计落盘（无论是否推送，保证闭环可追溯）
    logged = False
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logged = True
    except Exception:
        logged = False

    if dry_run or not webhook or requests is None:
        return {"dispatched": False,
                "reason": "dry-run" if (dry_run or not webhook) else "no-requests",
                "logged": logged}
    try:
        resp = requests.post(
            webhook,
            json={"msgtype": "text", "text": {"content": text}},
            timeout=10,
        )
        return {"dispatched": resp.status_code < 400,
                "status_code": resp.status_code, "logged": logged}
    except Exception as e:  # 推送失败不应阻断 CI/主流程
        return {"dispatched": False, "reason": str(e), "logged": logged}
