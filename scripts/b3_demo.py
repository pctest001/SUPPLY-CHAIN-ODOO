# B3 演示配方（odoo shell，幂等 + commit 持久化，UI 可查看）
# 运行: docker compose run --rm odoo odoo shell -d supplychain < scripts/b3_demo.py
from datetime import date, timedelta

Recipe = env['sc.recipe']
Template = env['product.template']

# 成品：柠檬味苏打水 330ml（tmpl 67，流程制造）
finished = Template.browse(67)
assert finished.exists() and finished.is_process_mfg, '成品模板 67 不存在或非流程制造'

# 原料模板 → product_variant_id
def variant(tmpl_id):
    t = Template.browse(tmpl_id)
    return t.product_variant_id

comp = {
    '去离子水': variant(74),
    '食品级柠檬酸': variant(60),
    '食用葡萄糖浆': variant(61),
    '香精香料-A型': variant(63),
}
for name, v in comp.items():
    assert v and v.is_storable, '原料 %s 未取得可库存变体' % name

# 幂等：同成品同名配方视为已建
existing = Recipe.search([('finished_product_tmpl_id', '=', finished.id),
                          ('name', '=', '柠檬味苏打水 330ml 配方')], limit=1)
if existing:
    rec = existing
    print('已存在配方 %s，跳过创建' % rec.code)
else:
    rec = Recipe.create({
        'name': '柠檬味苏打水 330ml 配方',
        'finished_product_tmpl_id': finished.id,
        'uom_id': finished.uom_id.id if finished.uom_id else False,
        'note': '投料顺序：去离子水 → 糖浆 → 柠檬酸 → 香精；常温混合 30 分钟。',
        'line_ids': [
            (0, 0, {'product_id': comp['去离子水'].id, 'product_qty': 82.0}),
            (0, 0, {'product_id': comp['食用葡萄糖浆'].id, 'product_qty': 12.0}),
            (0, 0, {'product_id': comp['食品级柠檬酸'].id, 'product_qty': 4.0}),
            (0, 0, {'product_id': comp['香精香料-A型'].id, 'product_qty': 2.0}),
        ],
    })
    print('已创建配方 %s' % rec.code)

print('配方: %s | 成品: %s | 总用量: %.1f | 原料数: %d' % (
    rec.code, finished.display_name, rec.total_qty, len(rec.line_ids)))
env.cr.commit()
print('已提交（演示库持久化）。')
