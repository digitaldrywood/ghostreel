#!/usr/bin/env python3
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KineticStylesTests(unittest.TestCase):
    def test_outgoing_scene_stops_painting_during_incoming_fade(self):
        css = (ROOT / "src" / "kinetic.css").read_text()

        hidden_scene = re.search(r"\.scene\{([^}]*)\}", css)
        visible_scene = re.search(r"\.scene\.on\{([^}]*)\}", css)

        self.assertIsNotNone(hidden_scene)
        self.assertIsNotNone(visible_scene)
        transition = re.search(r"(?:^|;)transition:([^;]+)", hidden_scene.group(1))

        self.assertIsNotNone(transition)
        self.assertIn("visibility:hidden", hidden_scene.group(1))
        self.assertEqual("opacity .34s ease", transition.group(1))
        self.assertIn("visibility:visible", visible_scene.group(1))


class KineticTimelineTests(unittest.TestCase):
    def run_builder(self, beats, words=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        run = Path(temp.name)
        audio = run / "audio"
        audio.mkdir()
        intake = run / "intake.json"
        intake.write_text(json.dumps({"title": "Generic timeline", "beats": beats}))
        timing_beats = [
            {"audio_start": index * 4.0 + 0.5, "audio_end": index * 4.0 + 3.5}
            for index in range(len(beats))
        ]
        (audio / "timing.json").write_text(
            json.dumps({"duration": len(beats) * 4.0, "beats": timing_beats})
        )
        if words is not None:
            (audio / "words.json").write_text(json.dumps(words))

        result = subprocess.run(
            ["python3", str(ROOT / "src" / "build_kinetic.py"), str(intake), str(run)],
            capture_output=True,
            text=True,
        )
        return result, run

    def test_multiword_cue_uses_normalized_word_timestamp(self):
        beats = [
            {"say": "Opening card remains.", "show": {"type": "text"}},
            {
                "say": "Keep it visible until Switch Right Here please.",
                "cue": "switch right here",
                "show": {"type": "text"},
            },
        ]
        words = self.words_for(beats)
        words[7].update({"w": "Switch", "start": 6.25})
        words[8]["w"] = "RIGHT!"
        words[9]["w"] = "Here,"

        result, run = self.run_builder(beats, words)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[6250,()=>{hide('#s0')", (run / "ad.html").read_text())

    def test_repeated_cue_is_rejected_as_ambiguous(self):
        beats = [
            {"say": "Opening card remains.", "show": {"type": "text"}},
            {
                "say": "Go now, pause, then go now.",
                "cue": "go now",
                "show": {"type": "text"},
            },
        ]

        result, _ = self.run_builder(beats, self.words_for(beats))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beat 1: cue 'go now' is ambiguous", result.stderr)
        self.assertIn("word offsets 0, 4", result.stderr)

    def test_missing_cue_is_rejected(self):
        beats = [
            {"say": "Opening card remains.", "show": {"type": "text"}},
            {
                "say": "A different phrase appears here.",
                "cue": "not present",
                "show": {"type": "text"},
            },
        ]

        result, _ = self.run_builder(beats, self.words_for(beats))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "beat 1: cue 'not present' was not found in its aligned word span",
            result.stderr,
        )

    def test_cue_free_intake_uses_beat_timing_without_words_file(self):
        beats = [
            {"say": "Opening card remains.", "show": {"type": "text"}},
            {"say": "Second card follows.", "show": {"type": "text"}},
        ]

        result, run = self.run_builder(beats)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[4500,()=>{hide('#s0')", (run / "ad.html").read_text())

    def test_internal_first_beat_cue_is_rejected_to_preserve_opening_coverage(self):
        beats = [
            {
                "say": "Keep this hidden until reveal now.",
                "cue": "reveal now",
                "show": {"type": "text"},
            }
        ]

        result, _ = self.run_builder(beats, self.words_for(beats))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beat 0: cue 'reveal now' starts at word offset 4", result.stderr)
        self.assertIn("leaves the opening audio without a visual", result.stderr)

    @staticmethod
    def words_for(beats):
        words = []
        cursor = 0.5
        for beat in beats:
            for word in beat["say"].split():
                words.append({"w": word, "start": cursor, "end": cursor + 0.2})
                cursor += 0.5
        return words


if __name__ == "__main__":
    unittest.main()
