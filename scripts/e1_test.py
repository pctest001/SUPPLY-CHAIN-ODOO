# E1 供应商协同 自测（odoo shell，退出自动回滚，不污染演示库）
# 运行: docker compose run --rm odoo odoo shell -d supplychain < scripts/e1_test.py
PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS  %s' % name)
    else:
        FAIL += 1
        print('  FAIL  %s' % name)


print('\n===== E1 供应商协同自测 =====')

Po = env['purchase.order']
Ack = env['sc.supplier.ack']

# 取一个真实存在的 PO（百世，P00024）做协同验证
po = Po.browse(24)
check('PO 存在且为采购单', bool(po) and po._name == 'purchase.order')
check('PO 供应商存在', bool(po.partner_id))

# 1) 新建交期确认单：默认 pending
ack = Ack.create({'po_id': po.id})
check('确认单号走序列 SACK/', ack.name.startswith('SACK/'))
check('初始状态=pending(待确认)', ack.state == 'pending')
check('供应商自动带出', ack.partner_id.id == po.partner_id.id)
check('PO 协同状态=pending', po.supplier_ack_state == 'pending')

# 2) 供应商确认交期
from datetime import date, timedelta
cdate = (date.today() + timedelta(days=7)).isoformat()
ack.action_confirm(committed_date=cdate, remark='可于下周交付')
check('确认后状态=confirmed', ack.state == 'confirmed')
check('确认交期已记录', str(ack.committed_date)[:10] == cdate)
check('确认时间已记录', bool(ack.confirmed_at))
check('PO 协同状态=confirmed', po.supplier_ack_state == 'confirmed')
check('PO 确认交期已联动', po.supplier_committed_date == ack.committed_date)

# 3) 幂等：再次确认应更新同一条（不新增）
po._create_or_update_ack('confirmed', committed_date=cdate, remark='更新备注')
check('幂等：PO 仍只关联一条确认单', po.supplier_ack_id.id == ack.id)

# 4) 驳回路径
ack2 = Ack.create({'po_id': po.id})
check('新确认单初始 pending', ack2.state == 'pending')
ack2.action_reject(remark='产能不足，无法按期交付')
check('驳回后状态=rejected', ack2.state == 'rejected')

# 5) PO 动作入口返回向导动作
action = po.action_register_supplier_ack()
check('登记交期入口返回向导动作', action.get('res_model') == 'sc.supplier.ack.wizard')

print('\n===== E1 汇总: %d PASS / %d FAIL =====' % (PASS, FAIL))
env.cr.rollback()
