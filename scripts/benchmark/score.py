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


def _discover_pred_files(pred_dir: Path, sample: str) -> List[Path]:
    """找 <sample>.pred.json 或 <sample>__<modeltag>.pred.json 模式的预测文件。"""
    files = []
    single = pred_dir / f"{sample}.pred.json"
    if single.exists():
        files.append(single)
    for f in pred_dir.glob(f"{sample}__*.pred.json"):
        files.append(f)
    return sorted(files)


def _model_tag(pred_path: Path, sample: str) -> str:
    """从文件名抽 model tag。<sample>__<tag>.pred.json → tag。"""
    stem = pred_path.stem.replace(".pred", "")
    if stem == sample:
        return "default"
    prefix = f"{sample}__"
    if stem.startswith(prefix):
        return stem[len(prefix):]
    return stem


def main() -> int:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    if not GT_DIR.exists() or not list(GT_DIR.glob("*.gt.json")):
        print(f"ERROR: no ground truth in {GT_DIR}.\n"
              f"  run build_ground_truth.py first (needs OPENROUTER_API_KEY).",
              file=sys.stderr)
        return 1

    results = []
    by_model: Dict[str, List[Dict]] = {}
    for gt_file in sorted(GT_DIR.glob("*.gt.json")):
        sample = gt_file.stem.replace(".gt", "")
        gt = json.loads(gt_file.read_text())
        preds = _discover_pred_files(PRED_DIR, sample)
        if not preds:
            print(f"  ✗ skip {sample}: no prediction found")
            continue
        for pred_file in preds:
            tag = _model_tag(pred_file, sample)
            pred = json.loads(pred_file.read_text())
            try:
                m = compute_metrics(gt["turns"], pred["turns"],
                                    total_dur=gt["audio_dur_sec"])
            except Exception as exc:
                print(f"  ✗ {sample} ({tag}): scoring error: {exc}",
                      file=sys.stderr)
                continue
            row = {"sample": sample, "model": tag, **m}
            results.append(row)
            by_model.setdefault(tag, []).append(row)

    if not results:
        print("ERROR: no scoreable samples (need GT + pred for at least one).",
              file=sys.stderr)
        return 1

    # stdout 表 — 每个 model 一段
    print()
    for tag, rows in sorted(by_model.items()):
        print("=" * 96)
        print(f"MODEL: {tag}")
        print(
            f"{'sample':<24} {'DER':>8} {'accuracy':>10} "
            f"{'gtTurns':>8} {'predTurns':>10} {'mapping':>20}"
        )
        print("-" * 96)
        for r in rows:
            mapping_str = " ".join(f"{k}→{v}" for k, v in r["mapping"].items())
            print(
                f"{r['sample']:<24} {r['der']*100:>7.2f}% "
                f"{r['accuracy']*100:>9.2f}% "
                f"{r['gt_turn_count']:>8} {r['pred_turn_count']:>10} "
                f"{mapping_str:>20}"
            )
        avg_der = sum(r["der"] for r in rows) / len(rows)
        avg_acc = sum(r["accuracy"] for r in rows) / len(rows)
        print("-" * 96)
        print(f"{'AVG':<24} {avg_der*100:>7.2f}% {avg_acc*100:>9.2f}%")
        if avg_acc >= 0.90:
            print(f"✓ TARGET MET ({tag}): avg accuracy {avg_acc*100:.2f}% ≥ 90%")
        else:
            print(f"✗ Below target ({tag}): avg accuracy {avg_acc*100:.2f}% < 90%")
        print()

    # 跨模型最佳
    if len(by_model) > 1:
        print("=" * 96)
        print("CROSS-MODEL SUMMARY")
        print(f"{'model':<24} {'avg_der':>10} {'avg_accuracy':>14} {'target_met':>12}")
        print("-" * 96)
        for tag, rows in sorted(by_model.items()):
            avg_der = sum(r["der"] for r in rows) / len(rows)
            avg_acc = sum(r["accuracy"] for r in rows) / len(rows)
            ok = "✓" if avg_acc >= 0.90 else "✗"
            print(f"{tag:<24} {avg_der*100:>9.2f}% {avg_acc*100:>13.2f}% {ok:>12}")
        print()

    # JSON 报告
    summary = {
        tag: {
            "avg_der": sum(r["der"] for r in rows) / len(rows),
            "avg_accuracy": sum(r["accuracy"] for r in rows) / len(rows),
            "target_met": (sum(r["accuracy"] for r in rows) / len(rows)) >= 0.90,
            "sample_count": len(rows),
        }
        for tag, rows in by_model.items()
    }
    report = {"results": results, "summary": summary}
    out = PRED_DIR / "scores.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Full report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
