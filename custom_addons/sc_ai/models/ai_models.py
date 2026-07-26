# sc_ai 模块：AI 智能层
# 实现 F6：对话式供应链助手(Function Calling) / 智能预警解读 / 智能补货建议
# 设计要点（对应 PRD 安全与工程素养）：
#   - AI 仅只读；所有查询走 Odoo ORM，自动继承当前用户的数据权限(ir.rule)
#   - LLM 仅可调用白名单内的只读工具函数，防提示词注入与越权写操作
#   - API Key 仅从环境变量读取，绝不入库 / 硬编码 / 进前端
#   - 全链路降级：LLM 调用失败/超时，主流程不受影响，提示"AI 暂不可用"

import json
import logging
import os
from datetime import date, timedelta

import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# AI 可调用的白名单函数（仅只读查询，防越权/防注入）
AI_TOOL_WHITELIST = {
    'query_stock',
    'query_purchase_orders',
    'query_suppliers',
    'query_expiring_lots',
    'query_low_stock',
    'query_supplier_acks',
}


def _safe_json(s):
    try:
        return json.loads(s or '{}')
    except Exception:
        return {}


class AiConfig(models.Model):
    _name = 'ai.config'
    _description = 'AI 配置'

    name = fields.Char(default='默认配置', required=True)
    provider = fields.Selection([
        ('openai', 'OpenAI'),
        ('deepseek', 'DeepSeek'),
        ('custom', '自定义 OpenAI 兼容'),
    ], default='deepseek', required=True)
    base_url = fields.Char(string='API Base URL',
                           help='自定义 provider 时填写，形如 https://api.deepseek.com/v1')
    model = fields.Char(default='deepseek-chat', required=True)
    api_key_env = fields.Char(string='API Key 环境变量名',
                              default='SUPPLY_AI_API_KEY',
                              help='Key 仅从环境变量读取，绝不入库/硬编码/进前端')
    timeout = fields.Integer(default=30)
    max_tokens = fields.Integer(default=800)
    active = fields.Boolean(default=True)

    def _get_api_key(self):
        return os.environ.get(self.api_key_env or 'SUPPLY_AI_API_KEY', '') or ''

    def _endpoint(self):
        if self.provider == 'custom' and self.base_url:
            return self.base_url.rstrip('/') + '/chat/completions'
        return {
            'openai': 'https://api.openai.com/v1/chat/completions',
            'deepseek': 'https://api.deepseek.com/v1/chat/completions',
        }.get(self.provider, 'https://api.deepseek.com/v1/chat/completions')

    @api.model
    def get_active(self):
        return self.search([('active', '=', True)], limit=1)


class AiChatMessage(models.Model):
    _name = 'ai.chat.message'
    _description = 'AI 对话消息'
    _order = 'sequence, id'

    session_id = fields.Many2one('ai.chat.session', ondelete='cascade')
    role = fields.Selection([('user', '用户'), ('assistant', 'AI'), ('tool', '工具')], required=True)
    content = fields.Text(required=True)
    sequence = fields.Integer(default=0)


