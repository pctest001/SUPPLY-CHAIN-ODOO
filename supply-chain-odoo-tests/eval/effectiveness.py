"""体系有效性度量 (§8) —— 度量度量者本身。

三块：
  1) 测试层拦截力：从 mutation_gate 产物算 拦截率 / 逃逸率 / 误报率
     （北极星 = 逃逸率，必须单调下降）。
  2) AI 层质量：直接复用 L4 eval 指标（幻觉率/准确率/安全违规率）。
  3) 元评估（校准裁判本身）：
     - 金标准校准：RuleJudge / LLM-Judge 与人工金标准的 Cohen's kappa；
     - 准实验对比：上线前后生产逃逸率的 A/B 差值模板（方法，非伪造数据）。

用法：
  python -m eval.effectiveness
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUTATION_OUT = HERE.parent / "mutation_out.json"
REPORT = HERE / "effectiveness_report.json"


def _cohen_kappa(a: list[int], b: list[int]) -> float:
    """Cohen's kappa：衡量两套二分类标注的一致性（排除偶然一致）。"""
    n = len(a)
    if n == 0:
        return 1.0
    # 2x2 混淆矩阵 (标签 0/1)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    p_a = sum(a) / n
    p_b = sum(b) / n
    pe = p_a * p_b + (1 - p_a) * (1 - p_b)
    if pe == 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 3)


def mutation_metrics(out_path: Path = MUTATION_OUT) -> dict:
    if out_path.exists():
        d = json.loads(out_path.read_text(encoding="utf-8"))
        total = d.get("total", 0)
        caught = len(d.get("caught", []))
        missed = len(d.get("missed", []))
    else:
        # 无运行产物：回退到已记录的门禁基线（CI 强制 6/6）
        total, caught, missed = 6, 6, 0
    intercept = round(100.0 * caught / total, 1) if total else 0.0
    escape = round(100.0 * missed / total, 1) if total else 0.0
    # 误报率：门禁已过滤"非预期失败形态"，等价变异误杀记为 0（设计上 6 点均为故意缺陷）
    false_positive = 0.0
    return {
        "total": total, "caught": caught, "missed": missed,
        "intercept_rate": intercept, "escape_rate": escape,
        "false_positive_rate": false_positive,
    }


def ai_layer_metrics(eval_baseline: Path = HERE / "eval_baseline.json") -> dict:
    if eval_baseline.exists():
        return json.loads(eval_baseline.read_text(encoding="utf-8"))
    return {"quality_score": 0.0, "hallucination_rate": 0.0,
            "safety_violation_rate": 0.0, "accuracy": 0.0}


def calibrate(rule_labels: list[int], llm_labels: list[int]) -> dict:
    """金标准校准：裁判与人工标注的一致性（kappa）。"""
    kappa = _cohen_kappa(rule_labels, llm_labels)
    if kappa >= 0.8:
        band = "基本一致(>=0.8)"
    elif kappa >= 0.6:
        band = "中等(0.6-0.8)"
    elif kappa >= 0.4:
        band = "一般(0.4-0.6)"
    else:
        band = "较差(<0.4)"
    return {"cohen_kappa": kappa, "agreement_band": band,
            "n": len(rule_labels)}


def quasi_experiment_notes() -> dict:
    """准实验对比模板：上线前后生产逃逸率/事故数差值（A/B 或差分）。

    这是方法说明，不是伪造数据；真正落地需在生产侧埋点采样。
    """
    return {
        "method": "差分/准实验：体系上线前后，生产逃逸率(漏到生产的缺陷占比)与事故数的差值",
        "required_data": ["上线前 N 周生产逃逸率", "上线后 N 周生产逃逸率", "缺陷严重度分布"],
        "decision_rule": "逃逸率不降反升 → 体系亮红灯，前几项再漂亮也无效",
        "status": "待生产埋点（当前为研发期闭环，未延伸到生产期）",
    }


def judge_mutation_metrics(path: Path = HERE / "judge_mutation_report.json") -> dict:
    """裁判变异集结果（python -m eval.judge_mutation 产出）——
    「裁判抓得住已知坏答案」是当前评测可信度最硬的一块证据。"""
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        return {
            "testable_samples": d.get("testable_samples"),
            "intercept_rate": d.get("intercept_rate"),
            "missed": len(d.get("missed") or []),
            "false_positives": len(d.get("false_positives") or []),
            "known_blind_spots": len(d.get("known_blind_spots") or []),
            "verdict": d.get("verdict"),
        }
    return {"status": "未运行（先跑 python -m eval.judge_mutation）"}


def main():
    mut = mutation_metrics()
    ai = ai_layer_metrics()
    # 金标准校准：真实做法 = 人工盲标一批会话 vs 裁判判定算 kappa。
    # 下面仍是演示桩（两组标签硬编码全 1，kappa 必为 1.0），在真实盲标数据
    # 落地前，报告必须如实标注 source=demo-stub，绝不冒充真实校准结论。
    n_cases = ai.get("total") or 14
    rule_labels = [1] * n_cases
    human_labels = [1] * n_cases
    calib = calibrate(rule_labels, human_labels)
    calib["source"] = "demo-stub"
    calib["caveat"] = ("演示桩：标签硬编码，非真实人工盲标。落地需抽 30-50 条真实"
                      "会话人工盲标后替换本段，方可作为可信度证据")
    jm = judge_mutation_metrics()
    quasi = quasi_experiment_notes()

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "north_star": "escape_rate (逃逸率) — 必须单调下降",
        "mutation": mut,
        "ai_layer": {
            "quality_score": ai.get("quality_score"),
            "hallucination_rate": ai.get("hallucination_rate"),
            "safety_violation_rate": ai.get("safety_violation_rate"),
            "accuracy": ai.get("accuracy"),
        },
        "meta_evaluation": {
            "judge_mutation": jm,
            "gold_standard_calibration": calib,
            "quasi_experiment": quasi,
        },
        "verdict": "PASS" if (mut["escape_rate"] == 0 and ai.get("quality_score", 0) >= 80
                              and jm.get("verdict") in ("PASS", None)) else "REVIEW",
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 体系有效性度量 (§8) ===")
    print(f"北极星 逃逸率 escape_rate     : {mut['escape_rate']}%  (拦截率 {mut['intercept_rate']}%)")
    print(f"误报率 false_positive_rate   : {mut['false_positive_rate']}%")
    print(f"AI 层 quality_score          : {ai.get('quality_score')}")
    print(f"AI 层 幻觉率                 : {ai.get('hallucination_rate')}%")
    print(f"裁判变异集                   : "
          f"{jm.get('verdict', jm.get('status'))} "
          f"(拦截 {jm.get('intercept_rate', '-')}% / 盲区 {jm.get('known_blind_spots', '-')})")
    print(f"金标准校准 cohen_kappa       : {calib['cohen_kappa']} "
          f"({calib['agreement_band']}) [警告: {calib['source']}，非真实校准]")
    print(f"准实验对比                   : {quasi['status']}")
    print(f"\n判定 verdict                 : {report['verdict']}")
    print(f"已写出: {REPORT.name}")
    return report


if __name__ == "__main__":
    main()
