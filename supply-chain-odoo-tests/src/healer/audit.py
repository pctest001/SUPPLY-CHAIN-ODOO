"""自愈审计：所有自愈动作必须留痕，便于事后区分『环境修复』与『真实回归』。

设计红线（见技术方案 v2.1 P0#2）：
- 自愈动作全量写审计，包含层级(env/data/config)、级别(info/heal/fail)、动作、详情。
- 自愈只发生在用例执行之前的环境准备阶段，绝不捕获用例断言失败去自愈。
- 用例执行后若失败，一律交给 pytest 判定，绝不掩盖真实回归。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import List

AUDIT_PATH = os.environ.get("ODOO_TEST_AUDIT", "healer_audit.jsonl")


@dataclass
class AuditEntry:
    ts: str
    layer: str          # env / data / config
    level: str          # info / heal / fail
    action: str
    detail: str = ""


class AuditLog:
    def __init__(self, path: str = AUDIT_PATH):
        self.path = path
        self.entries: List[AuditEntry] = []

    def log(self, layer: str, level: str, action: str, detail: str = "") -> AuditEntry:
        e = AuditEntry(time.strftime("%Y-%m-%dT%H:%M:%S"), layer, level, action, detail)
        self.entries.append(e)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
        except OSError:
            pass
        return e

    def count_heals(self) -> int:
        return sum(1 for e in self.entries if e.level == "heal")

    def reset(self) -> None:
        self.entries.clear()
        try:
            open(self.path, "w", encoding="utf-8").close()
        except OSError:
            pass


_AUDIT = AuditLog()


def get_audit() -> AuditLog:
    return _AUDIT
