"""ai_models.py 非降级路径补测：宿主机 mock LLM + Function Calling 全链路。

原覆盖率 48.8% 只走了降级分支。本文件用「宿主机起 OpenAI 兼容 mock server，
容器内 Odoo 经 host.docker.internal 回连」的方式黑盒驱动：
  - _call_llm 成功路径 + tool_calls 二段式对话；
  - 6 个白名单工具全部被 LLM 调用一遍（_tool_query_*）；
  - 白名单外调用（模拟提示词注入）被拒绝、坏参数工具调用被兜住；
  - ask() 成功落消息、chat/get_or_create_session/new_session 侧边面板接口；
  - interpret_alerts / suggest_replenishment 的『有配置』路径。

Key 安全红线不破：API Key 仍从环境变量读取——mock 配置把 api_key_env 指到
容器内必然存在的 PATH，Key 内容对 mock server 无意义。
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.ai

MOCK_PORT = 18899
MOCK_ANSWER = "MOCK_LLM_FINAL_ANSWER_OK"
_TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# LLM 第一轮返回的工具调用：6 个白名单工具 + 1 个注入 + 1 个坏参数
_TOOL_CALLS = [
    {"id": "c1", "type": "function",
     "function": {"name": "query_stock", "arguments": json.dumps({"limit": 5})}},
    {"id": "c2", "type": "function",
     "function": {"name": "query_purchase_orders", "arguments": json.dumps({"limit": 5})}},
    {"id": "c3", "type": "function",
     "function": {"name": "query_suppliers", "arguments": json.dumps({"limit": 5})}},
    {"id": "c4", "type": "function",
     "function": {"name": "query_expiring_lots", "arguments": json.dumps({"days": 30})}},
    {"id": "c5", "type": "function",
     "function": {"name": "query_low_stock", "arguments": "{}"}},
    {"id": "c6", "type": "function",
     "function": {"name": "query_supplier_acks", "arguments": "{}"}},
    # [Unwanted] 白名单外（模拟提示词注入）→ 应被拒绝而非执行
    {"id": "c7", "type": "function",
     "function": {"name": "drop_database", "arguments": "{}"}},
    # [Unwanted] 白名单内但参数非法 → 工具执行失败应被兜住
    {"id": "c8", "type": "function",
     "function": {"name": "query_stock", "arguments": json.dumps({"limit": "abc"})}},
]


class _MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"pong")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        has_tool_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        wants_tools = bool(body.get("tools"))
        if wants_tools and not has_tool_result:
            # 第一轮：要求调用全部工具
            msg = {"role": "assistant", "content": "", "tool_calls": _TOOL_CALLS}
        else:
            # 第二轮（或无工具场景）：直接给出最终回答
            msg = {"role": "assistant", "content": MOCK_ANSWER}
        payload = json.dumps({"choices": [{"message": msg}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _container_can_reach_host() -> bool:
    """容器内探测 host.docker.internal 可达性（不可达则 skip 而非误报失败）。"""
    cmd = ["docker", "compose", "-f", "docker-compose.test.yml", "exec", "-T", "odoo",
           "python3", "-c",
           f"import urllib.request; urllib.request.urlopen('http://host.docker.internal:{MOCK_PORT}/ping', timeout=5); print('ok')"]
    try:
        r = subprocess.run(cmd, cwd=_TESTS_DIR, capture_output=True, timeout=30)
        return b"ok" in r.stdout
    except Exception:
        return False


@pytest.fixture(scope="module")
def mock_llm(odoo_client, healed_env):
    """起 mock server + 切换 ai.config 到 mock；结束后恢复原配置。"""
    server = ThreadingHTTPServer(("", MOCK_PORT), _MockLLMHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    if not _container_can_reach_host():
        server.shutdown()
        pytest.skip("容器无法访问宿主 mock server（host.docker.internal 不可达）")

    prev_active = odoo_client.search("ai.config", [("active", "=", True)])
    if prev_active:
        odoo_client.write("ai.config", prev_active, {"active": False})
    cfg_id = odoo_client.create("ai.config", {
        "name": "__mock_llm_cfg",
        "provider": "custom",
        "base_url": f"http://host.docker.internal:{MOCK_PORT}/v1",
        "model": "mock-1",
        # Key 仍走环境变量红线：指向容器内必存在的 PATH（内容无意义）
        "api_key_env": "PATH",
        "timeout": 15,
        "active": True,
    })
    yield cfg_id
    odoo_client.unlink("ai.config", [cfg_id])
    if prev_active:
        odoo_client.write("ai.config", prev_active, {"active": True})
    server.shutdown()


def _new_session(client):
    return client.create("ai.chat.session", {})


def test_ask_function_calling_full_chain(odoo_client, healed_env, mock_llm):
    """ask()：两轮 LLM + 8 个工具调用（含注入拒绝/坏参数兜底）后返回最终回答。"""
    sid = _new_session(odoo_client)
    answer = odoo_client.execute("ai.chat.session", "ask", [sid], "现在库存和采购情况怎么样？")
    assert MOCK_ANSWER in answer, f"未走通非降级路径: {answer!r}"
    assert "暂不可用" not in answer and "降级" not in answer
    msgs = odoo_client.execute("ai.chat.session", "get_messages", [sid])
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant"], f"对话记录异常: {roles}"
    assert msgs[1]["content"] == answer


def test_chat_panel_api(odoo_client, healed_env, mock_llm):
    """chat()（OWL 侧边面板）：传入已有会话，返回 id/answer/messages。"""
    sid = _new_session(odoo_client)
    result = odoo_client.execute("ai.chat.session", "chat", sid, "查一下负库存")
    assert result["id"] == sid
    assert MOCK_ANSWER in result["answer"]
    assert len(result["messages"]) == 2


def test_chat_blank_question_shortcircuit(odoo_client, healed_env, mock_llm):
    """chat() 空问题：不落消息、直接短路返回。"""
    result = odoo_client.execute("ai.chat.session", "chat", 0, "   ")
    assert result["answer"] == "" and result["messages"] == []


def test_session_panel_lifecycle(odoo_client, healed_env, mock_llm):
    """new_session / get_or_create_session：侧边面板会话生命周期。"""
    ns = odoo_client.execute("ai.chat.session", "new_session")
    assert ns["id"] and ns["messages"] == []
    got = odoo_client.execute("ai.chat.session", "get_or_create_session")
    assert got["id"], "get_or_create_session 未返回会话"


def test_interpret_alerts_with_llm(odoo_client, healed_env, mock_llm):
    """interpret_alerts()：有配置时走 LLM（tools=[] 直答路径）。"""
    sid = _new_session(odoo_client)
    out = odoo_client.execute("ai.chat.session", "interpret_alerts", [sid])
    assert MOCK_ANSWER in out, f"预警解读未走 LLM 路径: {out!r}"


def test_suggest_replenishment_with_llm(odoo_client, healed_env, mock_llm):
    """suggest_replenishment()：有配置时走 LLM。"""
    sid = _new_session(odoo_client)
    out = odoo_client.execute("ai.chat.session", "suggest_replenishment", [sid])
    assert MOCK_ANSWER in out, f"补货建议未走 LLM 路径: {out!r}"
