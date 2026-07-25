from odoo import models, fields, api
from odoo.exceptions import UserError


class Recipe(models.Model):
    """配方（流程制造 BOM / 配方主数据）。

    流程制造（化工/食品）中，一个成品由若干原料按固定配比构成。
    配方记录「成品 → 原料清单（含用量/占比）」，用于：
      - 主数据沉淀（B3）
      - 在物料表单上直接查看某成品的配方
      - 与批次效期追溯（C3/D3）形成「成品-原料-批次」链路
    """

    _name = 'sc.recipe'
    _description = '配方（流程制造 BOM）'
    _order = 'code, id'

    name = fields.Char(string='配方名称', required=True)
    code = fields.Char(string='配方编码', readonly=True, default='New', copy=False, index=True)
    finished_product_tmpl_id = fields.Many2one(
        'product.template', string='成品（流程制造）', required=True,
        domain="[('is_process_mfg','=',True)]",
        help='该配方对应的流程制造成品（须标记为流程制造）',
    )
    company_id = fields.Many2one(
        'res.company', string='公司', default=lambda self: self.env.company, required=True,
    )
    uom_id = fields.Many2one('uom.uom', string='产量单位')
    note = fields.Text(string='工艺备注')
    line_ids = fields.One2many('sc.recipe.line', 'recipe_id', string='原料明细', copy=True)
    total_qty = fields.Float(string='总用量', compute='_compute_total_qty', store=False)
    line_count = fields.Integer(string='原料数', compute='_compute_line_count', store=False)

    @api.depends('line_ids.product_qty')
    def _compute_total_qty(self):
        for r in self:
            r.total_qty = sum(l.product_qty for l in r.line_ids)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for r in self:
            r.line_count = len(r.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') in (False, 'New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('sc.recipe') or 'New'
        return super().create(vals_list)

    @api.constrains('line_ids')
    def _check_lines(self):
        for r in self:
            if not r.line_ids:
                raise UserError('配方至少需要一种原料。')
            for line in r.line_ids:
                if line.product_qty <= 0:
                    raise UserError('原料「%s」用量必须大于 0。' % (line.product_id.display_name or ''))

    def name_get(self):
        return [(r.id, '%s (%s)' % (r.name, r.code)) for r in self]

    # 在成品物料表单上反向展示配方
    def action_open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '配方',
            'res_model': 'sc.recipe',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class RecipeLine(models.Model):
    """配方原料明细行"""

    _name = 'sc.recipe.line'
    _description = '配方原料明细'
    _order = 'id'

    recipe_id = fields.Many2one('sc.recipe', string='配方', ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'product.product', string='原料', required=True,
        domain="[('is_storable','=',True)]",
        help='参与该配方的原料（须为可库存物料）',
    )
    product_qty = fields.Float(string='用量', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='单位')
    percentage = fields.Float(string='占比%', compute='_compute_percentage', store=False, digits=(5, 2))

    @api.depends('product_qty', 'recipe_id.total_qty')
    def _compute_percentage(self):
        for l in self:
            total = l.recipe_id.total_qty or 0.0
            l.percentage = (l.product_qty / total * 100.0) if total else 0.0

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id and not self.uom_id:
            self.uom_id = self.product_id.uom_id

    @api.constrains('product_id', 'recipe_id')
    def _check_component(self):
        for l in self:
            if l.product_id and l.recipe_id.finished_product_tmpl_id:
                if l.product_id.product_tmpl_id.id == l.recipe_id.finished_product_tmpl_id.id:
                    raise UserError('原料「%s」不能与成品为同一物料。' % l.product_id.display_name)


class ProductTemplate(models.Model):
    """在物料上反向挂出配方，便于成品物料表单直接查看其配方。"""

    _inherit = 'product.template'

    recipe_ids = fields.One2many('sc.recipe', 'finished_product_tmpl_id', string='配方')
