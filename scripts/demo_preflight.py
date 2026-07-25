# -*- coding: utf-8 -*-
"""
演示前一键自检（preflight）：录屏前置条件全绿才开录，避免现场卡壳。

运行：
    cd supply-chain-odoo
    docker compose run --rm odoo odoo shell -d supplychain < scripts/demo_preflight.py

检查分两类：
  [环境/应用健康]  录屏能否正常进行（登录、模块、G7 接口、G7 前端打包、菜单入口）
  [演示数据齐备]  走查脚本依赖的演示数据是否已在库（仓 / 配方 / 交期确认 / 过期批次 / D2 调拨类型）
    任一类有 FAIL 都会退出码 1；演示数据缺失时打印精确灌数据命令，按需补灌即可。

退出码：全 PASS 为 0，任一 FAIL 为 1。
"""
import sys
import datetime

try:
    import requests
except ImportError:
    requests = None

# 注意：在 `docker compose run --rm odoo` 临时容器内，localhost 指向自身而非运行中的
# odoo-1 服务，必须用 compose 服务名 `odoo` 才能命中正在提供 Web 的实例。
BASE = "http://odoo:8069"
results = []

SEED_HINT = (
    "演示数据未齐，请按序灌入（b3 依赖 b4 建立的模板 ID，必须按顺序）：\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/b4_demo_data.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/b3_demo.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/d1_demo.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/d2_demo.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/d3_demo.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/d4_demo.py\n"
    "  docker compose run --rm odoo odoo shell -d supplychain < scripts/e1_demo.py\n"
    "（若 b3/e1 报 ID 断言失败，说明库里混入了非预期数据，需先 ./init.sh 干净重建再灌）"
)


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    extra = (" — " + detail) if detail else ""
    print("[%s] %s%s" % (mark, name, extra))


# ========== 环境 / 应用健康 ==========

# 1) 系统管理员 + 演示密码
admin_login = "admin"
try:
    g = env.ref("base.group_system")
    admin = env["res.users"].search([("groups_id", "in", [g.id])], limit=1)
    if admin:
        admin.write({"password": "admin"})
        env.cr.commit()  # 必须提交，否则运行中 odoo-1 实例读不到新密码，HTTP 登录会失败
        admin_login = admin.login
        check("[环境] 系统管理员存在且演示密码已置为 admin", True, admin_login)
    else:
        check("[环境] 系统管理员存在", False, "未找到 group_system 用户")
except Exception as e:
    check("[环境] 系统管理员查询异常", False, repr(e))

# 2) sc_ai 模块已安装
mod = env["ir.module.module"].search([("name", "=", "sc_ai")], limit=1)
check("[环境] sc_ai 模块已安装", bool(mod) and mod.state == "installed",
      mod.state if mod else "未找到")

# 3) G7 后端接口可用（ORM 直调，验证方法体存在）
try:
    sess = env["ai.chat.session"].get_or_create_session()
    ok1 = isinstance(sess, dict) and "id" in sess
    check("[环境] G7 get_or_create_session 可用", ok1,
          ("session_id=%s" % sess.get("id")) if ok1 else str(sess))
    ans = env["ai.chat.session"].chat(sess["id"], "当前有哪些物料库存？")
    alen = len(ans.get("answer") or "")
    check("[环境] G7 chat 返回非空答复（DeepSeek）", alen > 0, "答复长度=%d" % alen)
    ns = env["ai.chat.session"].new_session()
    check("[环境] G7 new_session 可用", isinstance(ns, dict) and "id" in ns,
          "session_id=%s" % ns.get("id"))
except Exception as e:
    check("[环境] G7 接口调用异常", False, repr(e))

# 4) 关键菜单 external id 全部存在
menu_xmlids = [
    "supply_chain_demo.menu_supply_chain_root",
    "supply_chain_demo.menu_sc_purchase_root",
    "supply_chain_demo.menu_sc_purchase_request",
    "supply_chain_demo.menu_sc_master_root",
    "supply_chain_demo.menu_sc_recipe",
    "supply_chain_demo.menu_sc_supplier_root",
    "supply_chain_demo.menu_sc_supplier_ack",
    "sc_ai.menu_sc_ai_root",
    "stock.menu_stock_root",
    "stock.menu_product_stock",
    "stock.menu_action_production_lot_form",
    "stock.menu_pickingtype",
    "stock.menu_stock_transfers",
    "purchase.menu_purchase_form_action",
]
missing = []
for xid in menu_xmlids:
    try:
        env.ref(xid)
    except Exception:
        missing.append(xid)
