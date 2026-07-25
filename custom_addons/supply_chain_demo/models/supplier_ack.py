from odoo import models, fields, api
from odoo.exceptions import UserError


class SupplierAck(models.Model):
    """供应商交期确认单（E1 供应商协同）。

    采购方向供应商下发 PO 后，供应商在此确认可交付的「交期」或「驳回」。
    该记录是供应商协同（交期对齐）的关键数据，既可在采购订单上直接查看，
    也可在「供应商协同工作台」统一跟踪。外部供应商门户（Odoo portal）可在二期
    复用本模型，由供应商自助确认；本期以内部协同工作台呈现能力。
    """

    _name = 'sc.supplier.ack'
    _description = '供应商交期确认单'
    _order = 'create_date desc, id'

    name = fields.Char(string='确认单号', readonly=True, default='New', copy=False, index=True)
    po_id = fields.Many2one('purchase.order', string='采购订单', required=True, ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='供应商', related='po_id.partner_id', store=True, readonly=True,
    )
    company_id = fields.Many2one(
        'res.company', string='公司', related='po_id.company_id', store=True, readonly=True,
    )
    state = fields.Selection([
        ('pending', '待确认'),
        ('confirmed', '已确认交期'),
        ('rejected', '已驳回'),
    ], string='状态', default='pending', required=True, copy=False, index=True)
    committed_date = fields.Date(string='供应商确认交期')
    remark = fields.Text(string='供应商备注')
    confirmed_at = fields.Datetime(string='确认时间', readonly=True)
    confirmed_by = fields.Many2one('res.users', string='确认人', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') in (False, 'New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('sc.supplier.ack') or 'New'
        return super().create(vals_list)

    def action_confirm(self, committed_date=None, remark=None):
        for rec in self:
            if not committed_date:
                raise UserError('请填写供应商确认交期。')
            rec.write({
                'state': 'confirmed',
                'committed_date': committed_date,
                'remark': remark or rec.remark,
                'confirmed_at': fields.Datetime.now(),
                'confirmed_by': self.env.user.id,
            })

    def action_reject(self, remark=None):
        for rec in self:
            rec.write({
                'state': 'rejected',
                'remark': remark or rec.remark,
                'confirmed_at': fields.Datetime.now(),
                'confirmed_by': self.env.user.id,
            })


class PurchaseOrder(models.Model):
    """采购订单扩展：承载供应商协同状态。

    无论交期确认单由「登记供应商交期」向导创建，还是在「供应商协同工作台」
    直接录入（关联 PO），PO 上的协同状态都从全部确认记录（ack_ids）实时计算，
    保证两条入口行为一致。
    """

    _inherit = 'purchase.order'

    ack_ids = fields.One2many('sc.supplier.ack', 'po_id', string='交期确认记录')
    supplier_ack_id = fields.Many2one('sc.supplier.ack', string='当前确认单', readonly=True, copy=False)
    supplier_ack_state = fields.Selection([
        ('pending', '待确认'),
        ('confirmed', '已确认交期'),
        ('rejected', '已驳回'),
    ], string='供应商协同状态', compute='_compute_supplier_ack', store=False)
    supplier_committed_date = fields.Date(string='供应商确认交期', compute='_compute_supplier_ack', store=False)

    @api.depends('ack_ids.state', 'ack_ids.committed_date')
    def _compute_supplier_ack(self):
        for po in self:
            ack = po.ack_ids.sorted('id', reverse=True)[:1]
            po.supplier_ack_state = ack.state if ack else False
            po.supplier_committed_date = ack.committed_date if (ack and ack.state == 'confirmed') else False

    def action_register_supplier_ack(self):
        """打开登记供应商交期确认的向导（E1 协同入口）"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '登记供应商交期确认',
            'res_model': 'sc.supplier.ack.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_po_id': self.id},
        }

    def _create_or_update_ack(self, state, committed_date=None, remark=None):
        """幂等地创建/更新本 PO 的供应商交期确认单（供向导与按钮调用）。"""
        self.ensure_one()
        ack = self.supplier_ack_id or self.env['sc.supplier.ack'].search(
            [('po_id', '=', self.id)], limit=1)
        if not ack:
            ack = self.env['sc.supplier.ack'].create({'po_id': self.id})
        if state == 'confirmed':
            ack.action_confirm(committed_date, remark)
        else:
            ack.action_reject(remark)
        self.supplier_ack_id = ack
        return ack


class SupplierAckWizard(models.TransientModel):
    """登记供应商交期确认（弹窗）：录入确认交期/备注，或驳回。"""

    _name = 'sc.supplier.ack.wizard'
    _description = '登记供应商交期确认'

    po_id = fields.Many2one('purchase.order', string='采购订单', required=True)
    partner_id = fields.Many2one(
        'res.partner', string='供应商', related='po_id.partner_id', readonly=True,
    )
    committed_date = fields.Date(string='供应商确认交期', required=True)
    remark = fields.Text(string='供应商备注')

    def action_confirm(self):
        self.ensure_one()
        self.po_id._create_or_update_ack('confirmed', self.committed_date, self.remark)
        return {'type': 'ir.actions.act_window_close'}

    def action_reject(self):
        self.ensure_one()
        self.po_id._create_or_update_ack('rejected', None, self.remark)
        return {'type': 'ir.actions.act_window_close'}
