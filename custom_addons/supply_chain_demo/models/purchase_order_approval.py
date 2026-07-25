from odoo import models, fields, api
from odoo.exceptions import UserError


class PurchaseOrderApproval(models.Model):
    """采购订单 PO 审批流（C2）。

    在原生 purchase.order 之上叠加审批状态机，与业务状态 `state` 解耦：
      - draft    待提交：可编辑
      - pending  待审批：已提交，等待审批（禁止确认/收货）
      - approved 已审批：可推进到采购单确认（生成收货作业）
      - rejected 已驳回：打回，可重置为草稿重新提交

    EARS 对齐：
      - [Event-driven] When 用户点击"提交审批"，the system shall 置为 pending。
      - [Event-driven] When 审批人点击"审批通过"，the system shall 置为 approved 并记录审批人/时间。
      - [Unwanted] If 审批状态非 approved 即点击"确认订单"，then the system shall 拒绝并报错。
    """

    _inherit = 'purchase.order'

    approval_state = fields.Selection([
        ('draft', '待提交'),
        ('pending', '待审批'),
        ('approved', '已审批'),
        ('rejected', '已驳回'),
    ], string='审批状态', default='draft', copy=False, index=True, tracking=True)
    approved_by = fields.Many2one('res.users', string='审批人', readonly=True, copy=False)
    approved_date = fields.Datetime(string='审批时间', readonly=True, copy=False)

    # ---- 状态流转 ----
    def action_submit_for_approval(self):
        self.ensure_one()
        if not self.order_line:
            raise UserError('请先添加采购明细后再提交审批。')
        if self.amount_total <= 0:
            raise UserError('采购订单金额为 0，请核对明细单价/数量。')
        self.write({'approval_state': 'pending',
                    'approved_by': False, 'approved_date': False})

    def action_approve(self):
        self.ensure_one()
        if self.approval_state != 'pending':
            raise UserError('仅"待审批"状态的采购订单可被审批。')
        self.write({'approval_state': 'approved',
                    'approved_by': self.env.user.id,
                    'approved_date': fields.Datetime.now()})

    def action_reject(self):
        self.ensure_one()
        if self.approval_state != 'pending':
            raise UserError('仅"待审批"状态的采购订单可被驳回。')
        self.write({'approval_state': 'rejected',
                    'approved_by': False, 'approved_date': False})

    def action_reset_approval(self):
        self.ensure_one()
        self.write({'approval_state': 'draft',
                    'approved_by': False, 'approved_date': False})

    # ---- [Unwanted] 未审批禁止确认（确认会生成收货作业，故也禁止收货） ----
    def button_confirm(self):
        for order in self:
            if order.approval_state != 'approved':
                raise UserError(
                    '采购订单 %s 尚未通过审批（当前：%s），无法确认。请先提交并审批。'
                    % (order.name, dict(self._fields['approval_state'].selection).get(order.approval_state)))
        return super().button_confirm()
