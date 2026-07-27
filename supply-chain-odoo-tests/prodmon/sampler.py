"""L6 采样策略（确定性，便于离线复现）。"""
from __future__ import annotations

import random
from collections import defaultdict

from .types import ProdSession


def sample(sessions: list[ProdSession], n: int, strategy: str = "recent",
           seed: int = 42) -> list[ProdSession]:
    """从生产会话中抽取 n 条用于评测。

    strategy:
      - recent     ：取最近的 n 条（默认，最贴近当前线上状态）
      - random     ：随机抽（固定 seed 可复现）
      - stratified ：按 prompt_version 分层按比例抽，保证各版本都有代表
    """
    if n <= 0 or n >= len(sessions):
        return list(sessions)

    if strategy == "random":
        return random.Random(seed).sample(sessions, n)

    if strategy == "stratified":
        buckets: dict = defaultdict(list)
        for s in sessions:
            buckets[s.prompt_version or "unknown"].append(s)
        out: list = []
        rnd = random.Random(seed)
        for b in buckets.values():
            k = max(1, round(n * len(b) / len(sessions)))
            out.extend(rnd.sample(b, min(k, len(b))))
        return out[:n]

    # default: recent
    return list(sessions[-n:])
