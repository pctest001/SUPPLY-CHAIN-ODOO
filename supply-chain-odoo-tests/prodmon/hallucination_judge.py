"""L6 幻觉裁判（可插拔）。

两类实现，均产出 (hallucinated: bool, reason: str)：
  - HeuristicHallucinationJudge：离线启发式哨兵（默认）。回答里的数量断言
    若未在工具结果中出现即判幻觉；无需外部依赖，可在 CI/sim 离线运行。
  - LLMHallucinationJudge      ：LLM-as-Judge，复用 DeepSeek（SUPPLY_AI_API_KEY，
    端点 https://api.deepseek.com/v1/chat/completions，模型 deepseek-chat）按 rubric
    判定回答是否得到工具数据支撑。调用失败（无 key / 网络 / 解析错误）一律降级回
    启发式——绝不伪造判定、绝不阻断监控。

get_hallucination_judge()：仅当环境变量 PROD_LLM_JUDGE 为真且 SUPPLY_AI_API_KEY
存在时启用 LLM 路径；否则默认启发式——保证 run_monitor --mode sim 离线可用。
"""
from __future__ import annotations

import json
import os
import re
from typing import Tuple

try:
    import requests
except Exception:  # 离线/最小化环境可能没有 requests
    requests = None

# 数量断言：回答里"共 N 项/个/条/批/种/笔"
COUNT_RE = re.compile(r"(?:共\s*)?(\d+)\s*(?:项|个|条|批|种|笔)")

DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
# 工具返回数据截断长度，避免超 token（约 4k 字符足够判据）
MAX_RESULTS_CHARS = 4000

SYSTEM_PROMPT = (
    "你是供应链 AI 生产监控的幻觉裁判。给定用户问题、AI 回答、以及 AI 调用工具返回的"
    "真实数据，请判断回答是否包含幻觉——即断言了工具返回数据无法支持的事实"
    "（如虚构的数量、不存在的订单/供应商、错误的状态或时间）。"
    "仅依据「工具返回的真实数据」判断，不要凭空猜测，也不要因为措辞不完美就判幻觉。"
    "返回严格 JSON：{\"hallucinated\": true 或 false, \"reason\": \"一句话理由\"}。"
)


def _count_heuristic(answer: str, results_text: str) -> Tuple[bool, str]:
    """原启发式：回答中的数量断言若未在工具结果文本出现，判疑似幻觉。"""
    claims = COUNT_RE.findall(answer or "")
    for c in claims:
        if c not in results_text:
            return True, f"回答断言数量 {c} 未在工具结果中出现（疑似幻觉）"
    return False, ""


class HallucinationJudge:
    def judge(self, session) -> Tuple[bool, str]:
        raise NotImplementedError


class HeuristicHallucinationJudge(HallucinationJudge):
    """离线启发式哨兵（默认）。仅在能拿到工具结果时判断。"""

    def judge(self, session) -> Tuple[bool, str]:
        if not session.tool_results:
            return False, ""
        results_text = json.dumps(session.tool_results, ensure_ascii=False)
        return _count_heuristic(session.answer, results_text)


class LLMHallucinationJudge(HallucinationJudge):
    """LLM-as-Judge（DeepSeek）。任何失败都降级回启发式，不阻断监控、不伪造。"""

    def __init__(self, fallback: HallucinationJudge | None = None,
                 api_key: str | None = None, endpoint: str = DEEPSEEK_ENDPOINT,
                 model: str = DEEPSEEK_MODEL):
        # 构造宽容：缺失 requests / key 不报错，留到 judge() 调用时再判并降级。
        self.api_key = api_key or os.getenv("SUPPLY_AI_API_KEY") or ""
        self.endpoint = endpoint
        self.model = model
        self._requests = requests
        self._fallback = fallback or HeuristicHallucinationJudge()

    def _call(self, question: str, answer: str, results_text: str) -> dict:
        if self._requests is None:
            raise RuntimeError("requests 不可用，LLM 幻觉裁判跳过（将降级启发式）")
        if not self.api_key:
            raise RuntimeError("未配置 SUPPLY_AI_API_KEY，LLM 幻觉裁判跳过（将降级启发式）")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"用户问题：\n{question}\n\n"
                    f"AI 回答：\n{answer}\n\n"
                    f"工具返回的真实数据：\n{results_text}\n"
                )},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {"Authorization": "Bearer " + self.api_key,
                   "Content-Type": "application/json"}
        resp = requests.post(self.endpoint, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"])

    def judge(self, session) -> Tuple[bool, str]:
        # 无工具结果时 LLM 也无据可依，直接交启发式（同样返回 False）
        if not session.tool_results:
            return False, ""
        results_text = json.dumps(session.tool_results, ensure_ascii=False)
        if len(results_text) > MAX_RESULTS_CHARS:
            results_text = results_text[:MAX_RESULTS_CHARS] + "\n…(已截断)"
        try:
            out = self._call(session.question, session.answer, results_text)
            hal = bool(out.get("hallucinated"))
            reason = str(out.get("reason", "")) or ("LLM 裁判判为幻觉" if hal else "")
            if hal:
                reason = "[LLM-Judge] " + reason
            return hal, reason
        except Exception:
            # 任何失败（网络/解析/限流/超时）→ 降级启发式，不阻断、不伪造
            h, r = self._fallback.judge(session)
            if h:
                r = "[LLM失败→启发式] " + r
            return h, r


def get_hallucination_judge() -> HallucinationJudge:
    """默认启发式（离线）；PROD_LLM_JUDGE 且 SUPPLY_AI_API_KEY 存在且 requests 可用时启用 LLM 路径。"""
    llm_enabled = os.getenv("PROD_LLM_JUDGE", "").lower() in ("1", "true", "yes", "on")
    has_key = bool(os.getenv("SUPPLY_AI_API_KEY"))
    if llm_enabled and has_key and requests is not None:
        try:
            return LLMHallucinationJudge()
        except Exception:
            return HeuristicHallucinationJudge()
    return HeuristicHallucinationJudge()
