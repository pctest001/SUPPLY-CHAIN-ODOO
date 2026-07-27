"""声明式场景执行引擎（支柱一·行为围栏）。

职责：读入场景 JSON -> 逐步执行 -> 采集观察点 -> 输出 raw capture。
归一化（时间戳/自增 id/UUID 清洗）在 P1 的 normalize.py 做，本模块只存原始值。

设计红线：
1. 场景绝不写死期望值——围栏只观察不断言，判定交给 diff(base vs head)。
2. 记录引用一律符号化（$ctx.* / $ref.*），不出现裸 id：双实例 id 不同。
3. $uniq 由共享 run_id 派生：同一次运行内 base/head 对同一 token 生成相同
   业务名（跨实例可对齐），不同次运行不冲突（可重复执行）。
4. 观察三类输出：
   - API：observe_action（方法返回值）/ observe_fault（守卫报错文本）
   - DB 快照：observe_records（read/search_read）
   - 报表数字：observe_count / observe_sum（聚合数值）
"""
from __future__ import annotations

import time
import xmlrpc.client
from datetime import date, timedelta


class ScenarioError(Exception):
    """场景定义或执行错误（区别于被测系统守卫抛错）。"""


# ---------------------------------------------------------------------------
# 符号解析
# ---------------------------------------------------------------------------
def _resolve(value, scope):
    """递归解析 $ctx.* / $ref.* / $uniq:* / $date:* 符号。"""
    if isinstance(value, str):
        if value.startswith("$ctx."):
            key = value[5:]
            if key not in scope["ctx"] or scope["ctx"][key] is None:
                raise ScenarioError(f"上下文缺少符号: {key}")
            return scope["ctx"][key]
        if value.startswith("$ref."):
            cur = scope["refs"]
            for seg in value[5:].split("."):
                if isinstance(cur, dict):
                    if seg not in cur:
                        raise ScenarioError(f"引用不存在: {value}")
                    cur = cur[seg]
                elif isinstance(cur, (list, tuple)):
                    cur = cur[int(seg)]
                else:
                    raise ScenarioError(f"引用路径无法下钻: {value}")
            return cur
        if value.startswith("$uniq:"):
            cache = scope["uniq"]
            if value not in cache:
                cache[value] = f"{value[6:]}-{scope['run_id']}-{len(cache)}"
            return cache[value]
        if value.startswith("$date:"):
            return (date.today() + timedelta(days=int(value[6:]))).isoformat()
        return value
    if isinstance(value, list):
        return [_resolve(v, scope) for v in value]
    if isinstance(value, dict):
        return {k: _resolve(v, scope) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# RPC 辅助（与 tests/ 中 _call_action / _fault_of 口径一致）
# ---------------------------------------------------------------------------
def _call_tolerant(client, model, method, ids, kwargs=None):
    """调用 action，容忍 Odoo 返回 None 导致的 XML-RPC 序列化噪声。"""
    try:
        return client.execute(model, method, ids, **(kwargs or {}))
    except xmlrpc.client.Fault as f:
        if "cannot marshal None" in str(f):
            return None
        raise


def _fault_text(fn):
    """执行 fn，捕获守卫抛错返回消息文本；正常执行返回 None。"""
    try:
        fn()
    except xmlrpc.client.Fault as f:
        if "cannot marshal None" in str(f):
            return None  # action 正常执行只是返回 None，不算守卫命中
        return str(f)
    except Exception as e:  # noqa: BLE001 - 观察点就是要抓异常文本
        return str(e)
    return None


# ---------------------------------------------------------------------------
# 领域宏（复用 tests/test_receipt_lot.py 的编排逻辑）
# ---------------------------------------------------------------------------
def _product_of_tmpl(client, tmpl_id):
    rows = client.search_read(
        "product.product", [("product_tmpl_id", "=", tmpl_id)], fields=["id", "uom_id"]
    )
    if not rows:
        raise ScenarioError(f"模板 {tmpl_id} 没有变体")
    uom = rows[0]["uom_id"]
    return rows[0]["id"], (uom[0] if isinstance(uom, (list, tuple)) else uom)


def _macro_make_product(client, scope, step, process_mfg):
    name = _resolve(step.get("name", "$uniq:FPROD"), scope)
    vals = {"name": name}
    if process_mfg:
        vals["is_process_mfg"] = True
    else:
        vals["is_storable"] = True
    tmpl = client.create("product.template", vals)
    prod, uom = _product_of_tmpl(client, tmpl)
    return {"tmpl": tmpl, "product": prod, "uom": uom}


def _macro_make_picking(client, scope, step):
    ctx = scope["ctx"]
    direction = step["direction"]
    product_id = _resolve(step["product"], scope)
    uom_id = _resolve(step["uom"], scope)
    qty = _resolve(step["qty"], scope)
    if direction == "in":
        type_id, src, dst = ctx["in_type"], ctx["supplier_loc"], ctx["stock_loc"]
    else:
        type_id, src, dst = ctx["out_type"], ctx["stock_loc"], ctx["customer_loc"]
    pid = client.create("stock.picking", {
        "picking_type_id": type_id,
        "location_id": src,
        "location_dest_id": dst,
        "move_ids": [(0, 0, {
            "name": f"fence move {product_id}",
            "product_id": product_id,
            "product_uom_qty": qty,
            "product_uom": uom_id,
            "location_id": src,
            "location_dest_id": dst,
        })],
    })
    client.execute("stock.picking", "action_confirm", [pid])
    move = client.search("stock.move", [("picking_id", "=", pid)], limit=1)
    return {"picking": pid, "move": move[0]}


def _macro_force_line(client, scope, step):
    pid = _resolve(step["picking"], scope)
    move_id = _resolve(step["move"], scope)
    vals = _resolve(step["vals"], scope)
    picking = client.read("stock.picking", [pid], fields=["move_line_ids"])[0]
    line_ids = picking["move_line_ids"]
    if line_ids:
        client.write("stock.move.line", [line_ids[0]], vals)
        if len(line_ids) > 1:
            client.unlink("stock.move.line", line_ids[1:])
        return line_ids[0]
    move = client.read("stock.move", [move_id],
                       fields=["location_id", "location_dest_id", "product_id", "product_uom"])[0]
    base = {
        "move_id": move_id,
        "picking_id": pid,
        "product_id": move["product_id"][0],
        "product_uom_id": move["product_uom"][0],
        "location_id": move["location_id"][0],
        "location_dest_id": move["location_dest_id"][0],
    }
    base.update(vals)
    return client.create("stock.move.line", base)


def _macro_receive(client, scope, step):
    """完整收货编排：建收货 -> 录批次效期 -> 验证 -> 返回 lot id。"""
    made = _macro_make_picking(client, scope, {
        "direction": "in",
        "product": step["product"], "uom": step["uom"], "qty": step["qty"],
    })
    lot_name = _resolve(step["lot_name"], scope)
    exp = _resolve(step["exp"], scope)
    qty = _resolve(step["qty"], scope)
    _macro_force_line(client, scope, {
        "picking": made["picking"], "move": made["move"],
        "vals": {"quantity": qty, "lot_name": lot_name,
                 "expiration_date": exp + " 12:00:00"},
    })
    _call_tolerant(client, "stock.picking", "button_validate", [made["picking"]])
    product_id = _resolve(step["product"], scope)
    lots = client.search("stock.lot",
                         [("name", "=", lot_name), ("product_id", "=", product_id)])
    if not lots:
        raise ScenarioError(f"收货验证后未生成批次 {lot_name}")
    return {"lot": lots[0], "picking": made["picking"], "lot_name": lot_name}


# ---------------------------------------------------------------------------
# 步骤分发
# ---------------------------------------------------------------------------
def _exec_step(client, scope, step):
    op = step["op"]
    r = lambda key: _resolve(step[key], scope)  # noqa: E731

    if op == "create":
        return client.create(step["model"], r("vals"))
    if op == "write":
        return client.write(step["model"], r("ids"), r("vals"))
    if op == "unlink":
        return client.unlink(step["model"], r("ids"))
    if op == "search":
        rows = client.search(step["model"], r("domain"), limit=step.get("limit"))
        if step.get("first"):
            if not rows:
                raise ScenarioError(f"search 无结果: {step['model']} {step['domain']}")
            return rows[0]
        return rows
    if op == "read_field":
        rec = client.read(step["model"], [r("id")], fields=[step["field"]])[0]
        return rec[step["field"]]
    if op == "action":
        return _call_tolerant(client, step["model"], step["method"], r("ids"),
                              step.get("kwargs"))

    # ---- 观察点（进 observations） ----
    if op == "observe_records":
        if "ids" in step:
            rows = client.read(step["model"], r("ids"), fields=step.get("fields"))
        else:
            rows = client.search_read(step["model"], r("domain"),
                                      fields=step.get("fields"),
                                      order=step.get("order"))
        scope["observations"][step["name"]] = rows
        return rows
    if op == "observe_action":
        val = _fault_or_value(client, scope, step)
        scope["observations"][step["name"]] = val
        return val
    if op == "observe_fault":
        inner = step["action"]
        msg = _fault_text(lambda: client.execute(
            inner["model"], inner["method"], _resolve(inner["ids"], scope),
            **(inner.get("kwargs") or {})))
        scope["observations"][step["name"]] = msg
        return msg
    if op == "observe_count":
        n = client.execute(step["model"], "search_count", r("domain"))
        scope["observations"][step["name"]] = n
        return n
    if op == "observe_sum":
        rows = client.search_read(step["model"], r("domain"), fields=[step["field"]])
        total = sum(row[step["field"]] or 0 for row in rows)
        scope["observations"][step["name"]] = total
        return total

    # ---- 领域宏 ----
    if op == "make_proc_product":
        return _macro_make_product(client, scope, step, process_mfg=True)
    if op == "make_plain_product":
        return _macro_make_product(client, scope, step, process_mfg=False)
    if op == "make_picking":
        return _macro_make_picking(client, scope, step)
    if op == "force_line":
        return _macro_force_line(client, scope, step)
    if op == "receive":
        return _macro_receive(client, scope, step)

    raise ScenarioError(f"未知步骤 op: {op}")


def _fault_or_value(client, scope, step):
    """observe_action：正常返回值 / marshal-None -> None / 守卫抛错 -> {'fault': msg}。"""
    try:
        return client.execute(step["model"], step["method"],
                              _resolve(step["ids"], scope),
                              **(step.get("kwargs") or {}))
    except xmlrpc.client.Fault as f:
        if "cannot marshal None" in str(f):
            return None
        return {"fault": str(f)}


# ---------------------------------------------------------------------------
# 场景运行
# ---------------------------------------------------------------------------
def run_scenario(client, ctx, scenario, run_id) -> dict:
    """执行单场景，返回 capture dict（raw，不含归一化）。"""
    scope = {
        "ctx": ctx,
        "refs": {},
        "uniq": {},
        "run_id": run_id,
        "observations": {},
    }
    started = time.time()
    status, error = "ok", None
    try:
        for step in scenario.get("steps", []):
            result = _exec_step(client, scope, step)
            if step.get("save_as"):
                scope["refs"][step["save_as"]] = result
    except Exception as e:  # noqa: BLE001 - 场景级失败要进 capture 而非炸掉整批
        status, error = "error", f"{type(e).__name__}: {e}"
    finally:
        for step in scenario.get("cleanup", []):
            try:
                _exec_step(client, scope, step)
            except Exception:  # noqa: BLE001 - 清理失败不影响判定
                pass
    return {
        "scenario": scenario["id"],
        "title": scenario.get("title", ""),
        "req": scenario.get("req", ""),
        "run_id": run_id,
        "status": status,
        "error": error,
        "duration_ms": int((time.time() - started) * 1000),
        "observations": scope["observations"],
    }
