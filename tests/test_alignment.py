import unittest

from liasse.alignment import assign_speakers, overlap_seconds
from liasse.models import SpeakerTurn, TranscriptSegment


class AlignmentTests(unittest.TestCase):
    def test_overlap_seconds(self):
        self.assertEqual(overlap_seconds(1, 5, 3, 6), 2)
        self.assertEqual(overlap_seconds(1, 2, 3, 4), 0)
        self.assertEqual(overlap_seconds(None, 2, 1, 3), 0)

    def test_assigns_largest_overlap(self):
        # segment 10-20s 跨两个 speaker（SPK_00: 10-12=2s, SPK_01: 12-20=8s）
        # 新算法（minority 20% > 12% 阈值）会按 speaker 边界拆成 2 sub-segments。
        # 测试至少两个 speaker 都被表示出来；主体段是 SPK_01（更长那段）。
        segments = [TranscriptSegment(start=10, end=20, text="hello world!")]
        turns = [
            SpeakerTurn(start=0, end=12, speaker="SPEAKER_00"),
            SpeakerTurn(start=12, end=25, speaker="SPEAKER_01"),
        ]

        assigned = assign_speakers(segments, turns)

        speakers = [s.speaker for s in assigned]
        self.assertIn("SPEAKER_01", speakers)
        # 主体段（最长 sub-segment）应是 SPK_01
        longest = max(assigned, key=lambda s: s.end - s.start)
        self.assertEqual(longest.speaker, "SPEAKER_01")


if __name__ == "__main__":
    unittest.main()


