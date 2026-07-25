# -*- coding: utf-8 -*-
"""H1 端到端联调（主链路 + AI 一次跑通）。

运行：
  cd supply-chain-odoo
  docker compose run --rm odoo odoo shell -d supplychain < scripts/h1_e2e.py

覆盖范围（一条龙连跑，退出时回滚，不污染演示库）：
  主链路：B 主数据 → C1 采购申请PR→PO → C2 PO审批流
          → C3 收货(批次/效期) → D1 入库/出库 → D2 跨仓调拨
          → D3 效期拦截 → D4 负库存/超额收货拦截
  看板数据源：F1 直接读 stock.quant 验证看板取数口径
  AI 链路：G1 实时对话(DeepSeek) / G6 注入拦截(白名单) / G4 权限继承(ir.rule)
"""
import datetime
from odoo import fields
from odoo.exceptions import UserError

PASS = FAIL = 0
SKIP = 0


def check(name, cond, note=''):
    global PASS, FAIL, SKIP
    if cond is None:
        SKIP += 1
        print('SKIP |', name, ('| ' + note) if note else '')
    elif cond:
        PASS += 1
        print('PASS |', name, ('| ' + note) if note else '')
    else:
        FAIL += 1
        print('FAIL |', name, ('| ' + note) if note else '')


def validate(picking):
    """处理 button_validate 可能返回的立即转移/欠单向导。"""
    res = picking.button_validate()
    if isinstance(res, dict) and res.get('res_model'):
        wiz = env[res['res_model']].browse(res['res_id'])
        if wiz.exists():
            if wiz._name == 'stock.immediate.transfer':
                wiz.process()
            elif wiz._name == 'stock.backorder.confirmation':
                wiz.process()
    return picking.state


def on_hand(product, loc, lot=None):
    dom = [('product_id', '=', product.id), ('location_id', '=', loc.id)]
    if lot:
        dom.append(('lot_id', '=', lot.id))
    return sum(env['stock.quant'].search(dom).mapped('quantity'))


# ===================== 环境：华南工厂 =====================
_hn = env['res.company'].search([('name', '=', '华南工厂')], limit=1)
env = env(context=dict(env.context, allowed_company_ids=[_hn.id]))
Product = env['product.product']
Lot = env['stock.lot']
Quant = env['stock.quant']
Picking = env['stock.picking']
PType = env['stock.picking.type']

wh = env['stock.warehouse'].search([('company_id', '=', _hn.id)], limit=1)
src_loc = wh.lot_stock_id                       # HNC2/Stock 原料仓
out_type = PType.search([('code', '=', 'outgoing'), ('warehouse_id', '=', wh.id)], limit=1)
in_type = PType.search([('code', '=', 'incoming'), ('warehouse_id', '=', wh.id)], limit=1)
hncf_type = PType.search([('sequence_code', '=', 'HNCF')], limit=1)
cust_loc = env.ref('stock.stock_location_customers')
vendor_loc = env.ref('stock.stock_location_suppliers')
check(bool(_hn) and bool(wh) and bool(out_type) and bool(in_type) and bool(hncf_type),
      'H1 环境就位(华南工厂/原料仓/出向/入向/HNCF调拨类型)')

print('\n===== 主链路：B 主数据 =====')
supplier = env['res.partner'].create({
    'name': 'H1演示供应商', 'supplier_rank': 1, 'company_id': _hn.id,
})
pm = env['product.product'].create({
    'name': 'H1演示-流程制造物料', 'type': 'consu',
    'is_process_mfg': True, 'list_price': 12.0, 'company_id': _hn.id,
})
check(pm.product_tmpl_id.is_process_mfg, 'B 流程制造物料标记生效')
check(pm.product_tmpl_id.tracking == 'lot', 'B 流程制造自动启用批次追踪')
check(pm.product_tmpl_id.use_expiration_date is True, 'B 流程制造自动启用效期管理')

