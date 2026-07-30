#!/usr/bin/env python3
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import lint_script  # noqa: E402


PASSING_NARRATION = (
    "Morning light fills every window. "
    "Footsteps cross the quiet wooden hallway. "
    "A kettle warms while the waking house settles into its familiar morning rhythm. "
    "The first visitor arrives with bread, and soon another friend brings flowers from the garden beside the road. "
    "Conversation gathers naturally around the kitchen table while each person finds a chair and offers a story from the week. "
    "By the time the meal begins, the small room feels generous because everyone has added something useful, personal, and carefully chosen. "
    "Later, when the plates are empty and evening rain moves across the windows, nobody hurries toward the door or watches the clock. "
    "The gathering lasts because ordinary details carry it forward, from the warm bread and bright flowers to the patient stories that make old friends feel newly understood. "
    "After the final guest leaves, the host turns off each lamp and pauses beside the table, where a few crumbs and folded napkins hold the shape of an evening built through many small acts of attention. "
    "Tomorrow the room will return to its usual purpose, but tonight it carries the easy silence that follows good company, shared work, unforced laughter, and enough time for every person to finish the thought they came to say."
)


class LintScriptTests(unittest.TestCase):
    def run_lint(self, path):
        return subprocess.run(
            [sys.executable, str(ROOT / "src" / "lint_script.py"), str(path)],
            capture_output=True,
            text=True,
        )

    def call_main(self, path):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            return_code = lint_script.main([str(path)])
        return return_code, stdout.getvalue(), stderr.getvalue()

    def test_flat_reference_fixture_pins_distribution_arithmetic(self):
        fixture = ROOT / "tests" / "fixtures" / "lint_flat_reference.txt"
        narration = lint_script.load_input(fixture)
        distribution = lint_script.analyze_distribution(narration.text)

        self.assertEqual(distribution.sentence_count, 25)
        self.assertAlmostEqual(distribution.mean_words, 9.72)
        self.assertAlmostEqual(distribution.stddev_words, 4.703360500748374)
        self.assertEqual(distribution.long_sentence_count, 1)
        self.assertEqual(distribution.over_30_count, 0)
        self.assertEqual(distribution.short_sentence_count, 7)
        self.assertEqual(
            {diagnostic.code for diagnostic in lint_script.rhythm_diagnostics(distribution)},
            {
                "rhythm-mean-words",
                "rhythm-stddev-words",
                "rhythm-long-sentence-percent",
                "rhythm-over-30-count",
                "rhythm-short-sentence-percent",
            },
        )

    def test_markdown_calibration_sample_passes_and_reports_distribution(self):
        return_code, stdout, stderr = self.call_main(ROOT / "docs" / "the-method.md")

        self.assertEqual(return_code, 0, stdout + stderr)
        self.assertIn("Mode: Markdown calibration prose (rhythm only)", stdout)
        self.assertIn("Mean sentence length: 12.20 words", stdout)
        self.assertIn("Lint passed.", stdout)

    def test_repository_scenes_example_passes(self):
        return_code, stdout, stderr = self.call_main(
            ROOT / "examples" / "scenes.example.json"
        )

        self.assertEqual(return_code, 0, stdout + stderr)
        self.assertIn("Mode: scenes.json narration", stdout)
        self.assertIn("Lint passed.", stdout)

    def test_scenes_report_writing_issues_with_beat_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scenes = Path(temp_dir) / "scenes.json"
            scenes.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "say": (
                                    "Here's the thing. Experts say this robust plan costs $20. "
                                    "Read that again."
                                ),
                                "show": {"type": "image", "path": "assets/one.png"},
                            }
                        ]
                    }
                )
            )

            return_code, stdout, _ = self.call_main(scenes)

        self.assertEqual(return_code, 1)
        self.assertIn("[banned-word] at beat 1", stdout)
        self.assertIn("[throat-clearing] at beat 1", stdout)
        self.assertIn("[weasel-attribution] at beat 1", stdout)
        self.assertIn("[written-number] at beat 1", stdout)
        self.assertIn("[spoken-symbol] at beat 1", stdout)
        self.assertIn("[fake-profound-kicker] at beat 1", stdout)

    def test_duplicate_visual_is_rejected(self):
        shows = (
            (1, {"type": "capture", "path": "assets/shared.png"}),
            (2, {"type": "capture", "path": "assets/shared.png"}),
        )

        diagnostics = lint_script.duplicate_visual_diagnostics(shows)

        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].code, "duplicate-visual")
        self.assertEqual(diagnostics[0].label, "beat 2")
        self.assertIn("beat 1", diagnostics[0].message)

    def test_banned_pattern_signals_are_detected(self):
        samples = {
            "binary-contrast": "It's not speed, it's rhythm.",
            "throat-clearing": "Here's the thing. State the point.",
            "faux-insight": "What most people get wrong is timing.",
            "colon-reveal": "The result: silence.",
            "importance-puffery": "This cannot be overstated.",
            "weasel-attribution": "Studies, suggest a change.",
            "negative-listing": "No camera. No editor.",
            "dramatic-fragmentation": "And one. And two.",
            "rhetorical-setup": "Why? Because it works.",
            "fake-profound-kicker": "Let that sink in.",
            "summary-recap": "To sum up, stop.",
        }

        for rule in lint_script.PATTERN_RULES:
            with self.subTest(rule=rule.code):
                self.assertRegex(samples[rule.code], rule.expression)

        self.assertRegex(
            "A paradigm—shift is still banned.",
            lint_script.phrase_expression("paradigm shift"),
        )

    def test_spoken_form_signals_are_detected(self):
        narration = lint_script.NarrationInput(
            segments=(
                lint_script.Segment(
                    "beat 1",
                    "As mentioned above, NASA costs $20 (before tax).",
                ),
                lint_script.Segment(
                    "beat 2",
                    "- Read this bullet. <break time='1s' />",
                ),
            ),
            shows=(),
            mode="scenes.json narration",
            enforce_writing_rules=True,
        )

        diagnostics = lint_script.writing_diagnostics(narration)

        self.assertEqual(
            {diagnostic.code for diagnostic in diagnostics},
            {
                "written-number",
                "spoken-symbol",
                "parenthetical",
                "page-reference",
                "acronym",
                "break-tag",
                "visual-layout",
            },
        )
        visual_layout = next(
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.code == "visual-layout"
        )
        self.assertEqual(visual_layout.label, "beat 2")

    def test_spatial_above_and_below_are_not_page_references(self):
        narration = lint_script.NarrationInput(
            segments=(
                lint_script.Segment(
                    "beat 1",
                    "Clouds drift above the hills while rain falls below the tree line.",
                ),
            ),
            shows=(),
            mode="scenes.json narration",
            enforce_writing_rules=True,
        )

        diagnostics = lint_script.writing_diagnostics(narration)

        self.assertNotIn(
            "page-reference",
            {diagnostic.code for diagnostic in diagnostics},
        )

    def test_passing_scenes_clear_full_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scenes = Path(temp_dir) / "scenes.json"
            scenes.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "say": PASSING_NARRATION,
                                "show": {"type": "text", "lines": ["WELCOME HOME"]},
                            }
                        ]
                    }
                )
            )

            return_code, stdout, stderr = self.call_main(scenes)

        self.assertEqual(return_code, 0, stdout + stderr)
        self.assertIn("Mode: scenes.json narration", stdout)
        self.assertIn("Lint passed.", stdout)

    def test_invalid_json_returns_an_input_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            scenes = Path(temp_dir) / "scenes.json"
            scenes.write_text("{")

            return_code, _, stderr = self.call_main(scenes)

        self.assertEqual(return_code, 2)
        self.assertIn("invalid JSON", stderr)

    def test_run_script_stops_before_storyboard_when_lint_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenes = temp / "scenes.json"
            scenes.write_text(
                json.dumps(
                    {
                        "beats": [
                            {
                                "say": "Every sentence stays short. The rhythm never changes.",
                                "show": {"type": "text", "lines": ["FLAT"]},
                            }
                        ]
                    }
                )
            )

            result = subprocess.run(
                ["bash", str(ROOT / "src" / "run.sh"), str(scenes)],
                capture_output=True,
                cwd=temp,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("==> 1. lint", result.stdout)
        self.assertNotIn("==> 2. storyboard", result.stdout)


if __name__ == "__main__":
    unittest.main()
