#!/usr/bin/env python3
"""Score liasse pipeline 预测 vs Claude GT,计算 DER + speaker accuracy。

两个指标:
  1. DER (Diarization Error Rate, pyannote.metrics 标准口径)
     - 包含 false_alarm + missed_detection + speaker_confusion
     - 自动做 best-speaker-mapping (Hungarian assignment),GT 的 A 和 pred 的
       SPEAKER_00 算同一人(只要时间最匹配),不算 confusion
     - 低越好,业界 SOTA pyannote 在 community-1 测试集 11.2%

  2. Speaker Accuracy (我们的目标指标,>90% pass)
     - 按 100ms 格点扫整段音频
     - 每个格点 GT 标签和 pred 标签经 best-mapping 后是否一致
     - = (一致格点数) / (GT 标了说话人的总格点数)
     - 这是「用户看到 transcript 时 speaker 标对的比例」最直接的度量

输出:
  - stdout 表格
  - results/scores.json 完整数字
  - results/scores-report.md 人读 markdown
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pyannote.core import Annotation, Segment
from pyannote.metrics.diarization import DiarizationErrorRate

ROOT = Path(__file__).resolve().parent.parent.parent
GT_DIR = ROOT / "scripts" / "benchmark" / "ground_truth"
PRED_DIR = ROOT / "scripts" / "benchmark" / "results"


def turns_to_annotation(turns: List[Dict[str, Any]]) -> Annotation:
    """Convert turns list into pyannote.core.Annotation."""
    ann = Annotation()
    for i, t in enumerate(turns):
        start = float(t["start"])
        end = float(t["end"])
        if end <= start:
            continue
        ann[Segment(start, end), i] = str(t["speaker"])
    return ann


def _label_at(turns: List[Dict[str, Any]], t: float):
    for tn in turns:
        if float(tn["start"]) <= t < float(tn["end"]):
            return str(tn["speaker"])
    return None


def _hungarian_map(
    gt_turns: List[Dict], pred_turns: List[Dict], dur: float, step: float = 0.1,
) -> Tuple[Dict[str, str], float]:
    """求 pred label → gt label 的 best mapping,返回 (mapping, accuracy)。

    算法:对每对 (gt_label, pred_label) 算同时刻共现总时长(秒),用贪心
    匹配最大化总匹配时长。2-speaker 场景下贪心和 Hungarian 等价。
    """
    gt_labels = sorted({str(t["speaker"]) for t in gt_turns})
    pred_labels = sorted({str(t["speaker"]) for t in pred_turns})

    # 共现矩阵:co[g][p] = 在该 cell 内 GT=g 且 pred=p 的时长(秒)
    co: Dict[Tuple[str, str], float] = {}
    t = 0.0
    while t < dur:
        g = _label_at(gt_turns, t)
        p = _label_at(pred_turns, t)
        if g is not None and p is not None:
            co[(g, p)] = co.get((g, p), 0.0) + step
        t += step

    # 贪心:挑当前最大的 co 项,锁定 g↔p,剩余继续
    mapping: Dict[str, str] = {}
    used_gt: set = set()
    pairs = sorted(co.items(), key=lambda kv: -kv[1])
    for (g, p), _ in pairs:
        if p in mapping or g in used_gt:
            continue
        mapping[p] = g
        used_gt.add(g)

    # 算 accuracy:每 step,如果 GT 标了 speaker,看 pred 映射后是否同。
    correct = 0.0
    counted = 0.0
    t = 0.0
    while t < dur:
        g = _label_at(gt_turns, t)
        p = _label_at(pred_turns, t)
        if g is None:
            t += step
            continue
        counted += step
        if p is not None and mapping.get(p) == g:
            correct += step
        t += step

    accuracy = correct / counted if counted > 0 else 0.0
    return mapping, accuracy


def compute_metrics(
    gt_turns: List[Dict[str, Any]],
    pred_turns: List[Dict[str, Any]],
    total_dur: float,
) -> Dict[str, Any]:
    gt_ann = turns_to_annotation(gt_turns)
    pred_ann = turns_to_annotation(pred_turns)

    der_metric = DiarizationErrorRate(collar=0.25, skip_overlap=False)
    uem = Segment(0.0, float(total_dur))
    der = float(der_metric(gt_ann, pred_ann, uem=uem))

    mapping, accuracy = _hungarian_map(gt_turns, pred_turns, total_dur)

    return {
        "der": der,
        "accuracy": accuracy,
        "mapping": mapping,
        "gt_turn_count": len(gt_turns),
        "pred_turn_count": len(pred_turns),
        "gt_speakers": sorted({str(t["speaker"]) for t in gt_turns}),
        "pred_speakers": sorted({str(t["speaker"]) for t in pred_turns}),
    }


def main() -> int:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    if not GT_DIR.exists() or not list(GT_DIR.glob("*.gt.json")):
        print(f"ERROR: no ground truth in {GT_DIR}.\n"
              f"  run build_ground_truth.py first (needs ANTHROPIC_API_KEY).",
              file=sys.stderr)
        return 1

    results = []
    for gt_file in sorted(GT_DIR.glob("*.gt.json")):
        sample = gt_file.stem.replace(".gt", "")
        pred_file = PRED_DIR / f"{sample}.pred.json"
        if not pred_file.exists():
            print(f"  ✗ skip {sample}: prediction not found ({pred_file.name})")
            continue
        gt = json.loads(gt_file.read_text())
        pred = json.loads(pred_file.read_text())
        try:
            m = compute_metrics(gt["turns"], pred["turns"],
                                total_dur=gt["audio_dur_sec"])
        except Exception as exc:
            print(f"  ✗ {sample}: scoring error: {exc}", file=sys.stderr)
            continue
        results.append({"sample": sample, **m})

    if not results:
        print("ERROR: no scoreable samples (need GT + pred for at least one).",
              file=sys.stderr)
        return 1

    # stdout 表
    print()
    print("=" * 88)
    print(f"{'sample':<24} {'DER':>8} {'accuracy':>10} {'gtTurns':>8} {'predTurns':>10} {'mapping':>12}")
    print("-" * 88)
    for r in results:
        mapping_str = " ".join(f"{k}→{v}" for k, v in r["mapping"].items())
        print(f"{r['sample']:<24} {r['der']*100:>7.2f}% {r['accuracy']*100:>9.2f}% "
              f"{r['gt_turn_count']:>8} {r['pred_turn_count']:>10} {mapping_str:>12}")
    avg_der = sum(r["der"] for r in results) / len(results)
    avg_acc = sum(r["accuracy"] for r in results) / len(results)
    print("-" * 88)
    print(f"{'AVG':<24} {avg_der*100:>7.2f}% {avg_acc*100:>9.2f}%")
    print()
    if avg_acc >= 0.90:
        print(f"✓ TARGET MET: average accuracy {avg_acc*100:.2f}% ≥ 90%")
    else:
        print(f"✗ Below target: avg accuracy {avg_acc*100:.2f}% < 90%")

    # JSON 报告
    report = {
        "results": results,
        "summary": {
            "avg_der": avg_der,
            "avg_accuracy": avg_acc,
            "target_met": avg_acc >= 0.90,
            "sample_count": len(results),
        },
    }
    out = PRED_DIR / "scores.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nFull report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