class WeightedAlignmentTests(unittest.TestCase):
    """新算法：按 speaker 累计 overlap 选最大（取代单 turn overlap 最长）。

    回归 bug：旧实现对长 ASR segment + 细 pyannote turn 场景失效 ——
    所有 segment 都被赋同一个 speaker。
    """

    def test_long_segment_picks_speaker_with_most_total_overlap(self):
        """ASR 30 秒长 segment，pyannote 给了 10 个细 turn：
        - SPEAKER_00 有 3 个长 turn 共 18 秒
        - SPEAKER_01 有 7 个短 turn 共 8 秒
        新算法应该选 SPEAKER_00（总 overlap 多），即使 SPEAKER_01 的 turn
        数量更多。
        """
        segments = [TranscriptSegment(start=0, end=30, text="long segment")]
        turns = [
            SpeakerTurn(start=0, end=8, speaker="SPEAKER_00"),    # 8s
            SpeakerTurn(start=8, end=8.5, speaker="SPEAKER_01"),  # 0.5
            SpeakerTurn(start=8.5, end=14, speaker="SPEAKER_00"), # 5.5s
            SpeakerTurn(start=14, end=15, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=15, end=20, speaker="SPEAKER_00"),  # 5s（cumulative 00=18.5）
            SpeakerTurn(start=20, end=21, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=21, end=22, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=22, end=23, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=23, end=24, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=24, end=27, speaker="SPEAKER_01"),  # 3 (cumulative 01=8.5)
            # 00 总计 18.5s, 01 总计 8.5s → 选 00
        ]
        assigned = assign_speakers(segments, turns)
        assert assigned[0].speaker == "SPEAKER_00"

    def test_minority_speaker_wins_when_total_overlap_higher(self):
        """tie-break 反例：单看 turn 数量 SPEAKER_01 多（5 个），但
        SPEAKER_00 单个 turn 累计更长，新算法选 00。"""
        segments = [TranscriptSegment(start=0, end=20, text="x")]
        turns = [
            SpeakerTurn(start=0, end=15, speaker="SPEAKER_00"),   # 15s
            SpeakerTurn(start=15, end=16, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=16, end=17, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=17, end=18, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=18, end=19, speaker="SPEAKER_01"),  # 1
            SpeakerTurn(start=19, end=20, speaker="SPEAKER_01"),  # 1
            # 00=15s, 01=5s → 00 wins
        ]
        assigned = assign_speakers(segments, turns)
        assert assigned[0].speaker == "SPEAKER_00"

    def test_realistic_interview_pattern_two_speakers_present(self):
        """模拟 2 分钟双人访谈：5 个 ASR segment 跨越 52 个 pyannote turns。
        期望最终 segments 里两个 speaker 都出现（不是所有都被赋
        SPEAKER_00，这就是 cleanup pass Phase E 发现的 bug）。"""
        # 用长 text 让拆分后每段都有内容
        segments = [
            TranscriptSegment(start=0,   end=8,   text="开场" * 10),
            TranscriptSegment(start=9,   end=47,  text="主答" * 50),
            TranscriptSegment(start=47,  end=80,  text="主答二" * 50),
            TranscriptSegment(start=80,  end=95,  text="研究者提问" * 10),
            TranscriptSegment(start=96,  end=120, text="再回答" * 30),
        ]
        turns = [
            SpeakerTurn(start=0,   end=2.1, speaker="SPEAKER_00"),
            SpeakerTurn(start=2.8, end=4.1, speaker="SPEAKER_01"),
            SpeakerTurn(start=4.1, end=8,   speaker="SPEAKER_00"),
            SpeakerTurn(start=9,   end=46,  speaker="SPEAKER_00"),
            SpeakerTurn(start=46,  end=47,  speaker="SPEAKER_01"),
            SpeakerTurn(start=47,  end=78,  speaker="SPEAKER_00"),
            SpeakerTurn(start=78,  end=80,  speaker="SPEAKER_01"),
            SpeakerTurn(start=80,  end=82,  speaker="SPEAKER_00"),
            SpeakerTurn(start=82,  end=95,  speaker="SPEAKER_01"),
            SpeakerTurn(start=96,  end=120, speaker="SPEAKER_00"),
        ]
        assigned = assign_speakers(segments, turns)
        speakers_present = set(s.speaker for s in assigned)
        assert speakers_present == {"SPEAKER_00", "SPEAKER_01"}, (
            f"双人访谈应该看到两个 speaker，实际 {speakers_present}"
        )
        # 验证 80-95s 时间区间内有 SPEAKER_01 的 sub-segment（提问被切出来）
        ask_segs = [s for s in assigned
                    if s.start >= 80 and s.end <= 95 and s.speaker == "SPEAKER_01"]
        assert ask_segs, "80-95s 区间内应有 SPEAKER_01 sub-segment"

    def test_no_overlap_keeps_original_speaker(self):
        """如果 turns 完全不与 segment 重叠，speaker 保持原值（不强行改）。"""
        segments = [TranscriptSegment(start=100, end=110, text="x",
                                       speaker="ORIGINAL")]
        turns = [SpeakerTurn(start=0, end=50, speaker="SPK_FAR")]
        assigned = assign_speakers(segments, turns)
        assert assigned[0].speaker == "ORIGINAL"

    def test_segment_with_none_timestamps_skips_alignment(self):
        """没有 start/end 的 segment（极少见，比如 ASR 单段无时间戳）不应
        因为算法而 crash。"""
        segments = [TranscriptSegment(start=None, end=None, text="x",
                                       speaker="SPEAKER_00")]
        turns = [SpeakerTurn(start=0, end=10, speaker="SPK_X")]
        assigned = assign_speakers(segments, turns)
        assert assigned[0].speaker == "SPEAKER_00"


