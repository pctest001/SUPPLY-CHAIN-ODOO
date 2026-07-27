"""捕获归一化：清洗环境噪声，只留行为语义（支柱一 P1）。

上轮 P0 前哨对比证实的教训（写死为设计规则）：
  ✗ 不允许用数值特征猜 id（base 新库 id=12 逃过阈值 → 假差异）；
  ✓ 只按【语义位置】结构化清洗——明确知道"这里是 id"的地方才清洗。

清洗规则（按语义位置）：
  1. dict 中的 "id" 键        -> 删除（read/search_read 必带，纯环境噪声）
  2. many2one 值 [int, "名称"]  -> 只留显示名（id 双端不同，名称才是语义）
  3. domain 三元组 [字段, op, 值]，字段为 id/x_id -> 值抹为 «ID»/«IDS:n»（保留数量语义）
  4. 字符串中的 run_id token   -> «RUN»（跨 run 可比）
  5. 单据号 P00154 / WH/IN/7 等 -> «PO»/«IN»…（序列号双端独立自增）
  6. 日期/时间 -> 相对天数 «D+180»/«D-10»（保留过期/未过期语义，消除绝对日期）

红线：宁可留噪声也不过度清洗——清洗过度会吞掉真实回归（假阴性比假阳性危险）。
"""
from __future__ import annotations

import re
from datetime import date

# 单据序列号模式（双端各自自增，无行为语义）
_REF_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bP\d{5}\b"), "«PO»"),
    (re.compile(r"\bWH/IN/\d+\b"), "«IN»"),
    (re.compile(r"\bWH/OUT/\d+\b"), "«OUT»"),
    (re.compile(r"\bWH/INT/\d+\b"), "«INT»"),
]

_DT_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?: \d{2}:\d{2}:\d{2})?\b")


def _norm_string(s: str, run_id: str, today: date) -> str:
    if run_id:
        s = s.replace(run_id, "«RUN»")

    def _dt(m: re.Match) -> str:
        try:
            delta = (date(int(m.group(1)), int(m.group(2)), int(m.group(3))) - today).days
        except ValueError:
            return m.group(0)
        return f"«D{delta:+d}»"

    s = _DT_RE.sub(_dt, s)
    for pat, repl in _REF_PATTERNS:
        s = pat.sub(repl, s)
    return s


def _is_m2o(v) -> bool:
    """Odoo many2one 读出形态：[id:int, display_name:str]。"""
    return (isinstance(v, (list, tuple)) and len(v) == 2
            and isinstance(v[0], int) and isinstance(v[1], str))


def _is_id_domain_leaf(v) -> bool:
    """domain 三元组 [field, op, value] 且 field 语义为 id。"""
    return (isinstance(v, (list, tuple)) and len(v) == 3
            and isinstance(v[0], str) and isinstance(v[1], str)
            and (v[0] == "id" or v[0].endswith("_id") or v[0].endswith("_ids")))


def normalize(value, run_id: str, today: date):
    """递归归一化任意 capture 值。"""
    if isinstance(value, str):
        return _norm_string(value, run_id, today)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "id":
                continue  # 规则1：记录自身 id 是环境噪声
            if _is_m2o(v):
                out[k] = _norm_string(v[1], run_id, today)  # 规则2：只留显示名
            else:
                out[k] = normalize(v, run_id, today)
        return out
    if isinstance(value, (list, tuple)):
        if _is_id_domain_leaf(value):  # 规则3：domain 中的 id 值
            field, op, val = value
            if isinstance(val, (list, tuple)):
                return [field, op, f"«IDS:{len(val)}»"]
            return [field, op, "«ID»"]
        return [normalize(v, run_id, today) for v in value]
    return value


def normalize_capture(payload: dict) -> dict:
    """归一化 runner 输出的整份 capture 文件（不改原对象）。"""
    run_id = payload.get("run_id", "")
    gen = payload.get("generated_at", "")
    m = _DT_RE.match(gen)
    today = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else date.today()
    out = {}
    for cap in payload.get("captures", []):
        out[cap["scenario"]] = {
            "req": cap.get("req", ""),
            "status": cap["status"],
            "error": _norm_string(cap["error"], run_id, today) if cap.get("error") else None,
            "observations": normalize(cap.get("observations", {}), run_id, today),
        }
    return out