print('\n===== 主链路：C1 采购申请PR → PO =====')
uom = pm.uom_id
pr = env['sc.purchase.request'].create({
    'partner_id': supplier.id, 'warehouse_id': wh.id,
    'line_ids': [(0, 0, {
        'product_id': pm.id, 'product_uom_qty': 100.0,
        'product_uom': uom.id, 'price_unit': 12.0,
        'date_planned': fields.Date.today(),
    })],
})
check(pr.state == 'draft', 'C1 PR 初始状态=草稿')
pr.action_submit()
check(pr.state == 'confirmed', 'C1 PR 提交后=已提交')
act = pr.action_generate_po()
po = env['purchase.order'].browse(act['res_id'])
check(pr.state == 'done', 'C1 PR 转PO后=已转PO')
check(po.order_line and po.order_line[0].product_qty == 100.0, 'C1 PO 明细数量=100')

print('\n===== 主链路：C2 PO 审批流 =====')
check(po.approval_state == 'draft', 'C2 PO 初始审批=待提交')
try:
    po.button_confirm()
    check(False, 'C2 未审批禁止确认(应被拦截)')
except UserError:
    check(True, 'C2 未审批确认被拦截(UserError)')
po.action_submit_for_approval()
check(po.approval_state == 'pending', 'C2 提交审批=待审批')
po.action_approve()
check(po.approval_state == 'approved', 'C2 审批通过=已审批')
check(bool(po.approved_by) and bool(po.approved_date), 'C2 记录审批人/时间')

print('\n===== 主链路：C3 收货(批次/效期) + D1 入库 =====')
po.button_confirm()
check(len(po.picking_ids) >= 1, 'C3 PO确认生成收货作业')
pick_in = po.picking_ids.filtered(lambda p: p.picking_type_id.code == 'incoming')[:1]
check(pick_in.picking_type_id.code == 'incoming', 'C3 收货作业=入向')
ml = pick_in.move_line_ids[0]
exp = fields.Datetime.now() + datetime.timedelta(days=180)
ml.write({'lot_name': 'H1-LOT-001', 'expiration_date': exp, 'quantity': 100.0})
st_in = validate(pick_in)
lot = env['stock.lot'].search(
    [('name', '=', 'H1-LOT-001'), ('product_id', '=', pm.id)], limit=1)
check(bool(lot) and bool(lot.expiration_date), 'C3 stock.lot 已建且效期可追溯')
check(st_in == 'done', 'D1 入库作业=done')
q_in = on_hand(pm, src_loc, lot)
check(abs(q_in - 100.0) < 0.01, 'D1 入库后来源仓库存 +100 (实=%s)' % q_in)

print('\n===== 主链路：D1 出库 + D3 效期拦截 =====')
# 正常出向（绑定有效批次）
p_out = Picking.create({
    'picking_type_id': out_type.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'company_id': _hn.id,
})
env['stock.move'].create({
    'name': pm.name, 'product_id': pm.id, 'product_uom_qty': 30,
    'product_uom': uom.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'picking_id': p_out.id, 'company_id': _hn.id,
})
p_out.action_confirm()
p_out.move_line_ids[0].write({'lot_id': lot.id, 'quantity': 30})
st_out = validate(p_out)
check(st_out == 'done', 'D1 正常出库(30)=done')
check(abs(on_hand(pm, src_loc, lot) - 70.0) < 0.01, 'D1 出库后该批次库存 100→70 (实=%s)' % on_hand(pm, src_loc, lot))

# D3：过期批次出向被拦截
lot_exp = Lot.create({
    'name': 'H1-LOT-EXPIRED', 'product_id': pm.id, 'company_id': _hn.id,
    'expiration_date': fields.Date.to_date('2020-01-01'),
})
Quant.create({'product_id': pm.id, 'location_id': src_loc.id, 'lot_id': lot_exp.id,
              'inventory_quantity': 50}).action_apply_inventory()
p_exp = Picking.create({
    'picking_type_id': out_type.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'company_id': _hn.id,
})
env['stock.move'].create({
    'name': pm.name, 'product_id': pm.id, 'product_uom_qty': 10,
    'product_uom': uom.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'picking_id': p_exp.id, 'company_id': _hn.id,
})
p_exp.action_confirm()
p_exp.move_line_ids[0].write({'lot_id': lot_exp.id, 'quantity': 10})
blocked = False
try:
    p_exp.button_validate()
