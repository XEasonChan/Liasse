import tempfile
import unittest
from pathlib import Path

from local_transcriber.exporters import export_srt
from local_transcriber.models import TranscriptSegment


class ExporterTests(unittest.TestCase):
    def test_export_srt(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "out.srt"
            export_srt(
                path,
                [
                    TranscriptSegment(
                        start=1.25,
                        end=3.5,
                        speaker="SPEAKER_00",
                        text="测试",
                    )
                ],
            )

            self.assertIn("00:00:01,250 --> 00:00:03,500", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
