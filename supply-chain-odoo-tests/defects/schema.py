"""缺陷闭环层 —— 数据模型与状态机。

把「发现问题之后」的链路补上：监控/CI 抓到的问题会话或真实缺陷，
统一沉淀为 defect 记录（按 signature 去重），走 Open→Triage→Fixing→Verifying→Closed
生命周期，关闭必须挂验证证据。本地用 defects.jsonl 持久化，外部工单系统(github/tapd)
作为可插拔 sink，连接器就绪即接。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict

# ---- 状态 ----
STATUS_OPEN = "Open"
STATUS_TRIAGE = "Triage"
STATUS_FIXING = "Fixing"
STATUS_VERIFYING = "Verifying"
STATUS_CLOSED = "Closed"
STATUSES = [STATUS_OPEN, STATUS_TRIAGE, STATUS_FIXING, STATUS_VERIFYING, STATUS_CLOSED]

# 合法状态转移（闭环：Closed 可 reopen 回 Open）
_TRANSITIONS = {
    STATUS_OPEN: {STATUS_TRIAGE, STATUS_FIXING, STATUS_CLOSED},
    STATUS_TRIAGE: {STATUS_FIXING, STATUS_CLOSED, STATUS_OPEN},
    STATUS_FIXING: {STATUS_VERIFYING, STATUS_OPEN},
    STATUS_VERIFYING: {STATUS_CLOSED, STATUS_FIXING},
    STATUS_CLOSED: {STATUS_OPEN},
}

# ---- 严重度 ----
SEVERITIES = ["critical", "high", "medium", "low"]
_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}  # critical=0 最高

# L6 flag -> 缺陷类别/严重度
_CATEGORY_BY_FLAG = {
    "safety_violation": "safety",
    "missed_refusal": "refusal",
    "false_refusal": "refusal",
    "hallucination": "hallucination",
}


@dataclass
class Defect:
    id: str = ""
    source: str = ""                 # prod_monitor | ci_gate | manual
    signature: str = ""              # 去重键 = hash(source|key)
    title: str = ""
    severity: str = "medium"         # critical/high/medium/low
    category: str = "other"          # safety/hallucination/refusal/mutation/behavior_fence/ui/rpc/other
    status: str = STATUS_OPEN
    evidence: dict = field(default_factory=dict)   # 指向 session/run/test/flags 等溯源信息
    owner: str = ""
    fix_ref: str = ""                # 修复 commit/PR 引用
    verified_by: str = ""            # 关闭时的验证证据（用例/重放/基线回升）
    occurrences: int = 1             # 同一缺陷被发现的次数（去重累计）
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Defect":
        return cls(**{k: d.get(k, "") if k in ("id", "source", "signature", "title",
                   "severity", "category", "status", "owner", "fix_ref",
                   "verified_by", "created_at", "updated_at") else
                   (d.get(k, 0) if k == "occurrences" else d.get(k, {} if k == "evidence" else ""))
                   for k in ("id", "source", "signature", "title", "severity",
                             "category", "status", "evidence", "owner", "fix_ref",
                             "verified_by", "occurrences", "created_at", "updated_at")})


def make_signature(source: str, key: str) -> str:
    return hashlib.sha1(f"{source}|{key}".encode("utf-8")).hexdigest()[:16]


def flag_to_category(flags: list) -> str:
    for f in ("safety_violation", "missed_refusal", "false_refusal", "hallucination"):
        if f in flags:
            return _CATEGORY_BY_FLAG[f]
    return "other"


def flag_to_severity(flags: list) -> str:
    if "safety_violation" in flags:
        return "critical"
    if "missed_refusal" in flags:
        return "high"
    if "hallucination" in flags:
        return "high"
    if "false_refusal" in flags:
        return "medium"
    return "medium"


def severity_rank(sev: str) -> int:
    return _SEV_RANK.get(sev, len(SEVERITIES))


def can_transition(frm: str, to: str) -> bool:
    return to in _TRANSITIONS.get(frm, set())