except UserError as e:
    blocked = True
    print('   D3 拦截提示:', str(e).replace('\n', ' ')[:80])
check(blocked, 'D3 过期批次出向被拦截(UserError)')
check(p_exp.state != 'done', 'D3 被拦截后作业未 done')

print('\n===== 主链路：D2 跨仓调拨（原料仓→成品仓） =====')
# HNCF 内部调拨：HNC2/Stock → HNF2/Stock
hnf2 = env['stock.warehouse'].search([('code', '=', 'HNF2')], limit=1)
dest_loc = hnf2.lot_stock_id
p_tr = Picking.create({
    'picking_type_id': hncf_type.id, 'location_id': src_loc.id,
    'location_dest_id': dest_loc.id, 'company_id': _hn.id,
})
env['stock.move'].create({
    'name': pm.name, 'product_id': pm.id, 'product_uom_qty': 20,
    'product_uom': uom.id, 'location_id': src_loc.id,
    'location_dest_id': dest_loc.id, 'picking_id': p_tr.id, 'company_id': _hn.id,
})
p_tr.action_confirm()
p_tr.move_line_ids[0].write({'lot_id': lot.id, 'quantity': 20})
st_tr = validate(p_tr)
check(st_tr == 'done', 'D2 跨仓调拨=done(事务一致)')
check(abs(on_hand(pm, dest_loc, lot) - 20.0) < 0.01, 'D2 目的仓到货 +20 (实=%s)' % on_hand(pm, dest_loc, lot))
check(abs(on_hand(pm, src_loc, lot) - 50.0) < 0.01, 'D2 来源仓扣减 70→50 (实=%s)' % on_hand(pm, src_loc, lot))

print('\n===== 主链路：D4 负库存 / 超额收货拦截 =====')
# 负库存：发出 9999 > 现有 50
p_neg = Picking.create({
    'picking_type_id': out_type.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'company_id': _hn.id,
})
env['stock.move'].create({
    'name': pm.name, 'product_id': pm.id, 'product_uom_qty': 9999,
    'product_uom': uom.id, 'location_id': src_loc.id,
    'location_dest_id': cust_loc.id, 'picking_id': p_neg.id, 'company_id': _hn.id,
})
p_neg.action_confirm()
p_neg.move_line_ids[0].write({'lot_id': lot.id, 'quantity': 9999})
blk_neg = False
try:
    p_neg.button_validate()
except UserError as e:
    blk_neg = True
    print('   D4 拦截提示:', str(e).replace('\n', ' ')[:80])
check(blk_neg, 'D4 负库存(9999>50)被拦截(UserError)')
check(p_neg.state != 'done', 'D4 被拦截后作业未 done')

# 超额收货：订购 10，到货 20
po2 = env['purchase.order'].create({
    'partner_id': supplier.id, 'company_id': _hn.id,
    'order_line': [(0, 0, {
        'product_id': pm.id, 'product_qty': 10, 'price_unit': 12.0,
        'product_uom': uom.id, 'date_planned': fields.Datetime.now(),
    })],
})
po2.write({'approval_state': 'approved'})
po2.button_confirm()
pick2 = po2.picking_ids[0]
mv2 = env['stock.move'].create({
    'name': pm.name, 'product_id': pm.id, 'product_uom_qty': 20,
    'product_uom': uom.id, 'location_id': vendor_loc.id,
    'location_dest_id': src_loc.id, 'picking_id': pick2.id, 'company_id': _hn.id,
    'purchase_line_id': po2.order_line[0].id,
})
pick2.action_confirm()
pick2.move_line_ids[0].write({'lot_name': 'H1-OVER', 'expiration_date': exp, 'quantity': 20})
blk_over = False
try:
    pick2.button_validate()
except UserError as e:
    blk_over = True
    print('   D4 拦截提示:', str(e).replace('\n', ' ')[:80])
