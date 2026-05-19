import unittest

from local_transcriber.alignment import assign_speakers, overlap_seconds
from local_transcriber.models import SpeakerTurn, TranscriptSegment


class AlignmentTests(unittest.TestCase):
    def test_overlap_seconds(self):
        self.assertEqual(overlap_seconds(1, 5, 3, 6), 2)
        self.assertEqual(overlap_seconds(1, 2, 3, 4), 0)
        self.assertEqual(overlap_seconds(None, 2, 1, 3), 0)

    def test_assigns_largest_overlap(self):
        segments = [TranscriptSegment(start=10, end=20, text="hello")]
        turns = [
            SpeakerTurn(start=0, end=12, speaker="SPEAKER_00"),
            SpeakerTurn(start=12, end=25, speaker="SPEAKER_01"),
        ]

        assigned = assign_speakers(segments, turns)

        self.assertEqual(assigned[0].speaker, "SPEAKER_01")


if __name__ == "__main__":
    unittest.main()
