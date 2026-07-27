"""Requirement 数据模型（薄条目，一句话也能立户）。

设计要点（来自需求条目化讨论的落地共识）：
  - 一句话需求不排斥：statement 允许很短，薄条目也比蒸发强；
  - oral（口头共识）是一等公民：线下达成一致后当场落条目，confidence 0.8；
  - confidence 不是摆设：围栏场景挂上后可升；bug 打脸后必须降。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict

REQ_ID_RE = re.compile(r"^REQ-[A-Z0-9]+(-[A-Z0-9]+)*$")

PROVENANCES = {
    "current-prd":   "现行 PRD/验收清单明文",
    "legacy":        "历史文档（含一句话需求）",
    "code-inferred": "代码/视图反推（按需考古产出）",
    "bug-derived":   "缺陷单反推",
    "oral":          "口头/IM 共识（当场落档）",
}

STATUSES = {
    "active":     "有效，可作为断言依据",
    "implied":    "行为存在但无文档背书（围栏观测到、待确认）",
    "deprecated": "已废弃",
    "conflict":   "多来源冲突，待人工裁决",
    "undefined":  "仅占位（只知道有这回事）",
}

# 缺省置信度（可被显式值覆盖）
DEFAULT_CONFIDENCE = {
    "current-prd": 1.0,
    "legacy": 0.7,
    "code-inferred": 0.6,
    "bug-derived": 0.8,
    "oral": 0.8,
}


@dataclass
class Requirement:
    id: str                      # REQ-C2-GUARD-ZERO
    title: str                   # 短标题
    statement: str = ""          # EARS 或一句话描述（允许薄）
    provenance: str = "current-prd"
    status: str = "active"
    confidence: float = -1.0     # -1 = 按 provenance 取缺省
    links: dict = field(default_factory=dict)   # prd/test/tech/code/scenarios/bug
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if self.confidence < 0:
            self.confidence = DEFAULT_CONFIDENCE.get(self.provenance, 0.5)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now

    def validate(self) -> list[str]:
        errs = []
        if not REQ_ID_RE.match(self.id):
            errs.append(f"{self.id}: id 不符合 REQ-XXX 格式")
        if not self.title:
            errs.append(f"{self.id}: 缺 title")
        if self.provenance not in PROVENANCES:
            errs.append(f"{self.id}: provenance 非法 {self.provenance}")
        if self.status not in STATUSES:
            errs.append(f"{self.id}: status 非法 {self.status}")
        if not (0.0 <= self.confidence <= 1.0):
            errs.append(f"{self.id}: confidence 越界 {self.confidence}")
        if self.provenance == "oral" and not self.notes:
            errs.append(f"{self.id}: oral 来源必须在 notes 记录谁/何时/何处达成共识")
        return errs

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Requirement":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
