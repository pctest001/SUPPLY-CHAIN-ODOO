"""演示：自定义抽象基类 OdooModel，被 StockQuant 复用。

要点：
  - OdooModel 继承 models.AbstractModel 并声明 `_abstract = True`，
    它是一个「mixin 基类」：不建表、不单独注册，只集中放公共字段/方法。
  - StockQuant 的 Python 基类用 models.Model（具体模型），通过
    `_inherit = 'odoo.model'` 把 OdooModel 当作 mixin 复用，
    从而自动获得基类里的字段与方法。这是 Odoo 推荐的标准写法。
  - 仍然不要重写 __init__，初始化用 default= / create 等 ORM 钩子。
"""

from odoo import models, fields, api


class OdooModel(models.AbstractModel):
    """所有业务模型的公共 mixin 基类（抽象，不建表、不单独注册）。"""

    _name = 'odoo.model'
    _description = 'Odoo 公共基类（抽象 mixin）'
    _abstract = True

    # 公共字段：所有 _inherit 它的模型自动拥有
    active = fields.Boolean(default=True, string='是否有效')
    remark = fields.Text(string='备注')

    def say_hello(self):
        """公共方法：所有复用它的模型都能调用。"""
        return f"hello from {self._name}"


class StockQuant(models.Model):
    """库存定量演示模型：复用 OdooModel（mixin）。

    标准写法：基类是 models.Model（具体模型），用 _inherit 引入抽象基类，
    而不是直接 class StockQuant(OdooModel) 去继承 AbstractModel——
    后者会让 _abstract 语义混乱、导致表无法创建。
    """

    _name = 'demo.stock.quant'
    _inherit = 'odoo.model'          # 复用抽象基类的字段与方法
    _description = '库存定量（演示：继承 OdooModel）'

    # —— 自己的字段 ——
    # default= 是 Odoo 推荐的初始化方式（而不是重写 __init__）
    product_code = fields.Char(string='物料编码', required=True)
    location = fields.Char(string='库位', default='WH/Stock')
    quantity = fields.Float(string='数量', default=0.0)

    @api.model_create_single
    def create(self, vals):
        """演示 ORM 钩子：写入前加工数据，等价于「构造时初始化」。"""
        vals = dict(vals)
        if not vals.get('remark'):
            vals['remark'] = f"由 {self._name} 自动创建"
        return super().create(vals)

    def show_info(self):
        """演示调用继承自基类的方法。"""
        return self.say_hello() + f" | {self.product_code}: {self.quantity}"
