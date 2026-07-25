# C2 自测 + A4 配置校验
# 引导 Odoo 环境（与 ai_test.py 同模式），直连 DB 跑审批流与 AI 配置。
import os
import odoo
from odoo.api import Environment
from odoo import SUPERUSER_ID
from odoo.exceptions import UserError

args = ['-d', 'supplychain']
for k, envk in (('HOST', 'db_host'), ('PORT', 'db_port'), ('USER', 'db_user'), ('PASSWORD', 'db_password')):
    if os.environ.get(k):
        args += ['--' + envk, os.environ[k]]
odoo.tools.config.parse_config(args)
cr = odoo.registry('supplychain').cursor()
env = Environment(cr, SUPERUSER_ID, {})

results = []  # (name, ok, detail)
def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), '-', name, ('' if cond else ('| ' + str(detail))))

TAG = 'C2_A4自测'
cleanup = []


def purge_tag(env, tag):
    """幂等：清除历史 TAG 残留，避免污染演示库/重复运行报错。"""
    partners = env['res.partner'].search([('name', 'like', tag + '%')])
    if not partners:
        return
    pos = env['purchase.order'].search([('partner_id', 'in', partners.ids)])
    for po in pos:
        try:
            po.picking_ids.action_cancel()
        except Exception:
            pass
        try:
            po.button_cancel()
        except Exception:
            pass
    pos.unlink()
    env['sc.purchase.request'].search([('partner_id', 'in', partners.ids)]).unlink()
    prods = env['product.product'].search([('name', 'like', tag + '%')])
    if prods:
        # 先清掉引用该物料的库存移动（已取消 PO 的 stock.move），否则产品删不掉
        moves = env['stock.move'].search([('product_id', 'in', prods.ids)])
        for p in moves.mapped('picking_id'):
            try:
                p.action_cancel()
            except Exception:
                pass
        try:
            moves.unlink()
        except Exception:
            pass
        prods.unlink()
    partners.unlink()
    env.cr.commit()


purge_tag(env, TAG)

try:
    # ---------- C2: 采购订单审批流 ----------
    supplier = env['res.partner'].create({'name': TAG + '供应商', 'supplier_rank': 1})
    cleanup.append(supplier)
    # 优先复用库内已有实物(consu)物料，避免测试污染；无则新建
    product = env['product.product'].search([('type', '=', 'consu')], limit=1)
    if not product:
        product = env['product.product'].create({
            'name': TAG + '物料', 'type': 'consu', 'list_price': 10.0, 'standard_price': 8.0})
        cleanup.append(product)

    Po = env['purchase.order']
    po = Po.create({
        'partner_id': supplier.id,
        'order_line': [(0, 0, {'product_id': product.id, 'name': product.name,
                               'product_qty': 5, 'price_unit': 10.0,
                               'date_planned': '2026-07-23'})],
    })
    cleanup.append(po)
    check('新 PO 默认审批状态=draft', po.approval_state == 'draft', po.approval_state)

    # [Unwanted] 草稿态禁止确认
    blocked_draft = False
    try:
        po.button_confirm()
    except UserError:
        blocked_draft = True
    check('草稿态确认被拦截', blocked_draft)

    # 提交 -> pending
    po.action_submit_for_approval()
    check('提交后状态=pending', po.approval_state == 'pending', po.approval_state)

    # [Unwanted] 待审态禁止确认（也禁止收货，因收货作业在确认时生成）
    blocked_pending = False
    try:
        po.button_confirm()
    except UserError:
        blocked_pending = True
    check('待审态确认被拦截', blocked_pending)

    # 审批通过 -> approved
    po.action_approve()
    check('审批后状态=approved', po.approval_state == 'approved', po.approval_state)
    check('记录审批人', bool(po.approved_by))
    check('记录审批时间', bool(po.approved_date))

    # 已批 -> 确认成功（生成收货作业）
    po.button_confirm()
    check('已批后可确认(到货)', po.state == 'purchase', po.state)
    check('确认生成收货作业(picking)', len(po.picking_ids) >= 1, len(po.picking_ids))

    # 驳回路径：新 PO 提交后驳回 -> rejected -> 重置 -> draft
    po2 = Po.create({
        'partner_id': supplier.id,
        'order_line': [(0, 0, {'product_id': product.id, 'name': product.name,
                               'product_qty': 2, 'price_unit': 9.0,
                               'date_planned': '2026-07-23'})],
    })
    cleanup.append(po2)
    po2.action_submit_for_approval()
    po2.action_reject()
    check('驳回后状态=rejected', po2.approval_state == 'rejected', po2.approval_state)
    po2.action_reset_approval()
    check('重置后状态=draft', po2.approval_state == 'draft', po2.approval_state)

    # C1 -> C2 联动：PR 生成的 PO 应处于待提交(审批)draft
    PR = env['sc.purchase.request']
    pr = PR.create({
        'partner_id': supplier.id,
        'warehouse_id': env['stock.warehouse'].search([], limit=1).id,
        'line_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': 3,
                             'product_uom': product.uom_id.id, 'price_unit': 10.0})],
    })
    cleanup.append(pr)
    pr.action_submit()
    pr.action_generate_po()
    check('PR 已转 PO(done)', pr.state == 'done', pr.state)
    gen_po = pr.po_ids[:1]
    check('PR 生成的 PO 审批状态=draft', gen_po and gen_po.approval_state == 'draft',
          gen_po.approval_state if gen_po else '无PO')
    if gen_po:
        cleanup.append(gen_po)

    # ---------- A4: AI 配置与 Key 注入 ----------
    cfg = env['ai.config'].get_active()
    check('存在启用的 AI 配置', bool(cfg))
    if cfg:
        check('AI 配置 provider=deepseek', cfg.provider == 'deepseek', cfg.provider)
        check('AI 配置激活', cfg.active is True)
    key = os.environ.get('SUPPLY_AI_API_KEY', '')
    check('环境变量 SUPPLY_AI_API_KEY 已注入', key.startswith('sk-'),
          ('len=%d' % len(key)) if key else '缺失')

finally:
    # 幂等清理：按依赖顺序——先取消并删除 PO(及其作业)，再删 PR/物料/供应商
    try:
        pos = [r for r in cleanup if r._name == 'purchase.order']
        others = [r for r in cleanup if r._name != 'purchase.order']
        for rec in pos:
            if rec.exists():
                try:
                    rec.picking_ids.action_cancel()
                except Exception:
                    pass
                try:
                    rec.button_cancel()
                except Exception:
                    pass
        for rec in pos:
            if rec.exists():
                try:
                    rec.unlink()
                except Exception as e:
                    print('cleanup po skip', rec.id, e)
        for rec in reversed(others):
            if rec.exists():
                try:
                    rec.unlink()
                except Exception as e:
                    print('cleanup skip', rec._name, rec.id, e)
        cr.commit()
    except Exception as e:
        print('cleanup error:', e)
    cr.close()

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print('\n=== C2/A4 自测: %d/%d PASS ===' % (passed, total))
import sys
sys.exit(0 if passed == total else 1)
