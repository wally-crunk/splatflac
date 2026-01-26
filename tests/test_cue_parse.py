import textwrap
import tempfile
from pathlib import Path
import unittest

from splatflac import parse_cue


class CueParseTests(unittest.TestCase):
    def test_titles_with_quotes_and_apostrophes(self) -> None:
        cue_text = textwrap.dedent(
            '''
            FILE "audio.flac" WAVE
              TRACK 01 AUDIO
                TITLE "It's a test"
                INDEX 01 00:00:00
              TRACK 02 AUDIO
                TITLE "He said "Hello" today"
                INDEX 01 00:01:00
            '''
        ).lstrip()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            audio_path = tmp_path / "audio.flac"
            audio_path.write_bytes(b"")
            cue_path = tmp_path / "test.cue"
            cue_path.write_text(cue_text, encoding="utf-8")

            cue = parse_cue(cue_path)

        self.assertEqual(cue.entries[0].tracks[0].title, "It's a test")
        self.assertEqual(cue.entries[0].tracks[1].title, 'He said "Hello" today')


if __name__ == "__main__":
    unittest.main()
