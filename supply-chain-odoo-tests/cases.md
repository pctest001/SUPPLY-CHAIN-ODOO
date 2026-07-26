# supply-chain-odoo-tests 用例目录与验证指南

> 同步自 `测试工程技术方案.md`。当前版本：**21 条用例**（M1 4 + M2 结构型 7 + M2 业务数值 7 + AI 1 + 多公司 2）。

## 1. 如何验证（拿绿 + 证明有效）

### 1.1 一键运行
```powershell
cd supply-chain-odoo-tests
.\verify.ps1        # 起实例 -> 装模块 -> 跑 pytest -> 打印自愈审计
```
脚本会：起 `db` → 初始化 `test_supplychain` 并安装 `supply_chain_demo,sc_ai` → 起 `odoo`(18069) → 等就绪 → 跑 `pytest -v --junitxml=report.xml` → 打印 `healer_audit.jsonl`。

### 1.2 手动分步
```powershell
cd supply-chain-odoo-tests
docker compose -f docker-compose.test.yml up -d db
docker compose -f docker-compose.test.yml stop odoo        # 避免与初始化抢建表
docker compose -f docker-compose.test.yml run --rm odoo odoo `
  -i supply_chain_demo,sc_ai -d test_supplychain --stop-after-init
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
- 删 PO 审批守卫 `button_confirm` 的 `approval_state` 判断 → `PO-APPROVE` 红。

## 2. 用例目录（21 条）

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

### AI 智能层（1，`tests/test_ai.py`，marker `ai`）
| 用例 | 断言 |
|------|------|
| test_ai_ask_degrades_gracefully | 无 LLM Key 时 `ai.chat.session.ask()` 返回非空降级文本、绝不抛异常（G5 全链路降级） |

### 多公司（2，`tests/test_multi_company.py`，marker `multicompany`）
| 用例 | 断言 |
|------|------|
| test_crossco_user_in_other_company | 跨公司测试用户归属第二家公司 |
| test_pr_company_scoped | 显式 `company_id` 的 PR 被如实记录（公司域写入不变量） |

## 3. 按 marker 筛选
```powershell
python -m pytest -m smoke          # 仅 M1 冒烟
python -m pytest -m business        # 仅 PRD 业务数值
python -m pytest -m "struct or ai"  # 结构型 + AI
```

## 4. 产物（均被 .gitignore 忽略，本地临时）
- `report.xml`：JUnit 报告（CI 也上传）
- `healer_audit.jsonl`：三层自愈审计，每次 session 重置，记录 env/config/data 各层动作
