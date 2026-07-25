from odoo import models, fields, api
from odoo.exceptions import UserError


class PurchaseRequest(models.Model):
    """采购申请 PR：需求部门发起、经提交后转化为采购订单 PO。

    状态机（EARS 对齐）：
      - draft     草稿：可编辑、可提交
      - confirmed 已提交：待生成采购订单（C2 审批流可在此前介入）
      - done      已转PO：已生成采购订单，PR 只读
      - cancel    已取消：作废
    """

    _name = 'sc.purchase.request'
    _description = '采购申请 PR'
    _order = 'date_request desc, id desc'

    name = fields.Char(string='单号', readonly=True, default='New', copy=False, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='供应商',
        domain="[('supplier_rank','>',0)]",
        help='生成 PO 时的交易对手，建议选择已标记为供应商的伙伴',
    )
    requested_by = fields.Many2one(
        'res.users', string='申请人', default=lambda self: self.env.user, readonly=True,
    )
    date_request = fields.Date(string='申请日期', default=fields.Date.today, required=True)
    company_id = fields.Many2one(
        'res.company', string='公司', default=lambda self: self.env.company, required=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='收货仓', required=True,
        domain="[('company_id','=',company_id)]",
        help='采购实物将入此仓，决定 PO 的收货（incoming）作业类型',
    )
    state = fields.Selection([
        ('draft', '草稿'),
        ('confirmed', '已提交'),
        ('done', '已转PO'),
        ('cancel', '已取消'),
    ], string='状态', default='draft', copy=False, index=True)
    line_ids = fields.One2many('sc.purchase.request.line', 'request_id', string='申请明细', copy=True)
    po_ids = fields.Many2many('purchase.order', string='关联采购订单', copy=False)
    po_count = fields.Integer(string='PO 数量', compute='_compute_po_count')

    @api.depends('po_ids')
    def _compute_po_count(self):
        for r in self:
            r.po_count = len(r.po_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('sc.purchase.request') or 'New'
        return super().create(vals_list)

    # ---- 状态流转（事件驱动，符合 EARS） ----
    def action_submit(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError('请先添加申请明细后再提交。')
        self.write({'state': 'confirmed'})

    def action_generate_po(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError('仅"已提交"状态的采购申请可生成采购订单。')
        if not self.partner_id:
            raise UserError('请先选择供应商后再生成采购订单。')
        if not self.line_ids:
            raise UserError('没有可申请明细，无法生成采购订单。')

        Po = self.env['purchase.order']
        order_line = []
        for line in self.line_ids:
            order_line.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.display_name,
                'product_qty': line.product_uom_qty,
                'product_uom': line.product_uom.id,
                'date_planned': line.date_planned or self.date_request,
                'price_unit': line.price_unit,
            }))

        po = Po.create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'date_order': self.date_request,
            'picking_type_id': self.warehouse_id.in_type_id.id,
            'order_line': order_line,
        })
        self.write({'po_ids': [(4, po.id)], 'state': 'done'})
        return {
            'type': 'ir.actions.act_window',
            'name': '采购订单',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        self.ensure_one()
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    def action_view_pos(self):
        self.ensure_one()
        if not self.po_ids:
            return
        return {
            'type': 'ir.actions.act_window',
            'name': '关联采购订单',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.po_ids.ids)],
            'target': 'current',
        }


class PurchaseRequestLine(models.Model):
    """采购申请明细行"""

    _name = 'sc.purchase.request.line'
    _description = '采购申请明细'

    request_id = fields.Many2one('sc.purchase.request', string='采购申请', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='物料', required=True)
    description = fields.Char(string='说明')
    product_uom_qty = fields.Float(string='数量', default=1.0, required=True)
    product_uom = fields.Many2one('uom.uom', string='单位', required=True)
    date_planned = fields.Date(string='计划交期', default=fields.Date.today)
    price_unit = fields.Float(string='预估单价', default=0.0)

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id:
            self.description = self.product_id.display_name
            if not self.product_uom:
                self.product_uom = self.product_id.uom_id
