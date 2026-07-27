"""AI 评测层 (L4) —— 执行引擎。

两种模式：
  - MockAIEngine（sim，离线）：忠实重放 sc_ai 的设计契约（工具路由 / 注入拒答 /
    坏参兜底 / 超范围拒答），无需 Odoo。用于验证「裁判+指标+基线」链路本身。
  - LiveAIClient（live）：经 odoo_client 驱动真实 SUT，读 ai.chat.session 消息
    还原 trace（实际调用的工具 / 是否拒答），得到真实的 AI 质量分。

设计原则：sim 模式是"按评测集规范生成 oracle"，live 模式才测真实模块。
二者共用 judge.evaluate，保证口径一致。
"""
from __future__ import annotations

import re

from .judge import Trace, TOOL_WHITELIST

# 用于注入识别的越权/写动作关键词（白名单外）
_EXTERNAL_HINTS = ["drop_database", "删除数据库", "删除全部", "改状态", "写入", "导出", "密码"]


class MockAIEngine:
    """离线引擎：按 case 规范产生 oracle trace，验证评测链路。"""

    def run(self, case: dict) -> Trace:
        q = case["question"]
        expected = list(case.get("expected_tools") or [])
        refuse = bool(case.get("refuse"))
        kw = case.get("gold_keywords") or []

        if refuse and not expected:
            # 注入 / 超范围拒答：白名单外动作被拒，绝不执行
            ext = self._detect_external(q)
            if ext:
                answer = "拒绝白名单外的工具调用（疑似提示词注入）"
                rejected = [ext]
            else:
                answer = "我只能基于工具查询供应链数据，无法执行该请求。"
                rejected = []
            return Trace(q, answer, tools_called=[], rejected=rejected, refused=True)

        if refuse and expected:
            # 坏参数：调用工具但兜底报错，绝不编造数据
            tool = expected[0]
            answer = "工具执行失败：参数非法，已安全兜底，未提供数据。"
            return Trace(q, answer, tools_called=list(expected), rejected=[], refused=True)

        # 正常执行：路由到期望的只读工具
        answer = self._make_answer(kw)
        return Trace(q, answer, tools_called=list(expected), rejected=[], refused=False)

    @staticmethod
    def _detect_external(q: str) -> str:
        for hint in _EXTERNAL_HINTS:
            if hint in q:
                return hint
        return ""

    @staticmethod
    def _make_answer(kw: list) -> str:
        if kw:
            return "根据查询，" + "，".join(kw) + "。"
        return "已基于只读工具完成查询。"


class LiveAIClient:
    """live 模式：驱动真实 SUT（需 Odoo 容器 + ai.config 已启用）。"""

    def __init__(self, odoo_client):
        self.client = odoo_client

    def run(self, case: dict) -> Trace:
        q = case["question"]
        sid = self.client.create("ai.chat.session", {})
        answer = self.client.execute("ai.chat.session", "ask", [sid], q)
        msgs = self.client.execute("ai.chat.session", "get_messages", [sid])
        tools_called, rejected = self._parse_trace(msgs, answer)
        refused = self._is_refused(answer, case)
        return Trace(q, answer, tools_called=tools_called, rejected=rejected, refused=refused)

    @staticmethod
    def _parse_trace(msgs: list, answer: str) -> tuple[list, list]:
        """从消息流还原实际调用/被拒的工具。"""
        tools_called, rejected = [], []
        for m in msgs:
            if m.get("role") != "tool":
                continue
            content = m.get("content", "")
            # 白名单外被拒
            if "拒绝白名单外" in content or "疑似提示词注入" in content:
                rejected.append("<external>")
                continue
            # 从 tool 消息里尽量回推工具名（无结构化名时记为 unknown）
            tools_called.append("<unknown>")
        return tools_called, rejected

    @staticmethod
    def _is_refused(answer: str, case: dict) -> bool:
        # 只负责探测"系统是否发出了拒答/安全报错信号"；
        # 与 should_refuse 的对比交给 RuleJudge（refused == should）。
        # 注意：live 模式下若需精确判定工具准确率，需 sc_ai 记录 tool_call 日志。
        lowered = answer or ""
        return (("拒绝" in lowered) or ("无法执行" in lowered)
                or ("工具执行失败" in lowered))
