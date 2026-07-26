# supply-chain-odoo-tests 用例目录与验证指南

> 同步自 `测试工程技术方案.md`。当前版本：**59 条用例**（M1 4 + M2 结构型 7 + M2 业务数值 7 + AI 降级 1 + AI 非降级 6 + 多公司 2 + 收货/批次 7 + 产品扩展 3 + 日志追踪 3 + 供应商确认单动作 7 + 采购订单审批 7 + 采购申请 5）。

## 1. 如何验证（拿绿 + 证明有效）

### 1.1 一键运行
```powershell
cd supply-chain-odoo-tests
.\verify.ps1        # 起实例 -> 装模块 -> 跑 pytest -> 打印自愈审计
```
脚本会：起 `db` → 初始化 `test_supplychain` 并安装 `supply_chain_demo,sc_ai,sc_log_trace` → 起 `odoo`(18069) → 等就绪 → 跑 `pytest -v --junitxml=report.xml` → 打印 `healer_audit.jsonl`。

### 1.2 手动分步
```powershell
cd supply-chain-odoo-tests
docker compose -f docker-compose.test.yml up -d db
docker compose -f docker-compose.test.yml stop odoo        # 避免与初始化抢建表
docker compose -f docker-compose.test.yml run --rm odoo odoo `
  -i supply_chain_demo,sc_ai,sc_log_trace -d test_supplychain --stop-after-init
