#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import prose_script  # noqa: E402
import segment_script  # noqa: E402


class ProseScriptTests(unittest.TestCase):
    def test_soft_wrapping_stays_inside_one_paragraph(self):
        paragraphs = prose_script.parse_prose(
            "The first thought wraps\nacross two lines.\n\nThe second thought stands alone.\n"
        )

        self.assertEqual(
            [paragraph.text for paragraph in paragraphs],
            [
                "The first thought wraps across two lines.",
                "The second thought stands alone.",
            ],
        )
        self.assertEqual([paragraph.line for paragraph in paragraphs], [1, 4])

    def test_dialogue_tags_are_metadata_not_spoken_text(self):
        paragraphs = prose_script.parse_prose(
            "[host] What changes first?\n\n[guest] The spoken answer stays here.\n"
        )

        self.assertEqual([paragraph.speaker for paragraph in paragraphs], ["host", "guest"])
        self.assertEqual(
            [paragraph.text for paragraph in paragraphs],
            ["What changes first?", "The spoken answer stays here."],
        )

    def test_visual_markdown_blocks_are_rejected(self):
        samples = (
            "# Heading",
            "- list item",
            "> quoted note",
            "| visual | grid |",
            "visual | grid",
            "```text\nproduction note\n```",
        )

        for sample in samples:
            with self.subTest(sample=sample):
                with self.assertRaises(prose_script.ProseFormatError):
                    prose_script.parse_prose(sample)


class SegmentScriptTests(unittest.TestCase):
    def test_first_segmentation_creates_unique_assignment_placeholders(self):
        result = segment_script.segment("First complete thought.\n\nSecond complete thought.\n")

        self.assertEqual(result.preserved, 0)
        self.assertEqual(result.placeholders, 2)
        self.assertEqual(result.document["format"], "narrator")
        self.assertEqual(result.document["aspect"], "16:9")
        self.assertEqual(result.document["voice_id"], "")
        self.assertEqual(
            [beat["say"] for beat in result.document["beats"]],
            ["First complete thought.", "Second complete thought."],
        )
        self.assertNotEqual(
            result.document["beats"][0]["show"],
            result.document["beats"][1]["show"],
        )

    def test_dialogue_segmentation_creates_two_speaker_configuration(self):
        result = segment_script.segment(
            "[host] What changes first?\n\n"
            "[guest] The answer keeps one complete thought together.\n\n"
            "[host] Where does the next cut land?\n"
        )

        self.assertEqual(result.document["format"], "dialogue")
        self.assertEqual(set(result.document["speakers"]), {"host", "guest"})
        self.assertEqual(
            [beat["speaker"] for beat in result.document["beats"]],
            ["host", "guest", "host"],
        )
        self.assertNotIn("[host]", result.document["beats"][0]["say"])

    def test_dialogue_segmentation_requires_every_paragraph_tagged(self):
        with self.assertRaisesRegex(
            segment_script.SegmentationError, "tag every paragraph"
        ):
            segment_script.segment(
                "[host] What changes first?\n\nThe answer lost its speaker.\n"
            )

    def test_tagged_prose_converts_existing_narrator_metadata_to_dialogue(self):
        existing = {
            "format": "narrator",
            "voice_id": "old-narrator-voice",
            "beats": [],
        }

        result = segment_script.segment(
            "[host] What changes first?\n\n[guest] The answer follows.\n",
            existing,
        )

        self.assertEqual(result.document["format"], "dialogue")
        self.assertEqual(set(result.document["speakers"]), {"host", "guest"})
        self.assertNotIn("voice_id", result.document)

    def test_moved_placeholders_are_renumbered_without_colliding(self):
        existing = segment_script.segment(
            "First complete thought.\n\nSecond complete thought.\n"
        ).document

        result = segment_script.segment(
            "Second complete thought.\n\nA new thought.\n\nFirst complete thought.\n",
            existing,
        )

        self.assertEqual(result.placeholders, 3)
        self.assertEqual(
            [beat["show"]["lines"][1] for beat in result.document["beats"]],
            ["BEAT 01", "BEAT 02", "BEAT 03"],
        )

    def test_surviving_paragraphs_keep_visuals_across_insertion_and_reorder(self):
        existing = {
            "title": "Generic explainer",
            "format": "explainer",
            "beats": [
                {
                    "say": "First complete thought.",
                    "show": {"type": "capture", "path": "assets/first.png"},
                },
                {
                    "say": "Second complete thought.",
                    "show": {"type": "diagram", "path": "assets/second.png"},
                },
            ],
        }

        result = segment_script.segment(
            "Second complete thought.\n\nA newly inserted thought.\n\n"
            "First complete thought.\n",
            existing,
        )

        self.assertEqual(result.preserved, 2)
        self.assertEqual(result.placeholders, 1)
        self.assertEqual(result.document["title"], "Generic explainer")
        self.assertEqual(
            result.document["beats"][0]["show"]["path"], "assets/second.png"
        )
        self.assertEqual(
            result.document["beats"][2]["show"]["path"], "assets/first.png"
        )
        self.assertEqual(
            result.document["beats"][1]["show"]["lines"],
            ["ASSIGN VISUAL", "BEAT 02"],
        )

    def test_close_edit_keeps_visual_but_drops_an_invalid_cue(self):
        existing = {
            "beats": [
                {
                    "say": "The visual cuts when this exact phrase is spoken.",
                    "cue": "exact phrase",
                    "show": {"type": "diagram", "path": "assets/cut.png"},
                    "note": "keep future beat metadata",
                }
            ]
        }

        result = segment_script.segment(
            "The visual now cuts when the matching words are spoken.", existing
        )

        beat = result.document["beats"][0]
        self.assertEqual(result.preserved, 1)
        self.assertEqual(result.dropped_cues, 1)
        self.assertEqual(beat["show"]["path"], "assets/cut.png")
        self.assertEqual(beat["note"], "keep future beat metadata")
        self.assertNotIn("cue", beat)

    def test_cli_updates_the_requested_scenes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            prose = temp / "narration.md"
            scenes = temp / "scenes.json"
            prose.write_text("A complete spoken thought lives here.\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "src" / "segment_script.py"),
                    str(prose),
                    str(scenes),
                ],
                capture_output=True,
                text=True,
            )

            document = json.loads(scenes.read_text())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Segmented 1 paragraph(s)", result.stdout)
        self.assertEqual(
            document["beats"][0]["say"], "A complete spoken thought lives here."
        )


if __name__ == "__main__":
    unittest.main()
