"""L6 prompt/模型版本化留痕（治理侧）。

统计采样会话的 prompt_version × model_used 分布，快照 prompt 版本注册表，
支持版本 diff。注册表需与 sc_ai 的 PROMPT_VERSION / PROMPT_REGISTRY 保持同步——
它是"线上到底跑了哪版 prompt/模型"的治理视图。
"""
from __future__ import annotations

from collections import Counter

from .types import VersionInfo

# prompt 版本注册表（治理侧快照，应随 sc_ai 升级同步）
PROMPT_REGISTRY = {
    "v1": ("你是供应链智能助手，服务于基于 Odoo 的流程制造供应链系统。"
           "你只能通过给定的工具函数查询数据，不得擅自编造数据或执行写操作。"
           "回答要简洁、面向业务（管理者/仓管/采购），给出可操作建议。"
           "所有数据查询均继承用户权限，禁止越权。"),
}


def analyze_versions(sessions: list) -> dict:
    """统计采样会话的 (prompt_version, model_used) 分布。"""
    c = Counter((s.prompt_version or "unknown", s.model_used or "unknown")
                for s in sessions)
    dist = [VersionInfo(pv, m, n) for (pv, m), n in c.items()]
    return {
        "total_sampled": len(sessions),
        "distribution": [
            {"prompt_version": d.prompt_version, "model_used": d.model_used,
             "count": d.count} for d in dist
        ],
    }


def diff_prompt(v1: str, v2: str) -> dict:
    """对比两个 prompt 版本的文本（治理审计用）。"""
    return {
        "v1": PROMPT_REGISTRY.get(v1, f"<{v1} 未登记>"),
        "v2": PROMPT_REGISTRY.get(v2, f"<{v2} 未登记>"),
        "registered": [v for v in (v1, v2) if v in PROMPT_REGISTRY],
    }


def current_prompt_version() -> str:
    """当前活跃 prompt 版本（与 sc_ai.PROMPT_VERSION 对齐）。"""
    return "v1"