check("[环境] 关键菜单 external id 全部存在", len(missing) == 0,
      ("缺失: " + ", ".join(missing)) if missing else "共 %d 个" % len(menu_xmlids))

# 5) HTTP 登录可达 + G7 前端组件完整打包进后台 bundle
if requests:
    try:
        import re
        s = requests.Session()
        r = s.post(BASE + "/web/session/authenticate", json={
            "jsonrpc": "2.0", "method": "call",
            "params": {"db": "supplychain", "login": admin_login, "password": "admin"}
        }, timeout=30)
        uid = r.json().get("result", {}).get("uid")
        check("[环境] HTTP 登录可达（%s/admin）" % admin_login, bool(uid), "uid=%s" % uid)

        w = s.get(BASE + "/web", timeout=30)
        check("[环境] GET /web 返回 200", w.status_code == 200, "status=%d" % w.status_code)

        # 抓所有后台 js bundle，逐个搜 G7 方法体（不依赖具体 bundle 名）
        js_urls = re.findall(r'src="(/web/assets/[^"]*\.js)"', w.text)
        needed = {
            "_loadSession": "AiChatSystray._loadSession",
            "get_or_create_session": "ai_models.get_or_create_session",
            "new_session": "ai_models.new_session",
            "sc_ai_chat": "systray 注册 sc_ai_chat",
        }
        miss = set(needed.keys())
        for u in js_urls:
            c = s.get(BASE + u, timeout=30).text
            for tok in list(miss):
                if tok in c:
                    miss.discard(tok)
        check("[环境] G7 组件已完整打包进后台 bundle（侧边面板可渲染的保证）",
              len(miss) == 0,
              ("缺失方法体: " + ", ".join(needed[t] for t in miss)) if miss
              else "含 _loadSession/get_or_create_session/new_session/sc_ai_chat")
    except Exception as e:
        check("[环境] HTTP/bundle 检查异常", False, repr(e))
else:
    check("[环境] HTTP/bundle 检查", False, "requests 不可用，跳过")

# ========== 演示数据齐备（走查依赖） ==========

wh_codes = ["HNC2", "HNF2", "HDR2", "HDC2"]
wh_n = env["stock.warehouse"].search_count([("code", "in", wh_codes)])
check("[数据] 演示仓齐备(华南/华东 各双仓)", wh_n == 4, "命中 %d/4" % wh_n)

recipe_n = env["sc.recipe"].search_count([])
check("[数据] 演示配方存在(sc.recipe, 如 RCP/2026/00014)", recipe_n > 0, "计数=%d" % recipe_n)

ack_n = env["sc.supplier.ack"].search_count([])
check("[数据] 供应商交期确认存在(sc.supplier.ack, 如 SACK/2026/00005)", ack_n > 0, "计数=%d" % ack_n)

today = datetime.date.today()
exp_n = env["stock.lot"].search_count([("expiration_date", "<", today)])
check("[数据] 存在已过期批次(供 D3 效期拦截演示)", exp_n > 0, "过期批次数=%d" % exp_n)

demo_exp = env["stock.lot"].search([("name", "=", "LOT-EXPIRED-DEMO")], limit=1)
check("[数据] D3 演示过期批次 LOT-EXPIRED-DEMO 存在", bool(demo_exp),
      demo_exp.name if demo_exp else "缺失")

pt_n = env["stock.picking.type"].search_count(
    [("sequence_code", "in", ["HNCF", "HNFC", "HDCF", "HDFC"])])
check("[数据] D2 跨仓调拨作业类型齐备(HNCF/HNFC/HDCF/HDFC)", pt_n == 4, "命中 %d/4" % pt_n)

# ========== 汇总 ==========
print("\n==== 自检汇总 ====")
npass = sum(1 for _, c, _ in results if c)
nfail = len(results) - npass
print("PASS=%d  FAIL=%d  TOTAL=%d" % (npass, nfail, len(results)))
for name, c, detail in results:
    if not c:
        print("  x %s — %s" % (name, detail))
print("==================")

demo_fail = any(name.startswith("[数据]") and not c for _, c, _ in results)
if demo_fail:
    print("\n>>> 演示数据缺失，录屏前请先灌入：")
    print(SEED_HINT)

sys.exit(1 if nfail else 0)
