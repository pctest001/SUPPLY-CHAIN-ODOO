#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 供应链库存看板 —— 轻量实时看板（standalone，无外部依赖）。

数据来源：直接通过 `docker compose exec db psql` 查询 supplychain 库
（复用 supplychain_queries.sql 的同款查询），完全绕过 Odoo ORM 多公司上下文限制。
前端为标准库 http.server 提供的内联 HTML/CSS/SVG 页面（无 CDN 依赖，离线可用）。

启动（仓库根目录 supply-chain-odoo/ 下执行）：
  python3 scripts/inventory_dashboard.py
浏览器打开 http://localhost:5000

环境变量（可选，含默认值）：
  DASH_PORT   5000
  DB_NAME     supplychain
"""
import os
import json
import subprocess
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DASH_PORT = int(os.environ.get('DASH_PORT', '5000'))
DB_NAME = os.environ.get('DB_NAME', 'supplychain')
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPIRY_WARN_DAYS = 60


def _run_sql(sql):
    """通过 docker compose exec db psql 执行查询，返回行列表（每行字段列表）。"""
    cmd = ['docker', 'compose', 'exec', '-T', 'db', 'psql',
           '-U', 'odoo', '-d', DB_NAME, '-At', '-F,', '-c', sql]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_DIR,
                       timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or '').strip() or 'psql 执行失败')
    rows = []
    for line in r.stdout.splitlines():
        if line == '' or line.startswith('(rows'):
            continue
        rows.append(line.split(','))
    return rows


def _name(val):
    """product_template.name 是 jsonb，取中文；兜底原值。"""
    if val is None:
        return ''
    return val


def fetch_data():
    try:
        today = date.today()

        # 供应链演示仓库（过滤掉 Odoo 自带 My Company/Chicago 等种子仓库）
        SUPPLY_WH = ['HNC2', 'HNF2', 'HDR2', 'HDC2']
        wh_arr = "ARRAY['%s']" % "','".join(SUPPLY_WH)

        # 仓库
        wh_rows = _run_sql(
            "SELECT code, name FROM stock_warehouse "
            "WHERE code = ANY(%s) ORDER BY code;" % wh_arr)
        warehouses = [{'code': r[0], 'name': r[1], 'qty': 0.0}
                      for r in wh_rows]
        wh_map = {w['code']: w for w in warehouses}

        # 实时库存（按 仓 / 物料 / 批次 汇总）
        q_rows = _run_sql("""
            SELECT wh.code,
                   COALESCE(pt.name->>'zh_CN', pt.name->>'en_US', pt.name::text),
                   COALESCE(lot.name, ''),
                   SUM(sq.quantity)
            FROM stock_quant sq
            JOIN stock_location sl ON sl.id = sq.location_id
            JOIN stock_warehouse wh ON wh.id = sl.warehouse_id
            JOIN product_product pp ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            LEFT JOIN stock_lot lot ON lot.id = sq.lot_id
            WHERE sq.quantity > 0
              AND wh.code = ANY(%s)
            GROUP BY wh.code, pt.name, lot.name
            ORDER BY wh.code, pt.name;
        """ % wh_arr)
        details = []
        sku_set = set()
        for r in q_rows:
            wh_code, pname, lot_name, qty = r[0], r[1], r[2], float(r[3] or 0)
            if wh_code in wh_map:
                wh_map[wh_code]['qty'] += qty
            key = (wh_code, pname, lot_name)
            sku_set.add(pname)
            details.append({
                'warehouse': wh_code,
                'product': pname,
                'lot': lot_name,
                'qty': round(qty, 2),
            })

        # 临期 / 过期 批次
        l_rows = _run_sql("""
            SELECT lot.name,
                   COALESCE(pt.name->>'zh_CN', pt.name->>'en_US', pt.name::text),
                   lot.expiration_date::date
            FROM stock_lot lot
            JOIN product_product pp ON pp.id = lot.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE lot.expiration_date IS NOT NULL
              AND lot.expiration_date::date <= CURRENT_DATE
                  + INTERVAL '%d days'
            ORDER BY lot.expiration_date;
        """ % EXPIRY_WARN_DAYS)
        expiring = []
        expired_cnt = 0
        expiring_cnt = 0
        for r in l_rows:
            exp = _parse_date(r[2])
            if not exp:
                continue
            days = (exp - today).days
            if days < 0:
                expired_cnt += 1
                level = 'expired'
            else:
                expiring_cnt += 1
                level = 'warn'
            expiring.append({
                'lot': r[0], 'product': r[1],
                'expiration': (r[2] or '')[:10], 'days': days, 'level': level,
            })

        # 跨仓调拨作业（internal）
        t_rows = _run_sql("""
            SELECT sp.name, spt.name, sp.state,
                   srcc.complete_name, dstc.complete_name,
                   sp.date_done::date
            FROM stock_picking sp
            JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
            LEFT JOIN stock_location srcc ON srcc.id = sp.location_id
            LEFT JOIN stock_location dstc ON dstc.id = sp.location_dest_id
            WHERE spt.code = 'internal'
            ORDER BY (sp.state='done'), sp.name DESC;
        """)
        transfers = []
        for r in t_rows:
            done = (r[5] or '')[:10] if r[5] else ''
            transfers.append({
                'name': r[0], 'type': r[1], 'state': r[2],
                'src': r[3] or '', 'dst': r[4] or '', 'done': done,
            })

        metrics = {
            'warehouses': len(warehouses),
            'sku': len(sku_set),
            'total_qty': round(sum(d['qty'] for d in details), 2),
            'expiring': expiring_cnt,
            'expired': expired_cnt,
        }
        return {
            'ok': True,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'metrics': metrics,
            'warehouses': [{'code': w['code'], 'name': w['name'],
                            'qty': round(w['qty'], 2)} for w in warehouses],
            'details': details,
            'expiring': expiring,
            'transfers': transfers[:30],
        }
    except Exception as e:  # noqa: BLE001
        return {'error': '拉取库存数据失败：%s' % str(e)}


def _parse_date(s):
    if not s:
        return None
    s = str(s)[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


# ----------------------------- 前端渲染 -----------------------------
def render_html(data):
    payload = json.dumps(data, ensure_ascii=False)
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>供应链库存看板</title>
<style>
  :root{
    --bg:#0f1420; --panel:#171d2b; --panel2:#1e2638; --line:#2a3346;
    --txt:#e6ebf5; --muted:#93a0b8; --accent:#3b82f6; --green:#22c55e;
    --amber:#f59e0b; --red:#ef4444; --teal:#14b8a6;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--txt);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
    "Microsoft YaHei",sans-serif;}
  .wrap{max-width:1180px;margin:0 auto;padding:22px 22px 60px;}
  header{display:flex;align-items:center;justify-content:space-between;
    flex-wrap:wrap;gap:12px;margin-bottom:18px;}
  h1{font-size:22px;margin:0;font-weight:650;letter-spacing:.5px;}
  h1 .dot{color:var(--teal);}
  .meta{color:var(--muted);font-size:13px;}
  button{background:var(--accent);color:#fff;border:0;border-radius:8px;
    padding:8px 16px;font-size:13px;cursor:pointer;}
  button:hover{filter:brightness(1.1);}
  .cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;
    margin-bottom:18px;}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px;}
  .card .k{color:var(--muted);font-size:12px;margin-bottom:6px;}
  .card .v{font-size:26px;font-weight:700;}
  .card.red .v{color:var(--red);}
  .card.amber .v{color:var(--amber);}
  .card.green .v{color:var(--green);}
  .grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;}
  @media(max-width:900px){.grid{grid-template-columns:1fr;}
    .cards{grid-template-columns:repeat(2,1fr);}}
  .panel{background:var(--panel);border:1px solid var(--line);
    border-radius:12px;padding:16px 18px;margin-bottom:16px;}
  .panel h2{font-size:15px;margin:0 0 14px;font-weight:600;
    display:flex;align-items:center;gap:8px;}
  .panel h2 .bar{width:4px;height:15px;background:var(--accent);
    border-radius:2px;display:inline-block;}
  .whrow{margin-bottom:12px;}
  .whrow .top{display:flex;justify-content:space-between;font-size:13px;
    margin-bottom:5px;}
  .whrow .top .nm{color:var(--muted);}
  .track{background:var(--panel2);border-radius:6px;height:14px;
    overflow:hidden;border:1px solid var(--line);}
  .fill{height:100%;background:linear-gradient(90deg,#3b82f6,#14b8a6);
    border-radius:6px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);}
  th{color:var(--muted);font-weight:600;font-size:12px;
    position:sticky;top:0;background:var(--panel);}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
  .tbl-scroll{max-height:340px;overflow:auto;}
  .tag{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;
    font-weight:600;}
  .tag.done{background:rgba(34,197,94,.15);color:var(--green);}
  .tag.wait{background:rgba(245,158,11,.15);color:var(--amber);}
  .tag.expired{background:var(--red);color:#fff;}
  .tag.warn{background:rgba(245,158,11,.2);color:var(--amber);}
  .err{background:rgba(239,68,68,.12);border:1px solid var(--red);
    color:#fca5a5;padding:16px;border-radius:10px;}
  .empty{color:var(--muted);padding:14px;text-align:center;}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="dot">●</span> 供应链库存看板</h1>
    <div style="display:flex;align-items:center;gap:14px;">
      <span class="meta" id="genat"></span>
      <button onclick="refresh()">刷新</button>
    </div>
  </header>
  <div id="app"></div>
</div>
<script>
const DATA = __PAYLOAD__;
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function fmt(n){return (n||0).toLocaleString('zh-CN',{maximumFractionDigits:2});}
function card(k,v,cls){return `<div class="card ${cls||''}"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`;}
function warehouseChart(wh){
  const max=Math.max(1,...wh.map(w=>w.qty));
  return wh.map(w=>{
    const pct=Math.round(w.qty/max*100);
    return `<div class="whrow"><div class="top"><span><b>${esc(w.code)}</b> <span class="nm">${esc(w.name)}</span></span><span>${fmt(w.qty)}</span></div>
      <div class="track"><div class="fill" style="width:${pct}%"></div></div></div>`;
  }).join('');
}
function detailsTable(rows){
  if(!rows.length) return '<div class="empty">暂无实时库存</div>';
  const body=rows.map(r=>`<tr>
    <td>${esc(r.warehouse)}</td><td>${esc(r.product)}</td>
    <td>${esc(r.lot||'—')}</td>
    <td class="num">${fmt(r.qty)}</td></tr>`).join('');
  return `<div class="tbl-scroll"><table><thead><tr>
    <th>仓库</th><th>物料</th><th>批次</th><th class="num">数量</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}
function expiringTable(rows){
  if(!rows.length) return '<div class="empty">无临期/过期批次</div>';
  const body=rows.map(r=>{
    const tag=r.level==='expired'?'<span class="tag expired">已过期</span>'
      :`<span class="tag warn">剩 ${r.days} 天</span>`;
    return `<tr><td>${esc(r.lot)}</td><td>${esc(r.product)}</td>
      <td>${esc(r.expiration)}</td><td>${tag}</td></tr>`;
  }).join('');
  return `<div class="tbl-scroll"><table><thead><tr>
    <th>批次</th><th>物料</th><th>效期</th><th>状态</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}
function transferTable(rows){
  if(!rows.length) return '<div class="empty">暂无跨仓调拨作业</div>';
  const body=rows.map(r=>{
    const st=r.state==='done'?'<span class="tag done">已完成</span>'
      :'<span class="tag wait">处理中</span>';
    return `<tr><td>${esc(r.name)}</td><td>${esc(r.type)}</td>
      <td>${esc(r.src)} → ${esc(r.dst)}</td><td>${st}</td>
      <td>${esc(r.done||'—')}</td></tr>`;
  }).join('');
  return `<div class="tbl-scroll"><table><thead><tr>
    <th>单号</th><th>类型</th><th>路线</th><th>状态</th><th>完成日</th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
}
function render(d){
  const app=document.getElementById('app');
  document.getElementById('genat').textContent='生成于 '+ (d.generated_at||'');
  if(d.error){app.innerHTML=`<div class="err">⚠️ ${esc(d.error)}</div>`;return;}
  const m=d.metrics;
  const cards=[
    card('仓库数',m.warehouses),
    card('SKU 数',m.sku),
    card('库存总量(件)',fmt(m.total_qty)),
    card('临期批次(≤60天)',m.expiring,'amber'),
    card('已过期批次',m.expired,m.expired?'red':'green'),
  ].join('');
  app.innerHTML=`
    <div class="cards">${cards}</div>
    <div class="grid">
      <div class="panel"><h2><span class="bar"></span>各仓库库存汇总</h2>
        ${warehouseChart(d.warehouses)}</div>
      <div class="panel"><h2><span class="bar"></span>临期 / 过期预警</h2>
        ${expiringTable(d.expiring)}</div>
    </div>
    <div class="panel"><h2><span class="bar"></span>实时库存明细（按 仓 / 物料 / 批次）</h2>
      ${detailsTable(d.details)}</div>
    <div class="panel"><h2><span class="bar"></span>跨仓调拨作业</h2>
      ${transferTable(d.transfers)}</div>`;
}
function refresh(){
  fetch('/api/data').then(r=>r.json()).then(d=>render(d)).catch(e=>{
    document.getElementById('app').innerHTML=
      `<div class="err">⚠️ 刷新失败：${esc(e)}</div>`;
  });
}
render(DATA);
</script>
</body>
</html>""" .replace('__PAYLOAD__', payload)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/data'):
            data = fetch_data()
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self._send(200, body, 'application/json; charset=utf-8')
        else:
            data = fetch_data()
            html = render_html(data).encode('utf-8')
            self._send(200, html)

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('0.0.0.0', DASH_PORT), Handler)
    print('库存看板已启动: http://localhost:%d  (Ctrl+C 停止)' % DASH_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == '__main__':
    main()
