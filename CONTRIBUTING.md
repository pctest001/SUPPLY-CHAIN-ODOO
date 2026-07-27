# 贡献指南（CONTRIBUTING）

欢迎参与本供应链 Odoo（supply-chain-odoo）项目。本文说明本地环境、测试运行方式与协作约定。

## 1. 项目结构

```
custom_addons/               # Odoo 自定义模块（supply_chain_demo / sc_ai / sc_log_trace）
docker-compose.yml           # 主实例（:8069），挂载 custom_addons
init.sh                      # 一键初始化数据库 + 安装模块
supply-chain-odoo-tests/     # 自动化测试工程（黑盒，不 import odoo）
  docker-compose.test.yml    # RPC 测试隔离实例（:18069，库名 test_supplychain）
  tests/                     # RPC 黑盒用例（59 条，经 XML-RPC 驱动）
  ui_tests/                  # UI 自动化用例（Playwright，跑在 Odoo 容器内连 :8069）
  src/                       # 测试客户端 + 三层自愈（env/config/data）
  verify.ps1 / run_coverage.ps1 / run_ui_tests.ps1  # 本地一键脚本
supply-chain-odoo-tests/测试工程技术方案.md  # 测试架构与黑盒原则
```

## 2. 本地运行

### 启动主实例
```bash
cp .env.example .env          # 填入 SUPPLY_AI_API_KEY（可选，缺省 AI 自动降级）
docker compose up -d
./init.sh                    # 建库并安装 supply_chain_demo,sc_ai
```
访问 http://localhost:8069 ，默认账号 `admin@example.com / admin`。

### 跑 RPC 黑盒测试（隔离实例 :18069）
```powershell
cd supply-chain-odoo-tests
.\verify.ps1                 # 起实例 -> 装模块 -> pytest -> 打印自愈审计
```

### 跑 UI 自动化（容器内 Playwright，连 :8069）
```powershell
cd supply-chain-odoo-tests
.\run_ui_tests.ps1
# 首次需容器内装浏览器（见脚本注释）：
# docker compose exec -u root odoo bash -c "pip install -q --break-system-packages pytest playwright pytest-playwright && python3 -m playwright install chromium && python3 -m playwright install-deps chromium"
```

## 3. CI

推送到 `main` 或开 PR 会触发 GitHub Actions（`.github/workflows/ci.yml`）：
- **rpc-tests**：起隔离实例 → 装模块 → 外部 pytest 驱动（生成 `report.xml` 产物）。
- **ui-tests**：主实例 → 容器内装 Playwright/Chromium → 复制 `ui_tests` 进容器 → 跑浏览器用例。

> 注：本机若处于受限网络（仅白名单域名可通），容器外无法装浏览器内核，UI 测试只能在可直连外网的 Odoo 容器内运行——与 CI 行为一致。

## 4. 协作约定

- **黑盒红线**：自动化测试不得 `import odoo`、不得修改 SUT 业务代码；发现的界面/数据问题以文档或 Issue 提出，由人工决策。
- **密钥**：真实密钥只在本地 `.env`（已被 `.gitignore` 忽略），绝不提交；CI 中 AI 缺省自动降级。
- **默认凭据**：`admin@example.com / admin`、数据库 `odoo/odoo` 为演示用途，公网部署前请修改。
- **提交**：保持原子提交、写明动机；文档与代码改动尽量分开。
- **许可证**：本项目采用 MIT（见 `LICENSE`），提交即视为同意以该许可证分发你的贡献。
