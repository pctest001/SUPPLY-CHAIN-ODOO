"""Odoo XML-RPC 客户端（仅用标准库，无第三方依赖）。

对应被测实例由 docker-compose.test.yml 拉起，默认 http://localhost:18069。
所有交互都是黑盒 RPC，绝不 import odoo、绝不修改 SUT 业务代码。
"""
from __future__ import annotations

import xmlrpc.client


class _TimeoutTransport(xmlrpc.client.Transport):
    """给 XML-RPC 加超时，避免被测实例未就绪时无限阻塞。"""

    def __init__(self, timeout: float = 30.0):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class OdooClient:
    def __init__(
        self,
        url: str = "http://localhost",
        db: str = "test_supplychain",
        username: str = "admin@example.com",
        password: str = "admin",
        port: int = 18069,
        timeout: float = 30.0,
    ):
        self.url = url.rstrip("/")
        self.port = port
        self.db = db
        self.username = username
        self.password = password
        self.uid: int | None = None
        common_url = f"{self.url}:{port}/xmlrpc/2/common"
        object_url = f"{self.url}:{port}/xmlrpc/2/object"
        self.common = xmlrpc.client.ServerProxy(common_url, transport=_TimeoutTransport(timeout), allow_none=True)
        self.models = xmlrpc.client.ServerProxy(object_url, transport=_TimeoutTransport(timeout), allow_none=True)

    # ---- 认证 ----
    def authenticate(self) -> int:
        self.uid = self.common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise ConnectionError(
                f"Odoo 认证失败: db={self.db} login={self.username}。\n"
                f"请先初始化被测实例:\n"
                f"  docker compose -f docker-compose.test.yml run --rm "
                f"odoo odoo -i supply_chain_demo,sc_ai -d {self.db} --stop-after-init\n"
                f"  docker compose -f docker-compose.test.yml up -d odoo"
            )
        return self.uid

    @property
    def authenticated_uid(self) -> int:
        if self.uid is None:
            self.authenticate()
        return self.uid

    # ---- 通用执行 ----
    def execute(self, model: str, method: str, *args, **kwargs):
        return self.models.execute_kw(self.db, self.authenticated_uid, self.password, model, method, args, kwargs)

    # ---- ORM 便捷封装 ----
    def search(self, model, domain, limit=None, offset=0, order=None):
        kw = {}
        if limit is not None:
            kw["limit"] = limit
        if offset:
            kw["offset"] = offset
        if order:
            kw["order"] = order
        return self.execute(model, "search", domain, **kw)

    def search_read(self, model, domain, fields=None, limit=None, offset=0, order=None):
        kw = {}
        if fields is not None:
            kw["fields"] = fields
        if limit is not None:
            kw["limit"] = limit
        if offset:
            kw["offset"] = offset
        if order:
            kw["order"] = order
        return self.execute(model, "search_read", domain, **kw)

    def read(self, model, ids, fields=None):
        kw = {"fields": fields} if fields else {}
        return self.execute(model, "read", ids, **kw)

    def create(self, model, vals):
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        return self.execute(model, "write", ids, vals)

    def unlink(self, model, ids):
        return self.execute(model, "unlink", ids)

    def fields_get(self, model, attributes=None):
        return self.execute(model, "fields_get", attributes or [])

    def model_exists(self, model: str) -> bool:
        try:
            return bool(self.execute("ir.model", "search_count", [("model", "=", model)]))
        except Exception:
            return False
