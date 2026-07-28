# 供应链管理系统（MVP）— Odoo 18 二次开发

[![CI](https://github.com/pctest001/SUPPLY-CHAIN-ODOO/actions/workflows/ci.yml/badge.svg)](https://github.com/pctest001/SUPPLY-CHAIN-ODOO/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

流程制造供应链 MVP：主数据 / 采购 / 多仓库存 / 批次效期 + 对话式 AI 助手。
作为面试作品集，覆盖从需求到上线的产品全流程。

## 技术栈

- **Odoo 18.0** (Community) + **PostgreSQL 15**，Docker Compose 一键编排
- 两个自定义模块：
  - `supply_chain_demo`：供应链核心（MVP：主数据 / 采购 / 多仓库存 / 批次效期）
  - `sc_ai`：AI 智能层（F6 对话式助手 / 智能预警解读 / 智能补货建议，LLM + Function Calling，只读白名单；**G7 OWL 侧边聊天面板**：顶栏 AI 按钮 + 右侧滑出面板，复用 ask()）

## 快速开始

```bash
# 1) 克隆/进入本目录后，一键初始化（建库 + 装模块 + 设置可登录的 admin）
./init.sh

# 可选：自定义管理员凭据
ADMIN_LOGIN=admin@example.com ADMIN_PASSWORD='YourPass123' ./init.sh
```

初始化完成后访问 **http://localhost:8069**，使用脚本末尾打印的账号密码登录。

> 默认凭据：**admin@example.com / admin**
> 凭据由模块 `post_init_hook` 用 Odoo 自身哈希（`_set_password()` → pbkdf2_sha512）设置，
> 确保与登录校验完全一致；且该过程**不改动任何安全参数**（如登录失败冷却保持默认）。

## 项目结构

```
supply-chain-odoo/
├── docker-compose.yml          # Odoo 18 + Postgres 15
├── init.sh                     # 可复现初始化（建库+装模块+设 admin）
├── scripts/reset_admin.py      # 可重复重置 admin 凭据（不削弱安全）
├── custom_addons/
│   ├── supply_chain_demo/      # 供应链核心模块
│   └── sc_ai/                  # AI 智能层模块
└── README.md
├── 作品说明.md                # 面试作品集叙事（定位/架构/亮点/STAR）
├── 演示走查脚本.md            # 现场 UI 走查 + 一键自检清单
└── scripts/
    └── h1_e2e.py              # H1 端到端联调（主链路+AI，35/35 PASS，事务内回滚）
```

## 自定义模块说明

### supply_chain_demo（核心 MVP）
- 依赖 `product / purchase / stock / product_expiry`（效期追溯）
- 演示组织：2 工厂（华南工厂 / 华东工厂）+ **每公司双仓**（华南：HNC2 原料仓 / HNF2 成品仓；华东：HDR2 原料仓 / HDC2 成品仓），随模块安装生成
- 提供物料扩展（流程制造自动开启批次+效期+可库存）、**采购申请 PR → 采购订单 PO**（draft→confirmed→done 状态机 + 一键转原生 PO）、**PO 审批流**（approval_state: 待提交→待审批→已审批，未审批禁止确认/收货，记录审批人/时间）、**C3 收货（批次/效期录入）**、**D1 入库/出库**（入向+出向双批次守卫，按批次量化正确可追溯）、**D2 跨仓调拨**（同工厂原料仓↔成品仓互转，事务一致 + 跨仓批次自动可追溯，原生内部调拨天然满足）、**D3 批次/效期拦截**（出向作业绑定「过期批次(lot)」时拒绝验证，不依赖 is_process_mfg，凡过期一律拦截；复用 B4 临期批次作对照）、**D4 负库存/超额收货拦截**（`button_validate` 守卫：出向/内部调拨发出量超过来源库位现有库存即拒；入向作业绑定采购订单行时累计收货超过订购量即拒；均不依赖 is_process_mfg）、**B3 配方主数据**（`sc.recipe`/`sc.recipe.line`：流程制造成品-原料配比+自动占比，物料表单反向展示配方）、**E1 供应商协同**（`sc.supplier.ack` 采购订单交期确认单 + PO 协同状态实时联动 + 登记向导 + 协同工作台）、**B4 演示数据**（每公司双仓 + ~22 中文 SKU 含批次/效期初始库存，3 个临期项供效期拦截演示）、多仓库存、批次效期等基础能力；**F1 库存看板**（standalone 实时 Web 看板：指标卡 + 各仓库存汇总 + 实时库存明细 + 临期预警 + 跨仓调拨，标准库 `http.server` + 直连 `psql` 取数，无第三方依赖，启动 `python3 scripts/inventory_dashboard.py` 后开 `http://localhost:5000`）

### sc_ai（AI 智能层）
- 依赖 `supply_chain_demo`
- 设计要点（对应 PRD 安全与工程素养）：
  - **只读**：所有查询走 Odoo ORM，自动继承当前用户数据权限（ir.rule）
  - **白名单**：LLM 仅可调用 6 个只读工具（query_stock / query_purchase_orders / query_suppliers / query_expiring_lots / query_low_stock / query_supplier_acks），防越权写与提示词注入
  - **密钥不落地**：API Key 仅从环境变量 `SUPPLY_AI_API_KEY` 读取，绝不入库 / 硬编码 / 进前端
  - **降级**：LLM 调用失败/超时，主流程不受影响，提示「AI 暂不可用」

#### 配置 AI（已配置 DeepSeek）
本仓库的 AI Key 通过环境变量 `SUPPLY_AI_API_KEY` 注入（`docker-compose.yml` 的 `odoo` 服务 environment 中以 `${SUPPLY_AI_API_KEY}` 引用，实际值来自本地 `.env`）。`.env` 已被 `.gitignore` 忽略、**绝不入库**，因此公开仓库不含任何真实密钥；配置方法见 `.env.example`。AI 默认配置见 `sc_ai/data/ai_config.xml`（provider=deepseek，model=deepseek-chat）。
未配置 Key 时 AI 自动降级（核心供应链功能不受影响）。要换 Key/模型，复制 `.env.example` 为 `.env` 并修改 `SUPPLY_AI_API_KEY`，或在系统「AI 配置」中调整。

> ⚠️ 安全提示：本仓库为演示/学习用途，使用默认弱凭据（`admin@example.com / admin`、数据库 `odoo/odoo`）。部署到公网前请务必修改所有默认密码。

## 运维脚本

```bash
# 仅重置管理员密码（无需重建库）
docker compose run --rm -v ./scripts:/scripts \
  -e ADMIN_LOGIN=admin@example.com -e ADMIN_PASSWORD=admin \
  odoo python3 /scripts/reset_admin.py

# 查看运行状态
docker compose ps
```

## 自测状态

核心验收点（干净环境端到端自测已通过）：
1. 干净建库后，**无需手动补密码**即可登录（admin@example.com / admin）——凭据由 `post_init_hook` 用 Odoo 自身哈希设置，可复现。
2. 登录直达应用登录页（非数据库管理器）：`docker-compose.yml` 已用 `db-filter=^supplychain$` 锚定单库。
3. 登录失败冷却（防暴力破解）保持 Odoo 默认（10 次 / 60 秒），**未被削弱**。
4. 两个模块与演示组织（华南/华东工厂 + HNC2/HDC2 仓）、AI 菜单/视图/权限（4 模型 + 5 权限）均正确加载。
5. AI 只读工具层 6 个函数均可执行并返回真实数据（含 E1 供应商协同 `query_supplier_acks`）；白名单拒绝越权/未知调用；无 `SUPPLY_AI_API_KEY` 时优雅降级。
6. **C1 采购申请 PR → 采购订单 PO**：`sc.purchase.request` 模型 + 列表/表单视图 + 菜单 + 权限(2 条) 已随模块升级加载；状态机（草稿→已提交→已转PO→已取消）与「提交后一键生成原生 `purchase.order`」逻辑经 `scripts/c1_test.py` 严格自测全部通过（18 项断言，含状态机拦截）。
7. **C2 PO 审批流**：继承 `purchase.order` 叠加 `approval_state`（待提交→待审批→已审批/已驳回），`button_confirm` 守卫未审批禁止确认（含收货作业在确认时生成，故待审态禁止收货）；审批通过记录审批人/时间。经 `scripts/c2_test.py` 严格自测 17 项断言全 PASS（含草稿/待审态确认拦截、已批生成收货作业、驳回重置、C1→C2 联动）。
8. **A4 配置 SUPPLY_AI_API_KEY 并实时联调**：Key 已注入 `docker-compose.yml` 且 `sc_ai` 默认启用 DeepSeek 配置；`scripts/ai_live_test.py` 用真实 Key 实调 DeepSeek 成功返回（非降级），AI 对话式助手端到端可用（G1 联调通过）。
9. **PO 页面全中文化**：新增 6 个继承视图（`supply_chain_demo/views/supply_chain_views.xml`），覆盖原生 `purchase` 模块英文标签——PO 表单头部按钮、标题（询价单/采购订单）、字段（供应商/币种/订单日期/预计到达日/审批日期/审批信息）、行内明细表头（产品/描述/数量/单价/税额/金额/计划日期/已收货/已开票/单位/折扣%）、主 PO 列表与搜索、独立行列表与搜索。已 `docker compose run -u supply_chain_demo` 升级并重启 odoo；`scripts/verify_zh_shell.py` 经 `odoo shell get_views` 校验表单/列表/搜索中文全 PASS。
10. **C3 收货（批次/效期录入）**：流程制造物料（`is_process_mfg`）标记时自动 `tracking=lot` + `use_expiration_date=True` + `is_storable=True` + 默认保质期；收货（入向 picking）守卫——流程制造明细缺批次号即拒绝验证（UserError），效期由原生 `product_expiry` 记录到 `stock.lot` 并可经 `stock.quant` 追溯。收货明细「批次号/效期」与批次表单「效期/移除日期」已中文化。经 `scripts/c3_test.py` 严格自测 **15/15 通过**（含自动批次+效期配置、PO→入向收货、写 lot 并记录效期、quant 入库 +100 且效期可追溯、缺批次被拒、中文视图校验）。
11. **D1 入库/出库**：在 C3 收货守卫基础上扩展 `stock.picking` 双守卫——入向(incoming) 流程制造缺批次号拒绝验证，出向(outgoing) 流程制造缺批次(lot_id) 拒绝发货（强制绑定到具体收货批次，保证按批次量化正确与可追溯）。端到端：入库 PO→收货(+100, 批次+效期)→出库交付(−30, 指定批次)→剩余 +70，按批次量化一致。经 `scripts/d1_test.py` 严格自测 **20/20 通过**（含入库写 lot+quant、出库按批次 write-off、入库/出库缺批次均被拒、中文视图校验）；`scripts/d1_demo.py` 已生成可检视演示链路 `WH/IN/00034 → WH/OUT/00012 → WH/Stock 库存 70.0（按批次）`。
12. **B4 演示数据扩充**：每公司双仓（华南 HNC2原料/HNF2成品、华东 HDR2原料/HDC2成品）；灌入 **22 个中文 SKU**（15 流程制造含批次+效期 / 7 普通可储存），按仓分布种入初始库存（经 `stock.quant` 库存调整落账）；含 3 个临期批次（效期 2026-08-27 / 09-06 / 09-21）供 D3 效期拦截演示。经 `scripts/b4_verify.py` 新会话实查确认：4 仓归属正确、22 SKU、各仓库存为正（HNC2 19700 / HNF2 2300 / HDR2 4800 / HDC2 5200）、临期批次齐全。`scripts/b4_demo_data.py` 幂等可重跑（commit 持久化）。
13. **D2 跨仓调拨（事务一致）**：同工厂内「原料仓↔成品仓」互转，新增 4 条内部调拨作业类型 `HNCF/HNFC`(华南 HNC2↔HNF2)、`HDCF/HDFC`(华东 HDR2↔HDC2)，显式绑定序列与两端 `lot_stock_id`。演示调拨 `HNCF/00001`（食品级柠檬酸 100，批次 LOT-HNC2-01，HNC2/Stock→HNF2/Stock）验证后来源 −100、目的 +100、**两仓合计守恒**，目的库存绑定原批次（跨仓批次可追溯）。内部调拨不额外加守卫——Odoo 在 `action_confirm` 自动按来源 quant 携带 `lot_id`，原生批次可追溯。经 `scripts/d2_test.py` 严格自测 **17/17 通过**（含类型正确、按批次量化守恒、自动填批、普通物料无批次调拨）。
14. **D3 批次/效期拦截**：在出向(outgoing)守卫中追加效期校验——出库作业任一明细绑定 `stock.lot` 的 `expiration_date`（`product_expiry` 字段，Datetime）早于今日即 `UserError` 拒绝验证；**不依赖 `is_process_mfg`**，凡出向绑定「过期批次」一律拦截（含非流程制造但启用批次追踪的物料）。复用 B4 临期批次（香精香料-A型/去离子水/消毒液2L，效期 2026-08-27~09-21，均为未来到期）作为"未过期可正常出库"对照。经 `scripts/d3_test.py` 严格自测 **12/12 通过**（含过期批次出向被拦截且库存不变、未过期批次正常出库并量化正确、非流程制造+过期批次同样被拦截）；`scripts/d3_demo.py` 已生成可检视演示：过期批次 `LOT-EXPIRED-DEMO`(效期 2025-01-01) + 出向交付单 `HNC2/OUT/00008`（绑定该批次），在 UI 点「验证」可复现拦截。
15. **D4 负库存/超额收货拦截**：在 `button_validate` 守卫新增两类拦截——①**负库存**（出向 outgoing / 内部调拨 internal）：来源库位现有库存（`stock.quant` 按 product+location+lot 求和）小于本次发出量即 `UserError` 拒绝验证，提示含物料/库位/现有量/发出量；②**超额收货**（入向 incoming 且绑定 `purchase_line_id`）：累计已收货 + 本次到货 > 订购量(product_qty) 即 `UserError` 拒绝验证。两类均**不依赖 `is_process_mfg`**，与 C3/D1/D3 守卫独立并存。经 `scripts/d4_test.py` 严格自测 **17/17 通过**（含出向超量被负库存拦截且库存不变、正常出向量化正确、内部调拨超量被拦截、入向超额收货被拦截且作业未 done、正常收货不受限）；`scripts/d4_demo.py` 已生成可检视演示：负库存出向单 `HNC2/OUT/00013`（发出 100 > 库存 30）、超额收货 PO `D4-PO-OVER-001`（订购 5 / 到货 50），在 UI 点「验证」均可复现拦截，commit 持久化且幂等。
16. **F1 库存看板**：standalone 实时 Web 看板（无第三方依赖）。后端标准库 `http.server`，数据经 `docker compose exec db psql` 直连 `supplychain` 库（绕过 Odoo ORM 多公司上下文限制），前端内联 HTML/CSS/SVG（无 CDN，离线可用）。含五大块：①指标卡（仓库数 / SKU 数 / 库存总量 / 临期批次≤60天 / 已过期批次）；②各仓库库存汇总条形图（4 个供应链仓库 HNC2/HNF2/HDR2/HDC2）；③实时库存明细（按仓/物料/批次）；④临期/过期预警（高亮 D3 演示过期批次 LOT-EXPIRED-DEMO 与 B4 埋的 3 个临期项）；⑤跨仓调拨作业（D2 演示 HNCF/00001 等）。实查：`http://localhost:5000` 返回 4 仓库存（19660/2400/4800/5200）、指标 4/23/32060/3/1、临期 3 + 过期 1、调拨 1。启动：`python3 scripts/inventory_dashboard.py` → 浏览器开 `http://localhost:5000`（依赖 `db` 容器与 docker 可用）。
17. **B3 配方主数据**：新增 `sc.recipe`/`sc.recipe.line`——流程制造成品（domain 限定 `is_process_mfg`）关联若干可库存原料、记录用量并自动计算「总用量 / 占比%」；校验空明细、用量≤0、原料=成品均 `UserError` 拒绝；成品物料表单新增「配方」页反向展示并可下钻；菜单「供应链管理 / 主数据 / 配方（BOM）」。经 `scripts/b3_test.py` 严格自测 **12/12 通过**（含序列 RCP/、总用量与占比计算、反向可见、三类约束拦截）；`scripts/b3_demo.py` 已生成可检视演示配方 `RCP/2026/00014`（柠檬味苏打水 330ml = 去离子水82/葡萄糖浆12/柠檬酸4/香精2，总量100），commit 持久化且幂等。
18. **E1 供应商协同（交期确认）**：新增 `sc.supplier.ack`（供应商交期确认单：状态 pending/confirmed/rejected、确认交期、备注、确认人/时间），采购订单扩展 `ack_ids` 反向关联与 `supplier_ack_state`/`supplier_committed_date`（**实时从全部确认记录计算**，向导或协同工作台录入均一致），`action_register_supplier_ack()` 登记向导 + `_create_or_update_ack()` 幂等；菜单「供应链管理 / 供应商协同 / 交期确认」工作台；并深化 AI——`sc_ai` 白名单 + 工具 + schema 新增 `query_supplier_acks`（AI 可回答「某供应商哪些 PO 尚未确认交期」）。经 `scripts/e1_test.py` 严格自测 **15/15 通过**（含序列 SACK/、状态联动、确认/驳回、幂等、AI 工具读到数据）；`scripts/e1_demo.py` 已生成可检视演示 `SACK/2026/00005`（PO P00024 / 供应商 百世 / 已确认交期 2026-07-30），commit 持久化且幂等。
19. **G7 OWL 侧边聊天面板**：`sc_ai` 新增 OWL 组件 `AiChatSystray`（顶栏 systray AI 按钮 + 右侧滑出面板，含消息列表 / 输入框 / 发送 / 新对话 / 降级提示），复用后端 `ai.chat.session.ask()`（只读 / 继承 `ir.rule` / 白名单 / 降级天然生效）；新增 3 个面板接口 `get_or_create_session` / `chat` / `new_session`（经 `/web/dataset/call_kw` 调用）。资产注册进 `web.assets_backend`（`sc_ai.scss` + `ai_chat_panel.xml` + `ai_chat_panel.js` + `sc_ai.js`），已验证组件代码完整打包进后台 `web.assets_web.min.js`；真实 HTTP 走查：登录 → GET /web 触发资产编译无报错 → `call_kw` 调 `chat` 返回真实 DeepSeek 库存答复（约 1770 字）。浏览器硬刷新（Ctrl+Shift+R）即可见顶栏 AI 按钮与侧边面板。

自测脚本见 `scripts/`：`init.sh`(可复现初始化)、`verify_login.py`(RPC 登录)、`form_login.py`(表单登录)、`verify_db.sql`(DB 验收)、`ai_test.py`(AI 工具)、`c1_test.py`(C1 采购申请→PO)、`c2_test.py`(C2 审批流+AI 配置校验)、`c3_test.py`(C3 收货批次/效期)、`d1_test.py`(D1 入库/出库端到端)、`d1_demo.py`(D1 演示链路持久化)、`d2_demo.py`(D2 跨仓调拨类型+演示调拨持久化)、`d2_test.py`(D2 跨仓调拨 17 项端到端)、`d3_demo.py`(D3 过期批次+出向交付单持久化，UI 可复现拦截)、`d3_test.py`(D3 效期拦截 12 项端到端)、`d4_demo.py`(D4 负库存/超额收货演示持久化，UI 可复现拦截)、`d4_test.py`(D4 负库存+超额收货 17 项端到端)、`b3_test.py`(B3 配方主数据 12 项端到端)、`b3_demo.py`(B3 演示配方持久化，UI 可查)、`e1_test.py`(E1 供应商协同 15 项端到端)、`e1_demo.py`(E1 演示交期确认持久化，UI 可查)、`b4_demo_data.py`(B4 演示数据灌入)、`b4_verify.py`(B4 数据验证)、`inventory_dashboard.py`(F1 实时库存看板服务：http.server + 直连 psql，开 http://localhost:5000)、`ai_live_test.py`(A4 实时调 DeepSeek)、`reset_admin.py`(可重复重置凭据)、`inspect_type.py`(排查用)、`supplychain_queries.sql`(DBeaver 常用查询：实时库存/各仓汇总/临期预警/跨仓调拨/流程制造物料/出入库/公司仓库)。

## 自动化测试

两套互补的自动化测试，详见 `supply-chain-odoo-tests/`：

- **RPC 黑盒测试（40+ 用例）**：经 XML-RPC/JSON-RPC 驱动 Odoo，验证业务守卫、状态机、PRD 数值、AI、多公司、收货、产品扩展、日志追踪；含行覆盖率度量 + Mutation 反假绿门禁。跑在隔离实例（18069）。
- **UI 自动化（Playwright 黑盒浏览器）**：真实浏览器驱动 Odoo 前端，验证页面渲染、中文化、菜单导航、字段标签、页签惰性渲染等呈现层质量。当前 4 条用例（对应 `演示走查脚本.md` 的 TC-B01 登录中文化、TC-B02 流程制造），跑在当前主实例 8069（容器内装 Chromium，宿主机代理白名单无法装浏览器）。一键运行：`.\supply-chain-odoo-tests\run_ui_tests.ps1`。
- **L4 AI 评测 + 有效性度量**：`eval/` 包对 AI 助手做金标准评测（`eval_set.json` 14 用例）与可插拔裁判（RuleJudge / LLM-as-Judge），量化准确率 / 幻觉率 / 拒答率 / 安全违规率，并落地 §8 有效性度量（北极星逃逸率、拦截率、金标准 kappa 校准）。纯标准库、离线可跑：`python -m eval.run_eval --mode sim --fail-under 80` 与 `python -m eval.effectiveness`。详见 `supply-chain-odoo-tests/测试工程技术方案.md` §4.7 与 `supply-chain-odoo-tests/质量体系架构.md`。
- **L6 生产监控与治理**：`prodmon/` 包在线采样生产 `ai.chat.session`，经 `ProductionJudge` 跑安全违规 / 拒答异常 / 幻觉信号 / **工具执行准确率 tool_exec_acc**（v3.4 新增，基于 `ai.chat.tool.log` 的 status 判定 ok/error/blocked，blocked 单列安全指标不计入失败）信号（无需金标准），对比 L4 回归基线 `eval_baseline.json` 触发告警；`sc_ai` 会话落 `prompt_version` / `model_used` 版本留痕，bad case 自动回流 L4 回归。live 模式接真实 SUT：`sc_ai` 新增 `ai.chat.tool.log` 持久化每次工具调用，`RpcCollector` 精确回填 tool_calls/tool_results/tool_statuses 精测工具准确率与安全；告警经 `prodmon/notify.py` 推送钉钉/企微/Slack webhook（`--notify` / `PROD_ALERT_WEBHOOK`，无配置降级 dry-run 审计），钉钉告警默认 @负责人手机号（`--at-mobiles` / `PROD_ALERT_AT_MOBILES` 可改，传 `[]` 关闭），形成"监控 → bad case → L4 回归 → prompt 迭代"闭环——且已用真实 LLM 完整演练一轮：L6 抓到的真实注入漏拒 case（PROD-61）回流评测集，prompt v1→v2 后 live 评测 15/15 满分、攻击重放被正确拒绝（详见测试方案 §4.8.3）。幻觉哨兵可插拔：默认启发式，`PROD_LLM_JUDGE=1` 时升级 LLM-as-Judge 复用 DeepSeek（见 §4.8.5）；报告统一呈现见 §4.9（`python -m reports.build` 生成自包含 HTML 仪表盘 + Markdown 周报）。纯标准库、离线可跑：`python -m prodmon.run_monitor --mode sim --fail-under 80`（另有 `tests/test_prodmon.py`）。定时巡检双通道：CI 每日 cron 跑离线门禁（ai-eval + prod-monitor，重型任务定时跳过）+ 本机定时任务每日对真实 SUT 跑 live 巡检。详见 `supply-chain-odoo-tests/测试工程技术方案.md` §4.8 与 `supply-chain-odoo-tests/质量体系架构.md`。
