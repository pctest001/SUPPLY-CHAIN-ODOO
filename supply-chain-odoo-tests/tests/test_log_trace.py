"""sc_log_trace 补测：请求级 trace id 注入（原 0% 覆盖 -> 模块被受控安装并验证）。

黑盒验证点：
  - 模块确实安装（uninstalled 是此前 0% 覆盖的根因）；
  - JSON-RPC 错误响应 data 携带 trace_id（serialize_exception patch）；
  - 不同请求 trace_id 不同（Request.__init__ patch，每请求一发）。
formatter patch 属日志输出层，无法黑盒断言内容，由错误响应路径间接覆盖。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import pytest

pytestmark = pytest.mark.logtrace

URL = os.getenv("ODOO_URL", "http://localhost")
PORT = int(os.getenv("ODOO_PORT", "18069"))
DB = os.getenv("ODOO_DB", "test_supplychain")
ADMIN_PASSWORD = os.getenv("ODOO_ADMIN_PASSWORD", "admin")

TRACE_RE = re.compile(r"^[0-9a-f]{8}$")


def _jsonrpc_error(uid: int) -> dict:
    """发一个必然报错的 JSON-RPC 调用（模型不存在），返回 error dict。"""
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "id": 1,
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [DB, uid, ADMIN_PASSWORD, "no.such.model", "search", [[]]],
        },
    }
    req = urllib.request.Request(
        f"{URL}:{PORT}/jsonrpc",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    assert "error" in body, f"预期报错却成功了: {body}"
    return body["error"]


def test_module_installed(odoo_client, healed_env):
    """sc_log_trace 必须处于 installed（0% 覆盖的根因就是没装）。"""
    rows = odoo_client.search_read(
        "ir.module.module", [("name", "=", "sc_log_trace")], fields=["state"])
    assert rows and rows[0]["state"] == "installed", f"sc_log_trace 未安装: {rows}"


def test_error_response_carries_trace_id(odoo_client, healed_env):
    """JSON-RPC 错误响应 data.trace_id 为 8 位 hex（serialize_exception patch）。"""
    err = _jsonrpc_error(odoo_client.uid)
    data = err.get("data") or {}
    tid = data.get("trace_id")
    assert tid, f"错误响应缺 trace_id: {err}"
    assert TRACE_RE.match(str(tid)), f"trace_id 格式应为 8 位 hex: {tid!r}"


def test_trace_id_unique_per_request(odoo_client, healed_env):
    """两次请求的 trace_id 不同（每个 Web 请求独立生成）。"""
    t1 = (_jsonrpc_error(odoo_client.uid).get("data") or {}).get("trace_id")
    t2 = (_jsonrpc_error(odoo_client.uid).get("data") or {}).get("trace_id")
    assert t1 and t2 and t1 != t2, f"trace_id 未按请求隔离: {t1} vs {t2}"
