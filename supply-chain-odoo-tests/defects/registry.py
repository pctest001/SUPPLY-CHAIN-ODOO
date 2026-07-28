"""缺陷闭环层 —— 本地缺陷库（registry）。

defects.jsonl 持久化所有 defect；按 signature 去重（同缺陷只 +1 计数不重复建单）；
提供状态机转移、查询。纯标准库、离线可跑。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schema import Defect, can_transition, severity_rank, STATUS_OPEN

DEFAULT_PATH = Path(__file__).resolve().parent / "defects.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DefectRegistry:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)
        self._by_sig: dict[str, Defect] = {}
        self._by_id: dict[str, Defect] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = Defect.from_dict(json.loads(line))
            self._by_sig[d.signature] = d
            self._by_id[d.id] = d

    def _next_id(self) -> str:
        nums = [int(d.id.split("-")[-1]) for d in self._by_id.values()
                if d.id.startswith("DEF-") and d.id.split("-")[-1].isdigit()]
        return f"DEF-{max(nums) + 1:03d}" if nums else "DEF-001"

    def add(self, defect: Defect, now=None):
        """新增或合并（去重）缺陆。返回 (defect, is_new)。"""
        now = now or _now()
        if defect.signature in self._by_sig:
            existing = self._by_sig[defect.signature]
            existing.occurrences += 1
            existing.updated_at = now
            if severity_rank(defect.severity) < severity_rank(existing.severity):
                existing.severity = defect.severity
            if defect.evidence:
                existing.evidence = defect.evidence
            if defect.title:
                existing.title = defect.title
            self._save()
            return existing, False
        defect.id = self._next_id()
        defect.created_at = now
        defect.updated_at = now
        if not defect.status:
            defect.status = STATUS_OPEN
        self._by_sig[defect.signature] = defect
        self._by_id[defect.id] = defect
        self._save()
        return defect, True

    def transition(self, defect_id: str, to: str, owner=None, fix_ref=None,
                   verified_by=None, now=None):
        """状态机转移；非法转移抛 ValueError。可选挂 owner/fix_ref/verified_by。"""
        d = self._by_id.get(defect_id)
        if d is None:
            raise KeyError(f"未知缺陷 {defect_id}")
        if not can_transition(d.status, to):
            raise ValueError(f"非法状态转移 {d.status} -> {to}（允许："
                             f"{sorted(can_transition_targets(d.status))}）")
        d.status = to
        d.updated_at = now or _now()
        if owner is not None:
            d.owner = owner
        if fix_ref is not None:
            d.fix_ref = fix_ref
        if verified_by is not None:
            d.verified_by = verified_by
        self._save()
        return d

    def get(self, defect_id: str) -> Defect | None:
        return self._by_id.get(defect_id)

    def query(self, status=None, source=None, category=None) -> list[Defect]:
        return [d for d in self._by_id.values()
                if (status is None or d.status == status)
                and (source is None or d.source == source)
                and (category is None or d.category == category)]

    def all(self) -> list[Defect]:
        return list(self._by_id.values())

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(d.to_dict(), ensure_ascii=False)
                 for d in sorted(self._by_id.values(), key=lambda x: x.id)]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def can_transition_targets(status: str) -> set:
    from .schema import _TRANSITIONS
    return _TRANSITIONS.get(status, set())
