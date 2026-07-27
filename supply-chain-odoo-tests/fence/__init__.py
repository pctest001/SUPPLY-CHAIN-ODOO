"""行为围栏（Behavior Fence）——变更安全三支柱之支柱一。

同一批声明式场景在 base / head 双实例上各跑一遍，采集全部可观测输出，
差分后扣除本次意图清单（intents.yml），剩余差异即回归嫌疑。

模块：
  context.py   双端上下文构建（复用 healer 幂等数据前置 + 库存上下文）
  engine.py    场景执行引擎（声明式步骤 + 领域宏 + 三类观测采集，输出 raw capture）
  runner.py    CLI：对指定 target 跑场景库，输出 captures/<target>_<run_id>.json
  scenarios/   场景库（*.json，每文件一组场景；id 全局唯一）
  captures/    运行产物（raw capture，git 不入库）

  normalize.py 归一化（按语义位置结构化清洗 id/m2o/domain/单号/日期，禁止数值猜 id）
  diff.py      差分引擎：归一化后对比两份 capture -> diff_report.json（有差异 exit 1）

  intents.yml  本次变更意图清单（每条必须挂 req+reason；合并后清空回 []）
  verdict.py   裁决器：diff − intents = 回归嫌疑；嫌疑>0 exit 1 禁止合并

base 实例由 docker-compose.base.yml -p fence-base 拉起（28069/5434，
FENCE_BASE_ADDONS 指向 base 版本代码）。CI 接入见 .github/workflows/ci.yml
的 behavior-fence job（仅 PR 触发）。
标准流程：双端同一 --run-id 各跑 runner -> fence.diff -> fence.verdict。
P3 待建：kb/ 薄存储 + PR 门禁（REQ 关联）。P4 待建：报告卡片 + 考古工具箱首件。
"""
