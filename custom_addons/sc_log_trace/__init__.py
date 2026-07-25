# -*- coding: utf-8 -*-
"""SC Log Trace —— 为每个 Web 请求注入 trace id 到日志。

做法���最小侵入的 monkey-patch，无需改 Odoo 核心代码）：
1. 给 Odoo 的 ColoredFormatter / DBFormatter 的 format 包一层：在每条日志
   message 前加 `[trace_id]` 前缀。trace id 存在 threading.local，非请求
   线程为 '-'。
2. 给 odoo.http.Request.__init__ 包一层：每次 Web 请求开始生成一个 8 位
   UUID 写入 threading.local，请求期间该线程打印的所有日志共享同一 ID。

注意：
- 仅 Web 请求（页面/JSON-RPC/HTTP）带 trace id；Cron、后台任务等非 Web
  请求线程没有，显示为 '-'（符合预期，它们本就不属于某次用户请求）。
- 多 worker / 多线程下 threading.local 天然隔离并发请求。
- 适配 Odoo 18：formatter 在 odoo.netsvc，web 请求基类是 odoo.http.Request
  （旧版名为 WebRequest，18 已更名）。
"""

import logging
import threading
import uuid

_logger = logging.getLogger(__name__)

_local = threading.local()


# ---------------------------------------------------------------------------
# 1) 日志 formatter 注入 trace id 前缀
#    Odoo 18 的 formatter 在 odoo.netsvc：ColoredFormatter -> DBFormatter
# ---------------------------------------------------------------------------
try:
    from odoo.netsvc import ColoredFormatter, DBFormatter

    def _make_trace_format(orig_format):
        def _fmt(self, record):
            tid = getattr(_local, "trace_id", None) or "-"
            saved = record.msg
            try:
                record.msg = "[%s] %s" % (tid, saved)
                return orig_format(self, record)
            finally:
                record.msg = saved
        return _fmt

    ColoredFormatter.format = _make_trace_format(ColoredFormatter.format)
    DBFormatter.format = _make_trace_format(DBFormatter.format)
    _logger.info("sc_log_trace: formatter patched (trace id enabled)")
except Exception as e:
    _logger.warning("sc_log_trace: failed to patch formatter: %s", e)


# ---------------------------------------------------------------------------
# 2) 每个 Web 请求生成 trace id
#    Odoo 18 的 web 请求基类是 odoo.http.Request（旧版 WebRequest）
# ---------------------------------------------------------------------------
try:
    import odoo.http

    _orig_request_init = odoo.http.Request.__init__

    def _patched_request_init(self, *args, **kwargs):
        _local.trace_id = uuid.uuid4().hex[:8]
        return _orig_request_init(self, *args, **kwargs)

    odoo.http.Request.__init__ = _patched_request_init
    _logger.info("sc_log_trace: Request patched (per-request trace id)")
except Exception as e:
    _logger.warning("sc_log_trace: failed to patch Request: %s", e)


# ---------------------------------------------------------------------------
# 3) 让 JSON 错误响应也带 trace id（便于前端报错时直接关联到日志）
#    Odoo 18 的错误 data 由 odoo.http.serialize_exception 构造
# ---------------------------------------------------------------------------
try:
    import odoo.http
    _orig_serialize = odoo.http.serialize_exception

    def _patched_serialize(exception):
        data = _orig_serialize(exception)
        tid = getattr(_local, "trace_id", None) or "-"
        if isinstance(data, dict):
            data["trace_id"] = tid
        return data

    odoo.http.serialize_exception = _patched_serialize
    _logger.info("sc_log_trace: serialize_exception patched (error JSON carries trace id)")
except Exception as e:
    _logger.warning("sc_log_trace: failed to patch serialize_exception: %s", e)
