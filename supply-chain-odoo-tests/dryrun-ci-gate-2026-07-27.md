# Dry-run：CI 门禁实战验证（2026-07-27）

## 目的
本分支仅用于发起一个真实 GitHub PR，实战演练根 `.github/workflows/ci.yml` 中的两道门禁：

- **`req-gate`**：校验 PR 正文/标题是否引用 ≥1 个已登记 REQ。
- **`behavior-fence`**：base（main）与 head（本分支）双实例跑同一批声明式场景 → 差分 → 扣 `intents` 作为回归嫌疑。

## 本分支与 main 的差异
仅新增本说明文件（本 commit）。业务代码零改动。

- `behavior-fence` 差分结果预期：回归嫌疑 ≈ 0 → **PASS**。
- `req-gate`：依赖 PR 正文引用 REQ，需人在 GitHub Web 开 PR 时填入（见下）。

## 开 PR 时的要求（满足 req-gate）
PR 标题/正文必须引用至少 1 个已登记 REQ，例如：

> `REQ-C2-APPROVAL`（采购订单审批，已在 `fence/scenarios/po_approval.json` 与 `intents.yml` 登记）

建议 PR 正文模板：

```
本 PR 实战验证 CI 的 behavior-fence 与 req-gate 门禁。
关联需求：REQ-C2-APPROVAL。
变更：仅新增 dry-run 说明，无业务代码改动。
```

## 预期结果
- CI 触发 `ai-eval` / `req-gate` / `behavior-fence` 等 job。
- 裁判变异集（评测可信度第 3 层）在 `ai-eval` job 内重跑：离线秒级，坏样本漏抓 / 好样本误杀即熔断。
- `behavior-fence` 对本分支差分 ≈ 0 嫌疑 → PASS。
- `req-gate` 校验 PR 正文含 REQ → PASS（前提是正文按上方模板填写）。
