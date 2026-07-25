from odoo import models, fields
from odoo.exceptions import UserError


class StockPickingSc(models.Model):
    """C3 收货守卫 + D1 出库守卫 + D3 效期拦截：流程制造物料必须按批次可追溯。

    EARS 对齐：
      - [Event-driven] When 仓库在「收货」(incoming) 作业点击"验证"，
        若某明细的物料为「流程制造」，the system shall 校验其已录入批次号(Lot)
        且已记录效期(Expiration Date)，否则拒绝验证并提示。
      - [Event-driven] When 仓库在「发货」(outgoing) 作业点击"验证"，
        若某明细的物料为「流程制造」，the system shall 校验其已指定批次(Lot)，
        否则拒绝验证并提示（保证出库可追溯到具体批次，按批次量化正确）。
      - [Event-driven] When 仓库在「发货」(outgoing) 作业点击"验证"，
        the system shall 校验所绑定批次(Lot)的效期(Expiration Date)未过期；
        若某明细批次的效期早于今日，拒绝验证并提示（D3 批次/效期拦截）。
      - [Event-driven] When 仓库在「发货/调出」(outgoing / internal) 作业点击"验证"，
        the system shall 校验来源库位的现有库存不小于本次作业发出量；
        若某明细发出量超过来源库位现有库存，拒绝验证并提示（D4 负库存拦截）。
      - [Event-driven] When 仓库在「收货」(incoming) 作业点击"验证"且该作业已关联
        采购订单行(purchase.order.line)，the system shall 校验累计收货量不超过订购量；
        若「已收货 + 本次到货」大于订购量，拒绝验证并提示（D4 超额收货拦截）。
    说明：批次/效期在确认收货(验证)时写入 stock.lot，从而实现效期可追溯；
          出库时通过 lot_id 绑定到具体收货批次，保证库存量化(write-off)正确；
          D3 复用 product_expiry 已落到 stock.lot 的 expiration_date 做越期拦截。
    """

    _inherit = 'stock.picking'

    def button_validate(self):
        today = fields.Date.today()
        for picking in self:
            code = picking.picking_type_id.code
            # 入向(incoming)：D4 超额收货拦截 + C3 守卫（批次 + 效期）
            if code == 'incoming':
                for line in picking.move_line_ids:
                    product = line.product_id
                    if not product:
                        continue
                    # D4：超额收货拦截（与是否流程制造无关，仅当绑定采购订单行时生效）
                    move = line.move_id
                    po_line = move.purchase_line_id if move else None
                    if po_line:
                        ordered = po_line.product_qty
                        done_qty = 0.0
                        for m in po_line.move_ids:
                            if m.picking_id and m.picking_id.state == 'done' and m != move:
                                done_qty += m.product_uom_qty
                        this_qty = line.quantity or 0.0
                        if (done_qty + this_qty) > ordered:
                            raise UserError(
                                '物料「%s」对应采购订单行订购量为 %s，已收货 %s，本次到货 %s，'
                                '累计将超出订购量，已拦截（D4 超额收货拦截）。'
                                % (product.display_name, ordered, done_qty, this_qty))
                    # C3：流程制造物料须录入批次号 + 效期
                    if not product.product_tmpl_id.is_process_mfg:
                        continue
                    # 批次：必须录入（lot_id 已选 或 lot_name 待建）
                    if not (line.lot_id or line.lot_name):
                        raise UserError(
                            '物料「%s」为流程制造物料，收货时必须录入批次号(Lot)。'
                            % product.display_name)
                    # 效期：必须录入（Odoo 原生 product_expiry 会记录到 stock.lot）
                    if not line.expiration_date:
                        raise UserError(
                            '物料「%s」为流程制造物料，收货时必须录入效期(Expiration Date)。'
                            % product.display_name)
            # 出向(outgoing)：D4 负库存拦截 + D1 守卫（流程制造出库必须指定批次）+ D3 效期拦截
            elif code == 'outgoing':
                for line in picking.move_line_ids:
                    product = line.product_id
                    if not product:
                        continue
                    # D4：负库存拦截（来源库位现有库存不足则拒绝）
                    self._d4_check_negative(line)
                    # D1：流程制造出库必须绑定到具体的收货批次（lot_id）
                    if product.product_tmpl_id.is_process_mfg and not line.lot_id:
                        raise UserError(
                            '物料「%s」为流程制造物料，出库时必须指定批次(Lot)后方可发货。'
                            % product.display_name)
                    # D3：效期拦截——批次已过期禁止出库
                    # 注：product_expiry 的 stock.lot.expiration_date 为 Datetime 字段，
                    # 须用 fields.Date.to_date() 转为日期后再与今日(date)比较。
                    exp = line.lot_id.expiration_date
                    if line.lot_id and exp and fields.Date.to_date(exp) < today:
                        raise UserError(
                            '物料「%s」的批次「%s」效期为 %s，已于今日之前过期，禁止出库'
                            '（D3 批次/效期拦截）。'
                            % (product.display_name, line.lot_id.name,
                               fields.Date.to_string(line.lot_id.expiration_date)))
            # 内部调拨(internal)：Odoo 在确认时会自动从来源库位批次携带 lot 到
            # 目的库位（按批次可追溯），D2 核心诉求「事务一致 + 批次可追溯」由原生满足；
            # 但仍需 D4 负库存拦截（来源库位扣减前校验，防止调出超出现有库存）。
            elif code == 'internal':
                for line in picking.move_line_ids:
                    self._d4_check_negative(line)
        return super().button_validate()

    def _d4_check_negative(self, line):
        """D4 负库存拦截：本次作业从来源库位发出的数量不得超过现有库存。"""
        product = line.product_id
        if not product:
            return
        qty = line.quantity or 0.0
        if qty <= 0:
            return
        domain = [('product_id', '=', product.id), ('location_id', '=', line.location_id.id)]
        if line.lot_id:
            domain.append(('lot_id', '=', line.lot_id.id))
        on_hand = sum(self.env['stock.quant'].search(domain).mapped('quantity'))
        if on_hand < qty:
            raise UserError(
                '物料「%s」在库位「%s」的现有库存为 %s，本次作业发出 %s 将导致负库存，'
                '已拦截（D4 负库存拦截）。'
                % (product.display_name, line.location_id.complete_name, on_hand, qty))
