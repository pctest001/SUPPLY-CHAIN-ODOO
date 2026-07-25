# E1 演示供应商交期确认（odoo shell，幂等 + commit 持久化，UI 可查看）
# 运行: docker compose run --rm odoo odoo shell -d supplychain < scripts/e1_demo.py
from datetime import date, timedelta

Po = env['purchase.order']
Ack = env['sc.supplier.ack']

# 取供应商「百世」的采购订单 P00024（id=24，purchase 状态）
po = Po.browse(24)
assert po.exists(), 'PO 24 不存在'

# 幂等：已存在确认单则更新确认交期；否则新建并确认
ack = Ack.search([('po_id', '=', po.id)], limit=1)
cdate = (date.today() + timedelta(days=7)).isoformat()
if ack:
    ack.action_confirm(committed_date=cdate, remark='已确认下周交付（演示数据）')
    print('已更新确认单 %s' % ack.name)
else:
    ack = Ack.create({'po_id': po.id})
    ack.action_confirm(committed_date=cdate, remark='已确认下周交付（演示数据）')
    print('已创建确认单 %s' % ack.name)

print('PO: %s | 供应商: %s | 协同状态: %s | 确认交期: %s' % (
    po.name, po.partner_id.name, ack.state, ack.committed_date))
env.cr.commit()
print('已提交（演示库持久化）。')
