"""L6 生产监控与治理 —— 共享数据类型。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProdSession:
    """一条生产会话的采样记录（由 collector 产出）。"""
    id: str
    question: str = ""
    answer: str = ""
    tool_calls: list = field(default_factory=list)   # 实际尝试调用的工具名
    tool_results: list = field(default_factory=list)  # 工具返回（用于幻觉启发式比对）
    user_id: str = ""
    prompt_version: str = "unknown"                  # 由 sc_ai 留痕（AiChatSession.prompt_version）
    model_used: str = "unknown"                      # 由 sc_ai 留痕（AiChatSession.model_used）
    created_at: str = ""


@dataclass
class ProdSessionResult:
    session_id: str
    safe: bool
    refusal_correct: bool
    hallucinated: bool
    flags: list = field(default_factory=list)         # safety_violation / missed_refusal / false_refusal / hallucination
    reasons: list = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.flags


@dataclass
class ProdAlert:
    level: str          # "critical" | "warning"
    metric: str
    value: float
    threshold: float
    detail: str


@dataclass
class VersionInfo:
    prompt_version: str
    model_used: str
    count: int
