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

# 内置默认 @手机号：告警时 @值班/治理负责人（钉钉群机器人 atMobiles 触发端内提醒）。
# 可用 env PROD_ALERT_AT_MOBILES（逗号分隔）或 dispatch(at_mobiles=...) 覆盖。
DEFAULT_AT_MOBILES = ["18658159309"]


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


def _resolve_at_mobiles(at_mobiles: list | None) -> list:
    """解析要 @的手机号列表。

    优先级：显式参数 > env PROD_ALERT_AT_MOBILES > 内置默认 DEFAULT_AT_MOBILES。
    显式传空列表 [] 可关闭 @（不 @任何人）。
    """
    if at_mobiles is not None:
        return [m.strip() for m in at_mobiles if m.strip()]
    env = os.getenv("PROD_ALERT_AT_MOBILES")
    if env:
        return [m.strip() for m in env.split(",") if m.strip()]
    return list(DEFAULT_AT_MOBILES)


def _is_dingtalk(webhook: str | None) -> bool:
    return bool(webhook) and "oapi.dingtalk.com" in webhook


def _build_payload(text: str, webhook: str, at_mobiles: list) -> dict:
    """按 webhook 平台构造推送体。

    钉钉 text 类型：@手机号需在 content 中出现才会触发端内提醒，故把 @<mobile>
    拼到正文末尾，并附 at.atMobiles 便于群内高亮。企微/Slack 暂按纯文本推送。
    """
    if _is_dingtalk(webhook):
        at_suffix = "".join(f"\n@{m}" for m in at_mobiles)
        return {"msgtype": "text",
                "text": {"content": text + at_suffix},
                "at": {"atMobiles": at_mobiles, "isAtAll": False}}
    return {"msgtype": "text", "text": {"content": text}}


def dispatch(alert: dict, webhook: str | None = None,
             dry_run: bool = False, log_path=DEFAULT_NOTIFY_LOG,
             at_mobiles: list | None = None) -> dict:
    """推送告警。

    返回 dict：{dispatched, status_code?, reason?, logged, at_mobiles}。
    webhook 为空 或 dry_run=True（或无 requests）→ 仅落盘 notify.log。
    at_mobiles：要 @的手机号（钉钉群机器人 atMobiles 触发端内提醒）；
        缺省取 env PROD_ALERT_AT_MOBILES 或内置默认 18658159309。
    """
    webhook = webhook or os.getenv("PROD_ALERT_WEBHOOK")
    text = format_markdown(alert)
    at_mobiles = _resolve_at_mobiles(at_mobiles)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry = {"timestamp": ts, "target": webhook or "dry-run",
             "message": text, "at_mobiles": at_mobiles}

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
                "logged": logged, "at_mobiles": at_mobiles}
    try:
        resp = requests.post(
            webhook,
            json=_build_payload(text, webhook, at_mobiles),
            timeout=10,
        )
        return {"dispatched": resp.status_code < 400,
                "status_code": resp.status_code, "logged": logged,
                "at_mobiles": at_mobiles}
    except Exception as e:  # 推送失败不应阻断 CI/主流程
        return {"dispatched": False, "reason": str(e), "logged": logged,
                "at_mobiles": at_mobiles}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="L6 告警推送（IM/值班渠道）")
    ap.add_argument("--alert", type=Path, default=DEFAULT_ALERT,
                    help="告警明细文件（默认 prod_alert.json）")
    ap.add_argument("--webhook", type=str, default=None,
                    help="告警 webhook 地址（钉钉/企微/Slack 兼容）；缺省读 env PROD_ALERT_WEBHOOK")
    ap.add_argument("--at-mobiles", dest="at_mobiles", type=str, default=None,
                    help="逗号分隔手机号，告警时 @；缺省取 env PROD_ALERT_AT_MOBILES 或内置默认 18658159309")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅落盘 notify.log 审计，不真正推送")
    args = ap.parse_args()
    at = args.at_mobiles.split(",") if args.at_mobiles else None
    out = dispatch(load_alert(args.alert), webhook=args.webhook,
                   dry_run=args.dry_run, at_mobiles=at)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
