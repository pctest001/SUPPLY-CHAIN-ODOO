# -*- coding: utf-8 -*-
def arch_of(model, vtype):
    res = env[model].get_views([(False, vtype)])
    return res['views'][vtype]['arch']

arch = arch_of('purchase.order', 'form')
checks = ['供应商', '提交审批', '确认订单', '审批订单', '询价单', '采购订单',
          '预计到达日', '产品', '数量', '单价', '税额', '金额', '计划日期', '审批信息']
all_ok = True
for c in checks:
    ok = c in arch
    all_ok = all_ok and ok
    print(('OK  ' if ok else 'MISS'), c)
print('---FORM RESULT---', 'PASS' if all_ok else 'FAIL')

list_arch = arch_of('purchase.order', 'list')
for c in ['供应商', '参考单号', '总金额', 'approval_state']:
    print(('OK  ' if c in list_arch else 'MISS'), 'list:', c)

search_arch = arch_of('purchase.order', 'search')
for c in ['订单', '我的订单', '供应商']:
    print(('OK  ' if c in search_arch else 'MISS'), 'search:', c)

line_arch = arch_of('purchase.order.line', 'list')
for c in ['采购订单明细', '产品', '单价', '数量', '单位', '金额', '计划日期', '供应商']:
    print(('OK  ' if c in line_arch else 'MISS'), 'line:', c)
