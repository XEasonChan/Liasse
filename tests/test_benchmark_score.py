"""score.py 的契约测试 — 不依赖真实 GT/pred 文件。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.benchmark.score import (
    compute_metrics,
    turns_to_annotation,
    _hungarian_map,
)


def test_turns_to_annotation_basic():
    turns = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    ann = turns_to_annotation(turns)
    labels = set(ann.labels())
    assert labels == {"A", "B"}


def test_compute_metrics_perfect_match():
    """GT == pred → DER 0, accuracy 1.0"""
    gt = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    pred = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    m = compute_metrics(gt, pred, total_dur=10.0)
    assert m["der"] < 0.01
    assert m["accuracy"] > 0.99


def test_compute_metrics_label_swap_is_perfect_after_mapping():
    """pred 用了 SPEAKER_00/01 而 GT 用 A/B,内容完全 swap 对齐 —
    best-mapping 应能 remap 后给出 accuracy = 1.0。"""
    gt = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    pred = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
        {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"},
    ]
    m = compute_metrics(gt, pred, total_dur=10.0)
    assert m["accuracy"] > 0.99
    assert m["mapping"] == {"SPEAKER_00": "A", "SPEAKER_01": "B"}


def test_compute_metrics_half_wrong():
    """GT 前 5s A + 后 5s B,但 pred 全归 A → accuracy ≈ 0.5"""
    gt = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    pred = [{"start": 0.0, "end": 10.0, "speaker": "A"}]
    m = compute_metrics(gt, pred, total_dur=10.0)
    assert 0.4 < m["accuracy"] < 0.6


def test_hungarian_mapping_picks_max_co_occurrence():
    gt = [
        {"start": 0.0, "end": 5.0, "speaker": "A"},
        {"start": 5.0, "end": 10.0, "speaker": "B"},
    ]
    pred = [
        {"start": 0.0, "end": 5.0, "speaker": "X"},
        {"start": 5.0, "end": 10.0, "speaker": "Y"},
    ]
    mapping, acc = _hungarian_map(gt, pred, dur=10.0)
    assert mapping == {"X": "A", "Y": "B"}
    assert acc > 0.99


def test_compute_metrics_target_accuracy_90():
    """模拟 ~90% 准确率场景。"""
    gt = [{"start": 0.0, "end": 10.0, "speaker": "A"}]
    pred = [
        {"start": 0.0, "end": 9.0, "speaker": "X"},
        {"start": 9.0, "end": 10.0, "speaker": "Y"},
    ]
    m = compute_metrics(gt, pred, total_dur=10.0)
    assert 0.85 < m["accuracy"] < 0.95