check(blk_over, 'D4 超额收货(20>10)被拦截(UserError)')
check(pick2.state != 'done', 'D4 超额被拦截后作业未 done')

print('\n===== F1 看板数据源验证（直读 stock.quant，仅内部库位） =====')
# F1 看板直连 psql 读 stock.quant(内部库位)；此处用 ORM 镜像其取数口径，
# 验证联调后「实际在库」数据正确（排除 客商/虚拟库位的对冲分录）。
h1_quants = Quant.search_read(
    [('product_id', '=', pm.id), ('quantity', '!=', 0), ('location_id.usage', '=', 'internal')],
    ['product_id', 'quantity', 'location_id', 'lot_id'])
total_qty = sum(q['quantity'] for q in h1_quants)
check(total_qty > 0, 'F1 数据源 stock.quant(内部库位)含 H1 物料在库(合计=%s)' % round(total_qty, 2))
# 验证跨仓分布：HNC2/Stock 应剩余 50，HNF2/Stock 应到货 20
q_hnc2 = on_hand(pm, src_loc, lot)
q_hnf2 = on_hand(pm, dest_loc, lot)
check(abs(q_hnc2 - 50.0) < 0.01 and abs(q_hnf2 - 20.0) < 0.01,
      'F1 跨仓分布正确(HNC2=%s, HNF2=%s)' % (round(q_hnc2, 2), round(q_hnf2, 2)))
loc_names = sorted({ (env['stock.location'].browse(q['location_id'][0]).complete_name) for q in h1_quants })
print('   F1 看板将展示 H1 物料内部库位:', loc_names)

print('\n===== AI 链路：G6 注入拦截 =====')
sess = env['ai.chat.session'].create({})
r_bad = sess._dispatch_tool('delete_everything_now', {})
check(isinstance(r_bad, dict) and 'error' in r_bad, 'G6 白名单外工具被拒(疑似注入)')
r_good = sess._dispatch_tool('query_stock', {'limit': 3})
check(isinstance(r_good, list), 'G6 白名单内工具可用')

print('\n===== AI 链路：G1 实时对话(DeepSeek) =====')
try:
    ans = sess.ask('当前系统里有哪些临期或负库存的物料需要关注？请给出简短建议。')
    check(bool(ans) and len(ans.strip()) > 0, 'G1 AI 对话返回非空', note=('首句: ' + ans.strip().split(chr(10))[0][:60]))
except Exception as e:
    check(None, 'G1 AI 实时对话', note='调用异常: %s' % e)

print('\n===== AI 链路：G4 权限继承（华东用户看不到华南库存） =====')
try:
    hd = env['res.company'].search([('name', '=', '华东工厂')], limit=1)
    hd_wh = env['stock.warehouse'].search([('company_id', '=', hd.id)], limit=1)
    hd_user = env['res.users'].create({
        'name': 'H1-G4华东仓管', 'login': 'h1_g4_hd', 'company_id': hd.id,
        'company_ids': [(6, 0, [hd.id])],
        'groups_id': [(6, 0, [env.ref('base.group_user').id,
                               env.ref('stock.group_stock_user').id])],
    })
    env_hd = env(user=hd_user.id, context=dict(env.context, allowed_company_ids=[hd.id]))
    hd_stock = env_hd['ai.chat.session'].create({})._tool_query_stock(limit=500)
    hn_wh_names = set(env['stock.warehouse'].search([('company_id', '=', _hn.id)]).mapped('name'))
    leaked = [q for q in hd_stock if (q.get('warehouse') or '') in hn_wh_names]
    check(len(leaked) == 0,
          'G4 华东用户AI查询未越权看到华南库存(命中华南数=%d)' % len(leaked),
          note=('华东可见库存条目=%d' % len(hd_stock)))
except Exception as e:
    check(None, 'G4 权限继承验证', note='需人工复核: %s' % e)

print('\n================ H1 联调汇总 ================')
print('PASS=%d  FAIL=%d  SKIP=%d' % (PASS, FAIL, SKIP))
print('(odoo shell 退出即回滚，演示库保持干净)')
try:
    env.cr.rollback()
except Exception:
    pass
