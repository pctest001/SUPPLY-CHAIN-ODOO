"""L6 采集器：把生产会话拉成 ProdSession 列表。

  - MockCollector ：离线回放 prod_fixtures.json（默认健康会话），CI/本地用。
  - RpcCollector  ：经 odoo_client 拉真实 ai.chat.session（需 Odoo + ai.config）。
                     读 model_used / prompt_version 字段（sc_ai 留痕后才有；
                     未升级模块时这两个字段缺失，回退 "unknown"，不报错）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .types import ProdSession


class ProductionCollector:
    def collect(self, since_days: int = 7, limit: int = 200) -> list[ProdSession]:
        raise NotImplementedError


class MockCollector(ProductionCollector):
    def __init__(self, fixtures: list | None = None,
                 fixtures_path: Path | None = None):
        if fixtures is not None:
            self._data = fixtures
        else:
            p = fixtures_path or (Path(__file__).resolve().parent / "prod_fixtures.json")
            self._data = json.loads(p.read_text(encoding="utf-8"))["sessions"]

    def collect(self, since_days: int = 7, limit: int = 200) -> list[ProdSession]:
        sessions = [ProdSession(**d) for d in self._data]
        return sessions[:limit]


class RpcCollector(ProductionCollector):
    """经 XML-RPC 拉取生产 ai.chat.session（黑盒，绝不 import odoo）。"""

    def __init__(self, client, since_days: int = 7, limit: int = 200):
        self.client = client
        self.since_days = since_days
        self.limit = limit

    def collect(self, since_days: int | None = None,
                limit: int | None = None) -> list[ProdSession]:
        since_days = since_days or self.since_days
        limit = limit or self.limit
        since = (datetime.now() - timedelta(days=since_days)).strftime("%Y-%m-%d %H:%M:%S")
        ids = self.client.search(
            "ai.chat.session", [("create_date", ">=", since)],
            limit=limit, order="create_date desc")
        if not ids:
            return []
        rows = self.client.read(
            "ai.chat.session", ids,
            ["message_ids", "model_used", "prompt_version", "user_id", "create_date"])
        # 工具调用日志（sc_ai 已落 ai.chat.tool.log）→ 精确回填 tool_calls/tool_results
        tool_rows = self.client.search_read(
            "ai.chat.tool.log", [("session_id", "in", ids)],
            ["session_id", "tool_name", "tool_result", "status"],
            order="sequence asc") if ids else []
        tools_by_session: dict[str, list] = {}
        for t in tool_rows:
            sid = str(t["session_id"][0] if isinstance(t["session_id"], (list, tuple)) else t["session_id"])
            tools_by_session.setdefault(sid, []).append(t)
        out: list[ProdSession] = []
        for r in rows:
            msg_ids = r.get("message_ids") or []
            msgs = self.client.read(
                "ai.chat.message", msg_ids, ["role", "content", "sequence"]) if msg_ids else []
            question = answer = ""
            for m in sorted(msgs, key=lambda x: x.get("sequence", 0)):
                if m["role"] == "user":
                    question = m["content"]
                elif m["role"] == "assistant":
                    answer = m["content"]
            sid = str(r["id"])
            tlogs = tools_by_session.get(sid, [])
            tool_calls = [t.get("tool_name") for t in tlogs]
            tool_results = []
            for t in tlogs:
                tr = t.get("tool_result") or "{}"
                try:
                    tool_results.append(json.loads(tr))
                except Exception:
                    tool_results.append({})
            out.append(ProdSession(
                id=sid, question=question, answer=answer,
                tool_calls=tool_calls,  # live 模式现已精确（源自 ai.chat.tool.log）
                tool_results=tool_results,
                prompt_version=r.get("prompt_version") or "unknown",
                model_used=r.get("model_used") or "unknown",
                user_id=str(r.get("user_id") or ""),
                created_at=str(r.get("create_date") or ""),
            ))
        return out
