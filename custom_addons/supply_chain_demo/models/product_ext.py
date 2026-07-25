from odoo import models, fields, api


class ProductTemplate(models.Model):
    """流程制造物料扩展：标记是否为流程制造，并强调批次/效期追溯。"""

    _inherit = 'product.template'

    # 流程制造（化工/食品等）业务标记，区别于普通进销存
    is_process_mfg = fields.Boolean(
        string='流程制造',
        default=False,
        help='启用后该物料按流程制造管理，自动开启批次(Lot)与效期(Expiry)追溯',
    )

    # ---- C3：流程制造物料自动启用批次 + 效期追溯 ----
    # 一旦标记「流程制造」，即按批次追踪(tracking=lot)并启用效期管理
    # (use_expiration_date)，同时给出默认保质期(expiration_time)，
    # 并使物料可库存(is_storable)，使收货时必须录入批次、效期被记录
    # 并可追溯(Odoo 原生 product_expiry)。
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_process_mfg'):
                vals['tracking'] = 'lot'
                vals['use_expiration_date'] = True
                vals['is_storable'] = True
                vals.setdefault('expiration_time', 365)
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_process_mfg'):
            proc = self.filtered(lambda r: r.is_process_mfg)
            if proc:
                proc.write({'tracking': 'lot', 'use_expiration_date': True, 'is_storable': True})
        return res

    @api.onchange('is_process_mfg')
    def _onchange_is_process_mfg(self):
        if self.is_process_mfg:
            self.tracking = 'lot'
            self.use_expiration_date = True
            self.is_storable = True
            if not self.expiration_time:
                self.expiration_time = 365