class AiChatSession(models.Model):
    _name = 'ai.chat.session'
    _description = 'AI 对话会话'
    _order = 'create_date desc'

    name = fields.Char(string='标题', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    message_ids = fields.One2many('ai.chat.message', 'session_id')
    last_reply = fields.Text()

    @api.depends('message_ids')
    def _compute_name(self):
        for rec in self:
            first = rec.message_ids.filtered(lambda m: m.role == 'user')[:1]
            rec.name = ((first.content or 'AI 对话')[:40]) if first else 'AI 对话'

    # ---------- 白名单工具实现（只读，继承当前用户权限） ----------
    def _tool_query_stock(self, product_name=None, warehouse=None, limit=20):
        domain = [('quantity', '>', 0)]
        if product_name:
            domain.append(('product_id.display_name', 'ilike', product_name))
        if warehouse:
            domain.append(('location_id.warehouse_id.name', 'ilike', warehouse))
        rows = self.env['stock.quant'].search_read(
            domain, ['product_id', 'quantity', 'location_id'],
            limit=min(int(limit), 100))
        Location = self.env['stock.location']
        out = []
        for r in rows:
            loc = Location.browse(r['location_id'][0]) if r['location_id'] else None
            out.append({'product': r['product_id'][1] if r['product_id'] else '',
                        'qty': r['quantity'],
                        'location': loc.name if loc else '',
                        'warehouse': loc.warehouse_id.name if (loc and loc.warehouse_id) else ''})
        return out

    def _tool_query_purchase_orders(self, state=None, limit=20):
        domain = []
        if state:
            domain.append(('state', '=', state))
        rows = self.env['purchase.order'].search_read(
            domain, ['name', 'partner_id', 'state', 'amount_total', 'date_order'],
            limit=min(int(limit), 100))
        return [{'po': r['name'],
                 'supplier': r['partner_id'][1] if r['partner_id'] else '',
                 'state': r['state'],
                 'amount': r['amount_total']}
                for r in rows]

    def _tool_query_suppliers(self, limit=20):
        rows = self.env['res.partner'].search_read(
            [('supplier_rank', '>', 0)], ['name', 'email', 'phone'],
            limit=min(int(limit), 100))
        return [{'name': r['name'], 'email': r['email'], 'phone': r['phone']}
                for r in rows]

    def _tool_query_expiring_lots(self, days=30, limit=50):
        Lot = self.env['stock.lot']
        # [Unwanted] 当前 Odoo 版本若未启用批次效期(expiration_date)，优雅降级而非崩溃
        if 'expiration_date' not in Lot._fields:
            _logger.warning('stock.lot 无 expiration_date 字段，跳过临期批次查询')
            return []
        horizon = (date.today() + timedelta(days=int(days))).isoformat()
        rows = Lot.search_read(
            [('expiration_date', '<=', horizon), ('expiration_date', '>=', date.today().isoformat())],
            ['name', 'product_id', 'expiration_date', 'product_qty'],
            limit=min(int(limit), 200))
        return [{'lot': r['name'],
                 'product': r['product_id'][1] if r['product_id'] else '',
                 'expiry': str(r['expiration_date'])[:10],
                 'qty': r['product_qty']}
                for r in rows]

    def _tool_query_low_stock(self, limit=50):
        quants = self.env['stock.quant'].search_read(
            [('quantity', '<', 0)], ['product_id', 'quantity', 'location_id'],
            limit=min(int(limit), 200))
        return [{'product': r['product_id'][1] if r['product_id'] else '',
                 'qty': r['quantity'],
                 'location': r['location_id'][1] if r['location_id'] else ''}
                for r in quants]

    def _tool_query_supplier_acks(self, state=None, limit=50):
        """E1 供应商协同：查询供应商交期确认情况（如待确认交期的 PO）。"""
        if 'sc.supplier.ack' not in self.env:
            return []
        domain = []
        if state:
            domain.append(('state', '=', state))
        rows = self.env['sc.supplier.ack'].search_read(
            domain, ['name', 'po_id', 'partner_id', 'state', 'committed_date'],
            limit=min(int(limit), 200))
        return [{'ack': r['name'],
                 'po': r['po_id'][1] if r['po_id'] else '',
                 'supplier': r['partner_id'][1] if r['partner_id'] else '',
                 'state': r['state'],
                 'committed_date': str(r['committed_date'])[:10] if r['committed_date'] else ''}
                for r in rows]

    def _dispatch_tool(self, name, args):
        if name not in AI_TOOL_WHITELIST:
            # [Unwanted] 白名单外调用（疑似提示词注入）→ 拒绝
            return {'error': '拒绝白名单外的工具调用（疑似提示词注入）'}
        method = getattr(self, '_tool_' + name, None)
        if not method:
            return {'error': '未知工具: ' + name}
        try:
            return method(**(args or {}))
        except Exception as e:
            return {'error': '工具执行失败: ' + str(e)}

    def _build_tools(self):
        return [
            {'type': 'function', 'function': {
                'name': 'query_stock',
                'description': '查询库存数量（可按物料名/仓库过滤），只读',
                'parameters': {'type': 'object', 'properties': {
                    'product_name': {'type': 'string', 'description': '物料名称（模糊）'},
                    'warehouse': {'type': 'string', 'description': '仓库名（模糊）'},
                    'limit': {'type': 'integer', 'description': '返回条数'}}, 'required': []}}},
            {'type': 'function', 'function': {
                'name': 'query_purchase_orders',
                'description': '查询采购订单，只读',
                'parameters': {'type': 'object', 'properties': {
                    'state': {'type': 'string', 'description': '状态如 purchase/done'},
                    'limit': {'type': 'integer'}}, 'required': []}}},
            {'type': 'function', 'function': {
                'name': 'query_suppliers',
                'description': '查询供应商列表，只读',
                'parameters': {'type': 'object', 'properties': {
                    'limit': {'type': 'integer'}}, 'required': []}}},
            {'type': 'function', 'function': {
                'name': 'query_expiring_lots',
                'description': '查询临期批次（效期在 N 天内），只读',
                'parameters': {'type': 'object', 'properties': {
                    'days': {'type': 'integer', 'description': '未来天数'},
                    'limit': {'type': 'integer'}}, 'required': []}}},
            {'type': 'function', 'function': {
                'name': 'query_low_stock',
                'description': '查询负库存/低于安全库存的物料，只读',
                'parameters': {'type': 'object', 'properties': {
                    'limit': {'type': 'integer'}}, 'required': []}}},
            {'type': 'function', 'function': {
                'name': 'query_supplier_acks',
                'description': '查询供应商交期确认情况（E1 供应商协同），只读；可筛选状态',
                'parameters': {'type': 'object', 'properties': {
                    'state': {'type': 'string', 'description': '状态：pending 待确认 / confirmed 已确认交期 / rejected 已驳回'},
                    'limit': {'type': 'integer'}}, 'required': []}}},
        ]

    def _build_system_prompt(self):
        return ('你是供应链智能助手，服务于基于 Odoo 的流程制造供应链系统。'
                '你只能通过给定的工具函数查询数据，不得擅自编造数据或执行写操作。'
                '回答要简洁、面向业务（管理者/仓管/采购），给出可操作建议。'
                '所有数据查询均继承用户权限，禁止越权。')

    def _call_llm(self, cfg, messages, tools):
        key = cfg._get_api_key()
        if not key:
            raise UserError(_('未配置 AI API Key（请设置环境变量 %s）') % (cfg.api_key_env or 'SUPPLY_AI_API_KEY'))
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
        payload = {
            'model': cfg.model,
            'messages': messages,
            'tools': tools,
            'tool_choice': 'auto',
            'max_tokens': cfg.max_tokens,
        }
        r = requests.post(cfg._endpoint(), json=payload, headers=headers, timeout=cfg.timeout)
        r.raise_for_status()
        msg = r.json()['choices'][0]['message']
        if msg.get('tool_calls'):
            messages.append({'role': 'assistant', 'content': msg.get('content', ''),
                             'tool_calls': msg['tool_calls']})
            for tc in msg['tool_calls']:
                fn = tc['function']
                result = self._dispatch_tool(fn['name'], _safe_json(fn.get('arguments')))
                messages.append({'role': 'tool', 'tool_call_id': tc['id'],
                                 'content': json.dumps(result, ensure_ascii=False, default=str)})
            payload['messages'] = messages
            r2 = requests.post(cfg._endpoint(), json=payload, headers=headers, timeout=cfg.timeout)
            r2.raise_for_status()
            return r2.json()['choices'][0]['message'].get('content', '')
        return msg.get('content', '')

    def ask(self, question):
        """F6.1 对话式助手：LLM + 函数调用查 Odoo 数据并回答"""
        cfg = self.env['ai.config'].get_active()
        if not cfg:
            return 'AI 未配置（请在「AI 配置」中启用一条配置）。'
        messages = [
            {'role': 'system', 'content': self._build_system_prompt()},
            {'role': 'user', 'content': question},
        ]
        try:
            answer = self._call_llm(cfg, messages, self._build_tools())
        except Exception as e:
            # [Unwanted] LLM 失败/超时 → 降级，主流程不受影响
            _logger.warning('AI LLM 调用失败，降级处理: %s', e)
            answer = ('(AI 暂时不可用，已降级。核心供应链功能不受影响。)\n'
                      + self._fallback(question))
        seq = len(self.message_ids)
        self.env['ai.chat.message'].create({'session_id': self.id, 'role': 'user',
                                            'content': question, 'sequence': seq})
        self.env['ai.chat.message'].create({'session_id': self.id, 'role': 'assistant',
                                            'content': answer, 'sequence': seq + 1})
        self.last_reply = answer
        return answer

    # ---------- OWL 侧边面板接口（G7，复用 ask()，不新增写能力） ----------
    @api.model
    def get_or_create_session(self):
        """供侧边面板：取当前用户最近会话（无则新建），返回 id + 消息历史。"""
        session = self.search([('user_id', '=', self.env.uid)],
                              limit=1, order='create_date desc')
        if not session:
            session = self.create({})
        return {'id': session.id, 'messages': session.get_messages()}

    def get_messages(self):
        self.ensure_one()
        return [{'role': m.role, 'content': m.content}
                for m in self.message_ids.sorted('sequence')]

    @api.model
    def chat(self, session_id, question):
        """供侧边面板：发一条消息，返回最新会话状态（含全部消息）。"""
        question = (question or '').strip()
        if not question:
            return {'id': session_id, 'answer': '', 'messages': []}
        session = self.browse(int(session_id)) if session_id else self.create({})
        answer = session.ask(question)
        return {'id': session.id, 'answer': answer, 'messages': session.get_messages()}

    @api.model
    def new_session(self):
        """供侧边面板：开启一个全新会话。"""
        session = self.create({})
        return {'id': session.id, 'messages': []}

    def _fallback(self, question):
        try:
            low = self._tool_query_low_stock(10)
            exp = self._tool_query_expiring_lots(30, 10)
            parts = []
            if low:
                parts.append('检测到负库存物料 %d 项，例如：%s' % (len(low), low[0]['product']))
            if exp:
                parts.append('检测到临期批次 %d 项，例如：%s' % (len(exp), exp[0]['product']))
            if parts:
                return '规则引擎结果：\n' + '\n'.join(parts)
        except Exception:
            pass
        return '暂时无法生成智能回答，请稍后重试或检查 AI 配置。'

    def interpret_alerts(self):
        """F6.2 智能预警解读：临期 + 负库存 → LLM 解读"""
        cfg = self.env['ai.config'].get_active()
        exp = self._tool_query_expiring_lots(30, 50)
        low = self._tool_query_low_stock(50)
        if not cfg:
            return 'AI 未配置。规则提示：临期 %d 项，负库存 %d 项。' % (len(exp), len(low))
        prompt = ('以下是供应链异常数据，请生成面向管理者的通俗解读与处置建议：\n'
                  '临期批次: %s\n负库存: %s' % (json.dumps(exp, ensure_ascii=False),
                                              json.dumps(low, ensure_ascii=False)))
        messages = [{'role': 'system', 'content': self._build_system_prompt()},
                    {'role': 'user', 'content': prompt}]
        try:
            return self._call_llm(cfg, messages, [])
        except Exception as e:
            _logger.warning('预警解读降级: %s', e)
            return '（AI 暂不可用）临期 %d 项、负库存 %d 项，建议优先处理。' % (len(exp), len(low))

    def suggest_replenishment(self):
        """F6.3 智能补货建议（统计级 + LLM 解释）"""
        cfg = self.env['ai.config'].get_active()
        low = self._tool_query_low_stock(50)
        if not cfg:
            return 'AI 未配置。负库存物料 %d 项，建议核查安全库存。' % len(low)
        prompt = ('以下为负库存/低库存物料，请基于数据给出补货建议与理由：\n%s'
                  % json.dumps(low, ensure_ascii=False))
        messages = [{'role': 'system', 'content': self._build_system_prompt()},
                    {'role': 'user', 'content': prompt}]
        try:
            return self._call_llm(cfg, messages, [])
        except Exception as e:
            _logger.warning('补货建议降级: %s', e)
            return '（AI 暂不可用）负库存 %d 项，建议按安全库存补货。' % len(low)


class AiChatWizard(models.TransientModel):
    _name = 'ai.chat.wizard'
    _description = 'AI 对话助手'

    question = fields.Text(string='你的问题', required=True)
    answer = fields.Text(string='AI 回答', readonly=True)
    session_id = fields.Many2one('ai.chat.session')

    def action_send(self):
        self.ensure_one()
        session = self.session_id or self.env['ai.chat.session'].create({})
        ans = session.ask(self.question)
        self.write({'answer': ans, 'session_id': session.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ai.chat.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
