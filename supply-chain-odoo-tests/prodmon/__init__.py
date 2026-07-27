"""L6 生产监控与治理 (prodmon)。

四块能力：
  - 在线采样评测：从生产 ai.chat.session 采样，经 ProductionJudge 跑质量信号
    （安全违规 / 拒答异常 / 幻觉启发式），产出生产指标并与 L4 基线对比。
  - 告警：生产指标越界（安全违规 0 容忍 / 幻觉超阈值 / 综合准确率跌破下限 / 相对基线退化）即告警。
  - prompt/模型版本化留痕：统计采样会话的 prompt_version × model_used 分布，
    治理侧快照 prompt 版本注册表，支持版本 diff（需 sc_ai 在会话记录上留痕）。
  - bad case 回流：把被判有问题（任一 flag）的生产会话沉淀为 bad_cases.jsonl，
    并折算成 L4 eval_set 建议条目，回流为回归测试。

离线可跑：默认 MockCollector 回放 prod_fixtures.json（健康会话，门禁 PASS）；
RpcCollector 经 odoo_client 拉真实生产会话（需 Odoo + ai.config，CI 不跑）。
"""
from .types import ProdSession, ProdSessionResult, ProdAlert, VersionInfo  # noqa: F401
from .judge_prod import ProductionJudge  # noqa: F401
from .collector import ProductionCollector, MockCollector, RpcCollector  # noqa: F401
from .sampler import sample  # noqa: F401
from .metrics import compute_prod_metrics, compare_to_baseline  # noqa: F401
from .alerting import evaluate_alerts, write_alert, DEFAULT_THRESHOLDS  # noqa: F401
from .badcase import capture_bad_cases  # noqa: F401
from .versioning import analyze_versions, diff_prompt, PROMPT_REGISTRY  # noqa: F401
from .notify import dispatch as notify_dispatch, load_alert, format_markdown  # noqa: F401
