# B3 配方主数据 自测（odoo shell，退出自动回滚，不污染演示库）
# 运行: docker compose run --rm odoo odoo shell -d supplychain < scripts/b3_test.py
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


print('\n===== B3 配方主数据自测 =====')

# 1) 准备成品（流程制造）与原料（可库存）
finished = env['product.template'].create({
    'name': 'B3测试-柠檬味苏打水',
    'is_process_mfg': True,  # 自动 is_storable/tracking=lot/use_expiration_date
})
check('流程制造成品自动 is_storable', finished.is_storable)
check('流程制造成品自动 tracking=lot', finished.tracking == 'lot')

comp1 = env['product.template'].create({'name': 'B3原料-去离子水', 'is_storable': True, 'type': 'consu'})
comp2 = env['product.template'].create({'name': 'B3原料-柠檬酸', 'is_storable': True, 'type': 'consu'})
comp3 = env['product.template'].create({'name': 'B3原料-糖浆', 'is_storable': True, 'type': 'consu'})
p1 = comp1.product_variant_id
p2 = comp2.product_variant_id
p3 = comp3.product_variant_id
check('原料可取得 product_variant', bool(p1) and bool(p2) and bool(p3))

# 2) 创建配方
recipe = env['product.template'].browse(finished.id)
Recipe = env['sc.recipe']
rec = Recipe.create({
    'name': '柠檬味苏打水配方',
    'finished_product_tmpl_id': finished.id,
    'line_ids': [
        (0, 0, {'product_id': p1.id, 'product_qty': 80.0}),
        (0, 0, {'product_id': p2.id, 'product_qty': 10.0}),
        (0, 0, {'product_id': p3.id, 'product_qty': 10.0}),
    ],
})
check('配方单号走序列 RCP/', rec.code.startswith('RCP/'))
check('配方成品关联正确', rec.finished_product_tmpl_id.id == finished.id)
check('总用量合计=100', abs(rec.total_qty - 100.0) < 1e-6)
# 占比
line_map = {l.product_id.id: l for l in rec.line_ids}
check('去离子水占比=80%%', abs((line_map[p1.id].percentage) - 80.0) < 1e-6)
check('柠檬酸占比=10%%', abs((line_map[p2.id].percentage) - 10.0) < 1e-6)

# 3) 成品物料反向挂出配方（product.template.recipe_ids）
check('成品物料反向可见配方', rec.id in [r.id for r in finished.recipe_ids])

# 4) 约束：空明细拒绝
try:
    Recipe.create({'name': '空配方', 'finished_product_tmpl_id': finished.id, 'line_ids': []})
    check('空明细配方被拒(UserError)', False)
except Exception:
    check('空明细配方被拒(UserError)', True)

# 5) 约束：用量<=0 拒绝
try:
    Recipe.create({
        'name': '负用量', 'finished_product_tmpl_id': finished.id,
        'line_ids': [(0, 0, {'product_id': p1.id, 'product_qty': -5.0})],
    })
    check('负用量配方被拒', False)
except Exception:
    check('负用量配方被拒', True)

# 6) 约束：原料=成品 拒绝
try:
    Recipe.create({
        'name': '自引用', 'finished_product_tmpl_id': finished.id,
        'line_ids': [(0, 0, {'product_id': finished.product_variant_id.id, 'product_qty': 1.0})],
    })
    check('原料=成品被拒', False)
except Exception:
    check('原料=成品被拒', True)

print('\n===== B3 汇总: %d PASS / %d FAIL =====' % (PASS, FAIL))
env.cr.rollback()
