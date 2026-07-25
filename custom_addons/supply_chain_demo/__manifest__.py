{
    'name': 'Supply Chain Demo (MVP)',
    'summary': '流程制造供应链 MVP：主数据 / 采购 / 多仓库存 / 批次效期',
    'version': '1.0',
    'license': 'LGPL-3',
    'category': 'Manufacturing',
    'website': 'https://example.com',
    'depends': ['base', 'product', 'purchase', 'stock', 'product_expiry'],
    'data': [
        'security/ir.model.access.csv',
        'data/demo_companies.xml',
        'data/purchase_request.xml',
        'data/master_seq.xml',
        'views/supply_chain_views.xml',
    ],
    # 可复现初始化：装模块即设置已知 admin 凭据（Odoo 自身哈希），无需手动补密码
    'post_init_hook': '_post_init_set_admin',
    'installable': True,
    'application': True,
}
