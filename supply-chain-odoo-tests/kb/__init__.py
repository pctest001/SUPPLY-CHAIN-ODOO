"""需求知识库（KB）薄存储——变更安全三支柱之支柱三·增量止血。

定位（与 v2 方案一致，明确不做的事）：
  ✗ 不做全量历史需求考古回填（v1 方案已降级为按需工具箱）
  ✓ 只保证【从今天起】每一次变更都留下需求条目与关联痕迹：
    - PR 必须引用 KB 中存在的 REQ-xxx（kb.gate 门禁）
    - intents.yml 的每条放行意图必须挂 KB 中存在的 REQ（kb.gate 校验）
    - 口头共识（oral）当场落一条薄条目，不再蒸发

模块：
  model.py  Requirement 数据模型 + 校验（provenance 含 oral；status 五态）
  store.py  requirements.json 读写 + CLI（add/list/show/validate）
  gate.py   门禁 CLI：PR 文本 REQ 引用检查 + intents.yml REQ 存在性检查
"""
