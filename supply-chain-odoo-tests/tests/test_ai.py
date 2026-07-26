"""B5：AI 智能层降级验证（作品说明 G5 全链路降级 / G 组密钥不落地）。

核心断言：无论 LLM 是否配置/可用，调用 ai.chat.session.ask() 都必须『优雅降级、
返回非空文本、绝不抛异常』——主供应链流程不受 AI 可用性影响。这是 AI 安全四原则中
『全链路降级』的端到端证据。
"""
import xmlrpc.client

from src.healer.audit import get_audit


def test_ai_ask_degrades_gracefully(odoo_client):
    """无可用 LLM（测试实例 SUPPLY_AI_API_KEY 为空）时，ask 返回非空降级文本而非崩溃。"""
    audit = get_audit()
    sid = odoo_client.create("ai.chat.session", {})
    try:
        # ask 签名 ask(self, question)，经 XML-RPC 以 [ids], question 形式调用
        answer = odoo_client.execute(
            "ai.chat.session", "ask", [sid], "当前有哪些临期或负库存物料？"
        )
        assert isinstance(answer, str) and answer.strip(), \
            "AI ask 应返回非空降级文本，而非抛异常中断主流程"
        audit.log("data", "info", "case:AI-DEGRADE", f"answer_len={len(answer)}")
    finally:
        try:
            odoo_client.unlink("ai.chat.session", [sid])
        except Exception:  # noqa: BLE001 - 清理失败不影响判定
            pass
