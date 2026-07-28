"""缺陷闭环层 —— emit（把发现的问题转成 defect 记录）。

两条来源归口同一 registry：
  1. prod_monitor：run_monitor 抓到的问题会话（bad case）→ emit_from_sessions
  2. ci_gate：CI 门禁命中的真实缺陷（mutation/behavior-fence/rpc/ui）→ emit_from_ci
两者都按 signature 去重，绝不重复建单。
"""
from __future__ import annotations

from .schema import Defect, make_signature, flag_to_category, flag_to_severity
from .registry import DefectRegistry
from .sink import LocalSink


def _session_title(question: str, flags: list) -> str:
    q = (question or "").strip().replace("\n", " ")
    head = q[:40] + ("…" if len(q) > 40 else "")
    flag_zh = {
        "safety_violation": "安全违规",
        "missed_refusal": "漏拒",
        "false_refusal": "误拒",
        "hallucination": "幻觉",
    }
    tags = "/".join(flag_zh.get(f, f) for f in flags)
    return f"[{tags}] {head}" if head else f"[{tags}] 未命名会话"


def emit_from_sessions(sessions, results, registry: DefectRegistry | None = None,
                       sink: LocalSink | None = None, now=None):
    """把 prod_monitor 的问题会话转为 defect。返回 (created, updated)。"""
    registry = registry or DefectRegistry()
    sink = sink or LocalSink(registry)
    created = updated = 0
    for s, r in zip(sessions, results):
        if getattr(r, "clean", False) or not getattr(r, "flags", None):
            continue
        sig = make_signature("prod_monitor", f"{s.id}|{sorted(r.flags)}")
        d = Defect(
            source="prod_monitor",
            signature=sig,
            title=_session_title(s.question, r.flags),
            severity=flag_to_severity(r.flags),
            category=flag_to_category(r.flags),
            evidence={
                "session_id": s.id,
                "flags": r.flags,
                "reasons": getattr(r, "reasons", []),
                "prompt_version": getattr(s, "prompt_version", "unknown"),
                "model_used": getattr(s, "model_used", "unknown"),
            },
        )
        d, is_new = registry.add(d, now=now)
        sink.emit(d, is_new)
        created += int(is_new)
        updated += int(not is_new)
    return created, updated


def emit_from_ci(source: str, key: str, title: str, severity: str = "high",
                 category: str = "other", evidence: dict | None = None,
                 registry: DefectRegistry | None = None, sink: LocalSink | None = None,
                 now=None):
    """CI 门禁命中的真实缺陷 → defect。返回 (defect, is_new)。"""
    registry = registry or DefectRegistry()
    sink = sink or LocalSink(registry)
    sig = make_signature("ci_gate", f"{source}|{key}")
    d = Defect(
        source="ci_gate",
        signature=sig,
        title=title,
        severity=severity,
        category=category,
        evidence=evidence or {},
    )
    d, is_new = registry.add(d, now=now)
    sink.emit(d, is_new)
    return d, is_new