docker compose -f docker-compose.test.yml up -d odoo
python -m pytest -v --junitxml=report.xml
```
> 关键坑：初始化（`run --rm ... -i ...`）时**不要**让主 `odoo` 服务同时跑，否则两者抢同一数据库建表会互相干扰。

### 1.3 只看用例不执行（不连实例）
```powershell
python -m pytest --collect-only -q
```

### 1.4 证明"不是假绿"（变异验证 / A2）
故意改 `custom_addons` 中一处状态机或 `constrains`，重启 odoo 重跑，对应用例应变红，再还原：
- 改 `sc.purchase.request.action_submit` 不置 `confirmed` → `PR-SUBMIT` 红；
- 删 `sc.recipe` "至少一种原料" `constrains` → `W-RECIPE-LINE` 红；
- 删 PO 审批守卫 `button_confirm` 的 `approval_state` 判断 → `PO-APPROVE` 红；
- 改 `sc.supplier.ack.action_confirm` 不置 `confirmed` → `ACK-CONFIRM` 红（M4）；
- 删 `purchase.order.button_confirm` 审批守卫 → `PO-CONFIRM-GUARD` 红（M5）；
- 删 `sc.purchase.request.action_generate_po` 的『无供应商』守卫 → `PR-GENPO-NOPARTNER` 红（M6）。

### 1.5 CI 已内置 mutation 门禁（自动化 A2，6 个变异点）
门禁逻辑收敛在 `mutation_gate.py`（本地/CI 双用，跨平台）。对每个变异点：
精确注入 → `restart odoo` 重载 → 只跑对应用例（**期望变红**）→ `finally` 还原源码；
任一变异未被抓住（用例仍绿）=> 测试过弱 => 退出码非 0 => CI 失败。

| ID | 变异内容 | 应抓住它的用例 |
|----|---------|---------------|
| M1-PR-SUBMIT | `action_submit` 提交后不置 `confirmed`（状态机断裂） | `PR-SUBMIT` |
| M2-RCPT-NOLOT | C3 收货批次守卫被绕过（无批次也放行） | `test_rcpt_nolot_rejected` |
| M3-RECIPE-QTY | 配方用量约束 `<=0` 松成 `<0`（零用量放行） | `C-RECIPE-QTY` |
| M4-ACK-CONFIRM | `action_confirm` 确认后不置 `confirmed`（状态机断裂） | `ACK-CONFIRM` |
| M5-PO-CONFIRM-GUARD | 删 `button_confirm` 审批守卫（未审批也能确认订单） | `PO-CONFIRM-GUARD` |
| M6-PR-GENPO-NOPARTNER | 删 `action_generate_po` 的『无供应商』守卫（无供应商也能生成 PO） | `PR-GENPO-NOPARTNER` |

本地复现（在已起实例上，约 3-5 分钟）：
```powershell
cd supply-chain-odoo-tests
python mutation_gate.py    # PASS = 全部 6 个变异均被抓住
```
最近一次本地结果：`caught=['M1-PR-SUBMIT','M2-RCPT-NOLOT','M3-RECIPE-QTY','M4-ACK-CONFIRM','M5-PO-CONFIRM-GUARD','M6-PR-GENPO-NOPARTNER'] missed=[]`。

### 1.6 代码行覆盖率（custom_addons）
黑盒 RPC 用例跑在宿主机、被测代码在 Odoo 容器内，`coverage run -m odoo` 无法测——Odoo 常驻 + 线程/gevent + `--dev` 重载子进程会让真正处理 RPC 的进程不在 coverage 之下（实测 `line_bits=0`，假 0%）。本工程用**子进程自动注入**方案拿到真实覆盖率：
- `covdata/sitecustomize/sitecustomize.py` + 环境变量 `COVERAGE_PROCESS_START=/mnt/covdata/.coveragerc`、`PYTHONPATH=/mnt/covdata/sitecustomize`（见 `docker-compose.test.yml`）：让**每个** python 进程（含重载子进程）启动时自动 `coverage.process_startup()`，`parallel=true` 各写独立数据文件；
- `.coveragerc` 里 `concurrency = thread,gevent`（同时兼容线程与 gevent）、`sigterm = true`（`docker stop` 的 SIGTERM 触发落盘，不依赖 Odoo atexit）；
- 停止后 `coverage combine` 合并，**报告在容器内出**（posix 路径与数据一致；在 Windows 宿主机直接出会因 `/mnt` 反斜杠映射对不上而误报 0%）。

一键采集：
```powershell
cd supply-chain-odoo-tests
powershell -ExecutionPolicy Bypass -File run_coverage.ps1
# 文本报告：cov_report.txt；HTML：covdata/htmlcov/index.html
```

最近一次结果（59 条用例，**TOTAL 85.1%**，645 语句 / 96 未覆盖；此前 21 条时为 51.5%）：

| 模块文件 | Stmts | Miss | Cover | 此前 |
|---|---|---|---|---|
| `sc_ai/models/ai_models.py` | 217 | 30 | **86.2%** | 48.8%（仅降级）|
| `sc_log_trace/__init__.py` | 44 | 6 | **86.4%** | 0%（未安装）|
| `supply_chain_demo/models/stock_receipt_lot.py` | 58 | 9 | **84.5%** | 10.3% |
| `supply_chain_demo/models/recipe.py` | 69 | 13 | 81.2% | 81.2% |
| `supply_chain_demo/models/product_ext.py` | 28 | 6 | **78.6%** | 32.1% |
| `supply_chain_demo/models/purchase_request.py` | 73 | 8 | **89.0%** | 76.7% |
| `supply_chain_demo/models/odoo_model_demo.py` | 24 | 6 | 75.0% | 75.0% |
| `supply_chain_demo/models/purchase_order_approval.py` | 32 | 0 | **100.0%** | 71.9% |
| `supply_chain_demo/models/supplier_ack.py` | 69 | 0 | **100.0%** | 66.7% |

CI 中已设 `--fail-under=70` 覆盖率门禁（实测 85.1%，留 ~15pt 余量防抖动）。
剩余未覆盖主要是：UI onchange、报表/看板 action 等黑盒 RPC 难驱动路径（此前 §4.4 归为死区的 `supplier_ack` 邮件通道经实测并不存在——其 compute/action/wizard 均为纯逻辑，已通过 RPC 全量覆盖到 100%）。

> 补测过程中顺带抓到一个真 bug：`ai_models._tool_query_expiring_lots` 误用
> `stock.lot.quantity`（Odoo 18 应为 `product_qty`），此前只测降级路径从未暴露，
> mock LLM 用例第一次驱动工具执行即崩，已修复。

## 2. 用例目录（40 条）

### M1 冒烟（4，`tests/test_bootstrap.py`，marker `smoke`）
| 用例 | 断言 |
|------|------|
| test_odoo_reachable | 实例可达 + admin 登录成功 |
| test_core_models_installed | 核心模型已装（sc.purchase.request / sc.recipe / sc.supplier.ack / ai.config） |
| test_two_companies_exist | 多公司前置（华南/华东） |
| test_cross_company_user_ready | 跨公司测试用户就绪 |

### M2 结构型（7，`tests/test_generated_struct.py`，marker `struct`，源自 `metagen.all_cases()`）
| ID | 期望（SUT 应拒绝/拦截） | 类型 |
|----|------------------------|------|
| G-PR-SUBMIT | 无明细 PR 提交应被拒 | GuardCase |
| G-PR-GENPO | 草稿态 PR 生成 PO 应被拒 | GuardCase |
| C-RECIPE-QTY | 配方用量≤0 应被拒 | CreateViolationCase |
| C-RECIPE-CMP | 原料=成品应被拒 | CreateViolationCase |
| W-RECIPE-LINE | 配方清空明细应被拒 | WriteViolationCase |
| G-ACK-CONF | 供应商确认交期缺失应被拒 | CreateThenActionCase |
| S-PR-STATE | PR 非法 state 值应被拒 | SelectionViolationCase |

### M2 业务数值型（7，`tests/test_generated_business.py`，marker `business`）
- 规则元数据校验（3）：test_prd_rules_loaded / test_prd_rule_ids_unique / test_prd_rule_source_traced
- PRD 状态流断言（4，源自 `prd_rules.PRD_RULES` + `metagen`）：

| ID | 期望（PRD 规定） | 来源 |
|----|-----------------|------|
| PR-SUBMIT | 提交后 PR 状态=`confirmed` | 验收清单 §1 / 作品说明 B 采购申请 |
| PR-GENPO | 生成 PO 后=`done` 且 `po_ids` 非空；**并断言原生 purchase.order 供应商/明细/公司正确** | 同上（B6 深化） |
| ACK-CONFIRM | 确认交期后=`confirmed` | 验收清单 §2 E1 / 作品说明 E |
| PO-APPROVE | 未审批确认被拒；提交后=`pending`；审批后=`approved` 且记录审批人 | 验收清单 §2 C2 / 作品说明 C |

### AI 智能层——降级（1，`tests/test_ai.py`，marker `ai`）
| 用例 | 断言 |
|------|------|
| test_ai_ask_degrades_gracefully | 无 LLM Key 时 `ai.chat.session.ask()` 返回非空降级文本、绝不抛异常（G5 全链路降级） |

### AI 智能层——非降级（6，`tests/test_ai_llm_mock.py`，marker `ai`）
宿主机起 OpenAI 兼容 mock server，容器经 `host.docker.internal` 回连（不可达则整组 skip）。
Key 红线不破：`api_key_env` 指向容器内必存在的 `PATH`，Key 内容对 mock 无意义。
| 用例 | 断言 |
|------|------|
| test_ask_function_calling_full_chain | 两轮 LLM + 8 个工具调用（6 白名单工具全触发 + 注入拒绝 + 坏参数兜底）后返回最终回答并落消息 |
| test_chat_panel_api | `chat()`（OWL 侧边面板）返回 id/answer/messages |
| test_chat_blank_question_shortcircuit | 空问题短路，不落消息 |
| test_session_panel_lifecycle | `new_session` / `get_or_create_session` 会话生命周期 |
| test_interpret_alerts_with_llm | 预警解读走 LLM 路径（非降级） |
| test_suggest_replenishment_with_llm | 补货建议走 LLM 路径（非降级） |

### 收货/批次/出库守卫（7，`tests/test_receipt_lot.py`，marker `receipt`）
| 用例 | 断言（验收清单 C3/D1/D3/D4） |
|------|------|
| test_rcpt_nolot_rejected | C3：流程制造收货未录批次 -> 拒绝验证 |
| test_rcpt_noexp_rejected | C3：录批次但缺效期 -> 拒绝验证 |
| test_rcpt_ok_lot_traceable | 正向：批次+效期齐全 -> 验证通过，`stock.lot` 落效期，按批次在库量=5 |
| test_rcpt_over_po_qty_rejected | D4：PO 订 5 收 8 -> 超额收货拦截（全链路：PO 审批->确认->收货） |
| test_out_nolot_rejected | D1：出库不指定批次 -> 拒绝 |
| test_out_expired_lot_rejected | D3：过期批次出库 -> 拒绝 |
| test_out_negative_stock_rejected | D4：零库存出 5 -> 负库存拦截 |

### 产品扩展（3，`tests/test_product_ext.py`，marker `struct`）
| 用例 | 断言 |
|------|------|
| test_create_process_mfg_auto_tracking | create 标记流程制造 -> 自动 lot 追踪+效期+可库存+保质期 365 |
| test_create_normal_not_affected | 普通物料不被强制追踪 |
| test_write_upgrade_to_process_mfg | write 后补标记（含 filtered 分支）同样自动启用 |

### 日志追踪（3，`tests/test_log_trace.py`，marker `logtrace`）
| 用例 | 断言 |
|------|------|
| test_module_installed | `sc_log_trace` 处于 installed（此前 0% 覆盖根因 = 没装） |
| test_error_response_carries_trace_id | JSON-RPC 错误响应 `data.trace_id` 为 8 位 hex |
| test_trace_id_unique_per_request | 两次请求 trace_id 不同（按请求隔离） |

### 多公司（2，`tests/test_multi_company.py`，marker `multicompany`）
| 用例 | 断言 |
|------|------|
| test_crossco_user_in_other_company | 跨公司测试用户归属第二家公司 |
| test_pr_company_scoped | 显式 `company_id` 的 PR 被如实记录（公司域写入不变量） |

### 供应商确认单动作（7，`tests/test_supplier_ack.py`，marker `supplierack`）
| 用例 | 断言（验收清单 §2 E1 / 作品说明 E 供应商协同） |
|------|------|
| test_ack_reject | `action_reject` 置 `rejected` 且写入驳回原因 |
| test_po_supplier_ack_compute | 确认后 PO 的 `supplier_ack_state`/`supplier_committed_date` 被 compute 出 |
| test_po_register_supplier_ack_action | `action_register_supplier_ack` 返回打开 `sc.supplier.ack.wizard` 的 act_window 且预置 `default_po_id` |
| test_ack_wizard_confirm_update | 向导确认（PO 已有 ack）经 `_create_or_update_ack` 更新为 `confirmed` |
| test_ack_wizard_confirm_create | 向导确认（PO 无 ack）经 `_create_or_update_ack` 新建为 `confirmed` |
| test_ack_wizard_reject_create | 向导拒绝（PO 无 ack）经 `_create_or_update_ack` 新建为 `rejected` |
| test_ack_wizard_reject_update | 向导拒绝（PO 已有 ack）经 `_create_or_update_ack` 更新为 `rejected` |

### 采购订单审批流（7，`tests/test_po_approval.py`，marker `poapproval`）
| 用例 | 断言（验收清单 §2 C2 / 作品说明 C 采购审批） |
|------|------|
| test_po_approval_reject | `action_reject` 置 `rejected` |
| test_po_approval_reset | `action_reset_approval` 置 `draft` |
| test_po_approve_guard_not_pending | draft 调 `action_approve` 抛『待审批』UserError |
| test_po_reject_guard_not_pending | draft 调 `action_reject` 抛『待审批』UserError |
| test_po_submit_guard_no_line | 无明细 `submit` 抛『采购明细』UserError |
| test_po_submit_guard_zero_amount | 金额 0 `submit` 抛『金额为 0』UserError |
| test_po_confirm_guard_not_approved | 未审批 `button_confirm` 抛『尚未通过审批』UserError（M5 守卫） |

### 采购申请 PR（5，`tests/test_purchase_request.py`，marker `purchaserequest`）
| 用例 | 断言（验收清单 §2 C2 / 作品说明 C 采购审批前置） |
|------|------|
| test_pr_generate_po_no_partner | 已提交无供应商 `genpo` 抛『请先选择供应商』UserError（M6 守卫） |
| test_pr_cancel | `action_cancel` 置 `cancel` |
| test_pr_reset | `action_reset` 置 `draft` |
| test_pr_view_pos_with_po | `action_view_pos` 返回打开 `purchase.order` 的 act_window + 预置 domain |
| test_pr_view_pos_no_po | 无关联 PO 时 `action_view_pos` return None（Odoo 18 XML-RPC 不序列化 None，服务端执行该分支后由 marshaller 抛错，代码行仍覆盖） |

## 3. 按 marker 筛选
```powershell
python -m pytest -m smoke          # 仅 M1 冒烟
python -m pytest -m business        # 仅 PRD 业务数值
python -m pytest -m "struct or ai"  # 结构型 + AI
python -m pytest -m supplierack      # 仅供应商确认单动作
python -m pytest -m poapproval         # 仅采购订单审批流动作
python -m pytest -m purchaserequest    # 仅采购申请动作/守卫
```

## 4. 产物（均被 .gitignore 忽略，本地临时）
- `report.xml`：JUnit 报告（CI 也上传）
- `healer_audit.jsonl`：三层自愈审计，每次 session 重置，记录 env/config/data 各层动作
