"""缺陷闭环层 —— sink（缺陷出口）。

registry 负责本地持久化；sink 负责把缺陷「投递」到外部工单系统。
当前只实现 LocalSink（生成本地汇总 md）；GitHubIssueSink / TapdSink 预留为
可插拔接口——连接器(GitHub/TAPD)未接入时静默 no-op，registry 仍保留本地副本，
连接器就绪后替换 sink 即可，无需改调用方。
"""
from __future__ import annotations

from pathlib import Path

from .schema import STATUSES
from .registry import DefectRegistry


class DefectSink:
    name = "base"

    def emit(self, defect, created: bool):
        raise NotImplementedError


class LocalSink(DefectSink):
    name = "local"

    def __init__(self, registry: DefectRegistry, summary_path: Path | None = None):
        self.registry = registry
        self.summary_path = summary_path or (registry.path.parent / "defects_summary.md")

    def emit(self, defect, created: bool):
        self._write_summary()
        return defect

    def _write_summary(self):
        defects = self.registry.all()
        lines = ["# 缺陷汇总（Defect Closure）", "",
                 f"> 来源：本地缺陷库 `{self.registry.path.name}`；共 {len(defects)} 条。",
                 "",
                 "## 按状态分布", ""]
        for st in STATUSES:
            n = sum(1 for d in defects if d.status == st)
            if n:
                lines.append(f"- **{st}**: {n}")
        lines += ["", "## 明细", "",
                  "| ID | 状态 | 严重度 | 类别 | 来源 | 标题 | 出现次数 | Owner | 修复引用 | 验证证据 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for d in sorted(defects, key=lambda x: (STATUSES.index(x.status), x.id)):
            lines.append(f"| {d.id} | {d.status} | {d.severity} | {d.category} | "
                         f"{d.source} | {d.title} | {d.occurrences} | {d.owner or '-'} | "
                         f"{d.fix_ref or '-'} | {d.verified_by or '-'} |")
        self.summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class GitHubIssueSink(DefectSink):
    """预留：GitHub Issues 建单。连接器(gh/api token)就绪后实现 emit 内建 issue 逻辑。

    未接入时 emit 返回 None（不建单），registry 本地副本仍完整保留。
    """
    name = "github_issue"

    def __init__(self, token: str | None = None):
        self.token = token

    def emit(self, defect, created: bool):
        if not self.token:
            return None  # 连接器未接入：no-op
        # TODO: 用 PyGithub / REST API 建/更新 issue；defect.id 可作为 issue 正文溯源锚点
        raise NotImplementedError("GitHub connector 未接入：请配置 token 后实现 emit")


class TapdSink(DefectSink):
    """预留：TAPD 缺陷单。连接器就绪后实现。"""
    name = "tapd"

    def __init__(self, token: str | None = None):
        self.token = token

    def emit(self, defect, created: bool):
        if not self.token:
            return None
        raise NotImplementedError("TAPD connector 未接入：请配置 token 后实现 emit")