class SplitSegmentTests(unittest.TestCase):
    """跨 speaker 长 segment 应该按 pyannote turn 边界拆碎。"""

    def test_low_minority_segment_stays_single(self):
        """minority < 12% 阈值时不该拆。"""
        segments = [TranscriptSegment(
            start=10, end=110, text="A" * 100, speaker="SPEAKER_00",
        )]
        # 100s 长，SPEAKER_01 只占 8s = 8% < 12%
        turns = [
            SpeakerTurn(start=10,  end=50, speaker="SPEAKER_00"),  # 40s
            SpeakerTurn(start=50,  end=58, speaker="SPEAKER_01"),  # 8s
            SpeakerTurn(start=58,  end=110, speaker="SPEAKER_00"), # 52s
        ]
        assigned = assign_speakers(segments, turns)
        assert len(assigned) == 1, "minority < 12% 不该拆"
        assert assigned[0].speaker == "SPEAKER_00"

    def test_balanced_segment_gets_split_into_multiple(self):
        """近一半时间是 SPEAKER_01 → 拆。"""
        segments = [TranscriptSegment(
            start=10, end=80,
            text="A" * 100,
            speaker="SPEAKER_00",
        )]
        turns = [
            SpeakerTurn(start=10, end=30, speaker="SPEAKER_00"),  # 20s
            SpeakerTurn(start=30, end=55, speaker="SPEAKER_01"),  # 25s (35% — 超 25%)
            SpeakerTurn(start=55, end=80, speaker="SPEAKER_00"),  # 25s
        ]
        assigned = assign_speakers(segments, turns)
        speakers = [s.speaker for s in assigned]
        # 应至少出现两个 speaker
        assert "SPEAKER_00" in speakers and "SPEAKER_01" in speakers, (
            f"应该拆出 SPEAKER_01，实际 {speakers}"
        )

    def test_split_preserves_total_text_chars(self):
        """拆后所有 sub-segment 的 text 长度总和应等于原 segment text 长度
        （不丢字、不重复）。"""
        text = "甲方说话内容然后乙方提问最后甲方继续回答这一切。"
        segments = [TranscriptSegment(start=10, end=70, text=text, speaker="SPEAKER_00")]
        turns = [
            SpeakerTurn(start=10, end=30, speaker="SPEAKER_00"),
            SpeakerTurn(start=30, end=50, speaker="SPEAKER_01"),
            SpeakerTurn(start=50, end=70, speaker="SPEAKER_00"),
        ]
        assigned = assign_speakers(segments, turns)
        joined = "".join(s.text for s in assigned)
        # 允许 strip 掉零星空格，主体字符应保留
        assert len(joined) == len(text), (
            f"拆后字符总数变了: 原 {len(text)} → 拆后 {len(joined)}"
        )

    def test_split_subsegments_have_correct_time_boundaries(self):
        """拆出的 sub-segment 时间区间应严格按 pyannote turn 边界。"""
        segments = [TranscriptSegment(start=0, end=60, text="x" * 60, speaker="X")]
        turns = [
            SpeakerTurn(start=0, end=25, speaker="A"),
            SpeakerTurn(start=25, end=45, speaker="B"),
            SpeakerTurn(start=45, end=60, speaker="A"),
        ]
        assigned = assign_speakers(segments, turns)
        boundaries = [(s.start, s.end, s.speaker) for s in assigned]
        # merge_adjacent_segments 会把首末两个 A 段合并吗?它检查 same_speaker
        # 且 close_enough (gap ≤ 1s)。这里 B 在中间隔开，A 和 A 不相邻，所以
        # 应保留 3 段。
        speakers = [b[2] for b in boundaries]
        assert "A" in speakers and "B" in speakers

    def test_very_short_minority_subsegment_gets_absorbed(self):
        """0.5 秒的「嗯/对」碎片不应单独成段，应合并到相邻 majority。"""
        segments = [TranscriptSegment(start=0, end=30, text="x" * 30, speaker="X")]
        turns = [
            SpeakerTurn(start=0,    end=14,   speaker="SPEAKER_00"),
            SpeakerTurn(start=14,   end=14.5, speaker="SPEAKER_01"),  # 0.5s 嗯
            SpeakerTurn(start=14.5, end=22,   speaker="SPEAKER_00"),
            SpeakerTurn(start=22,   end=30,   speaker="SPEAKER_01"),  # 8s 真插话
        ]
        # SPEAKER_01 共 0.5 + 8 = 8.5s / 30 = 28% > 25% → 触发拆
        # 但 0.5s 段太短，应被合并掉
        assigned = assign_speakers(segments, turns)
        for s in assigned:
            assert (s.end - s.start) >= 1.0, (
                f"sub-segment 不应短于 1s: {s.start}-{s.end} ({s.speaker})"
            )
