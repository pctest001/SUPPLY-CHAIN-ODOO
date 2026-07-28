"""缺陷闭环层（Defect Closure）—— 发现问题之后的链路。

把监控/CI 抓到的缺陷统一沉淀、去重、走生命周期、挂验证证据，形成
「发现 → 建单 → 分派 → 修复 → 验证关闭」的真正闭环。本地 defects.jsonl 持久化，
外部工单系统作为可插拔 sink。
"""
from .schema import (
    Defect, make_signature, flag_to_category, flag_to_severity,
    can_transition, STATUS_OPEN, STATUS_TRIAGE, STATUS_FIXING,
    STATUS_VERIFYING, STATUS_CLOSED, STATUSES, SEVERITIES,
)
from .registry import DefectRegistry
from .sink import DefectSink, LocalSink, GitHubIssueSink, TapdSink
from .emit import emit_from_sessions, emit_from_ci

__all__ = [
    "Defect", "make_signature", "flag_to_category", "flag_to_severity",
    "can_transition", "STATUS_OPEN", "STATUS_TRIAGE", "STATUS_FIXING",
    "STATUS_VERIFYING", "STATUS_CLOSED", "STATUSES", "SEVERITIES",
    "DefectRegistry", "DefectSink", "LocalSink", "GitHubIssueSink", "TapdSink",
    "emit_from_sessions", "emit_from_ci",
]
