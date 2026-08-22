#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AssembleTests(unittest.TestCase):
    def test_mixed_png_and_mp4_are_normalized_and_source_audio_removed(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenes_path = temp / "scenes.json"
            out = temp / "out"
            render = out / "render"
            audio = out / "audio"
            render.mkdir(parents=True)
            audio.mkdir()

            scenes_path.write_text(
                json.dumps(
                    {
                        "aspect": "16:9",
                        "beats": [
                            {"say": "Alpha", "show": {"type": "image"}},
                            {"say": "Beta", "show": {"type": "text"}},
                        ],
                    }
                )
            )
            (audio / "words.json").write_text(
                json.dumps(
                    [
                        {"w": "Alpha", "start": 0.0, "end": 4.0},
                        {"w": "Beta", "start": 4.0, "end": 8.0},
                    ]
                )
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=320x240",
                    "-frames:v",
                    "1",
                    str(render / "00.png"),
                ],
                check=True,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=160x90:r=24:d=0.2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=0.2",
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(render / "01.mp4"),
                ],
                check=True,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=mono:sample_rate=44100",
                    "-t",
                    "8",
                    "-c:a",
                    "libmp3lame",
                    str(audio / "vo.mp3"),
                ],
                check=True,
            )

            result = subprocess.run(
                ["bash", str(ROOT / "src" / "assemble.sh"), str(scenes_path), str(out)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for index in range(2):
                probe = json.loads(
                    subprocess.check_output(
                        [
                            ffprobe,
                            "-v",
                            "error",
                            "-show_streams",
                            "-show_format",
                            "-of",
                            "json",
                            str(out / "seg" / f"{index:02d}.mp4"),
                        ],
                        text=True,
                    )
                )
                self.assertEqual([stream["codec_type"] for stream in probe["streams"]], ["video"])
                video = probe["streams"][0]
                self.assertEqual((video["width"], video["height"]), (1920, 1080))
                self.assertEqual(video["pix_fmt"], "yuv420p")
                self.assertEqual(video["avg_frame_rate"], "30/1")
                self.assertAlmostEqual(float(probe["format"]["duration"]), 4.0, delta=0.04)

            final_probe = json.loads(
                subprocess.check_output(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-show_streams",
                        "-of",
                        "json",
                        str(out / "final.mp4"),
                    ],
                    text=True,
                )
            )
            audio_streams = [
                stream for stream in final_probe["streams"] if stream["codec_type"] == "audio"
            ]
            self.assertEqual(len(audio_streams), 1)
            self.assertEqual(audio_streams[0]["channels"], 1)

    def test_missing_visual_lists_both_accepted_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenes_path = temp / "scenes.json"
            out = temp / "out"
            (out / "audio").mkdir(parents=True)
            scenes_path.write_text(json.dumps({"beats": [{"say": "Alpha"}]}))
            (out / "audio" / "words.json").write_text(
                json.dumps([{"w": "Alpha", "start": 0.0, "end": 4.0}])
            )

            result = subprocess.run(
                ["bash", str(ROOT / "src" / "assemble.sh"), str(scenes_path), str(out)],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing visual for beat 0", result.stderr)
            self.assertIn("00.png", result.stderr)
            self.assertIn("00.mp4", result.stderr)

    def run_assemble(self, scenes, words):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenes_path = temp / "scenes.json"
            out = temp / "out"
            render = out / "render"
            audio = out / "audio"
            render.mkdir(parents=True)
            audio.mkdir()

            scenes_path.write_text(json.dumps({"aspect": "16:9", "beats": scenes}))
            (audio / "words.json").write_text(json.dumps(words))
            (audio / "vo.mp3").touch()
            for index in range(len(scenes)):
                (render / f"{index:02d}.png").touch()

            fake_bin = temp / "bin"
            fake_bin.mkdir()
            fake_ffmpeg = fake_bin / "ffmpeg"
            fake_ffmpeg.write_text(
                "#!/bin/sh\n"
                "last=\n"
                'for arg in "$@"; do\n'
                '  case "$arg" in\n'
                '    *.mp3) [ -f "$arg" ] || exit 2 ;;\n'
                '  esac\n'
                '  last="$arg"\n'
                "done\n"
                ': > "$last"\n'
            )
            fake_ffmpeg.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                ["bash", str(ROOT / "src" / "assemble.sh"), str(scenes_path), str(out)],
                capture_output=True,
                env=env,
                text=True,
            )
            windows_path = out / "windows.txt"
            windows = windows_path.read_text().splitlines() if windows_path.exists() else []
            return result, windows

    def test_full_cue_phrase_chooses_the_complete_sequence(self):
        scenes = [
            {
                "say": "Alpha opens",
                "cue": "Alpha",
                "show": {"type": "image", "path": "assets/alpha.png"},
            },
            {
                "say": "Beta cue drifts. Cue lands here",
                "cue": "CUE lands!",
                "show": {"type": "diagram", "path": "assets/beta.png"},
            },
            {
                "say": "Gamma finishes",
                "show": {"type": "capture", "path": "assets/gamma.png"},
            },
        ]
        words = [
            {"w": "Alpha", "start": 0.0, "end": 1.0},
            {"w": "opens", "start": 1.0, "end": 5.0},
            {"w": "Beta", "start": 5.0, "end": 6.0},
            {"w": "cue", "start": 6.0, "end": 7.0},
            {"w": "drifts.", "start": 7.0, "end": 9.0},
            {"w": "Cue", "start": 9.0, "end": 10.0},
            {"w": "lands", "start": 10.0, "end": 11.0},
            {"w": "here", "start": 11.0, "end": 14.0},
            {"w": "Gamma", "start": 14.0, "end": 15.0},
            {"w": "finishes", "start": 15.0, "end": 18.0},
        ]

        result, windows = self.run_assemble(scenes, words)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            windows,
            ["0 0.000 9.000", "1 9.000 5.000", "2 14.000 4.000"],
        )

    def test_diagram_and_still_minimum_dwell_are_accepted(self):
        scenes = [
            {
                "say": "Diagram holds",
                "show": {"type": "diagram", "path": "assets/diagram.png"},
            },
            {
                "say": "Still holds",
                "show": {"type": "image", "path": "assets/still.png"},
            },
        ]
        words = [
            {"w": "Diagram", "start": 0.0, "end": 1.0},
            {"w": "holds", "start": 1.0, "end": 5.0},
            {"w": "Still", "start": 5.0, "end": 6.0},
            {"w": "holds", "start": 6.0, "end": 9.0},
        ]

        result, windows = self.run_assemble(scenes, words)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(windows, ["0 0.000 5.000", "1 5.000 4.000"])

    def test_opening_silence_is_covered_from_zero(self):
        scenes = [
            {
                "say": "Alpha opens",
                "show": {"type": "image", "path": "assets/alpha.png"},
            },
            {
                "say": "Beta closes",
                "show": {"type": "image", "path": "assets/beta.png"},
            },
        ]
        words = [
            {"w": "Alpha", "start": 1.0, "end": 2.0},
            {"w": "opens", "start": 2.0, "end": 5.0},
            {"w": "Beta", "start": 5.0, "end": 6.0},
            {"w": "closes", "start": 6.0, "end": 9.0},
        ]

        result, windows = self.run_assemble(scenes, words)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(windows, ["0 0.000 5.000", "1 5.000 4.000"])

    def test_internal_first_beat_cue_rejects_uncovered_audio(self):
        scenes = [
            {
                "say": "Alpha cue lands",
                "cue": "cue lands",
                "show": {"type": "image", "path": "assets/alpha.png"},
            }
        ]
        words = [
            {"w": "Alpha", "start": 0.0, "end": 1.0},
            {"w": "cue", "start": 1.0, "end": 2.0},
            {"w": "lands", "start": 2.0, "end": 5.0},
        ]

        result, _ = self.run_assemble(scenes, words)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beat 0", result.stderr.lower())
        self.assertIn("opening audio without a visual", result.stderr.lower())

    def test_cue_phrase_ignores_standalone_punctuation_tokens(self):
        scenes = [
            {
                "say": "Wait — now",
                "cue": "Wait — now",
                "show": {"type": "image", "path": "assets/wait.png"},
            }
        ]
        words = [
            {"w": "Wait", "start": 0.0, "end": 1.0},
            {"w": "—", "start": 1.0, "end": 1.0},
            {"w": "now", "start": 1.0, "end": 4.0},
        ]

        result, windows = self.run_assemble(scenes, words)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(windows, ["0 0.000 4.000"])

    def test_unsatisfiable_diagram_and_still_dwell_report_the_beat(self):
        cases = (("diagram", 4.5, "5.000"), ("image", 3.5, "4.000"))

        for visual_type, audio_end, minimum in cases:
            with self.subTest(visual_type=visual_type):
                scenes = [
                    {
                        "say": "Visual rushes",
                        "show": {"type": visual_type, "path": "assets/visual.png"},
                    }
                ]
                words = [
                    {"w": "Visual", "start": 0.0, "end": 1.0},
                    {"w": "rushes", "start": 1.0, "end": audio_end},
                ]

                result, _ = self.run_assemble(scenes, words)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("beat 0", result.stderr.lower())
                self.assertIn(visual_type, result.stderr.lower())
                self.assertIn(minimum, result.stderr)
                self.assertIn("lengthen narration", result.stderr.lower())

    def test_next_cue_that_breaks_dwell_reports_both_beats(self):
        scenes = [
            {
                "say": "Diagram holds",
                "show": {"type": "diagram", "path": "assets/diagram.png"},
            },
            {
                "say": "Next cue lands",
                "cue": "cue lands",
                "show": {"type": "image", "path": "assets/next.png"},
            },
        ]
        words = [
            {"w": "Diagram", "start": 0.0, "end": 1.0},
            {"w": "holds", "start": 1.0, "end": 2.0},
            {"w": "Next", "start": 2.0, "end": 3.0},
            {"w": "cue", "start": 3.0, "end": 4.0},
            {"w": "lands", "start": 4.0, "end": 8.0},
        ]

        result, _ = self.run_assemble(scenes, words)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("beat 0 (diagram)", result.stderr.lower())
        self.assertIn("before beat 1 starts", result.stderr.lower())
        self.assertIn("move beat 1's cue later", result.stderr.lower())

    def test_missing_and_ambiguous_cues_report_the_beat(self):
        words = [
            {"w": "Cue", "start": 0.0, "end": 1.0},
            {"w": "lands", "start": 1.0, "end": 2.0},
            {"w": "then", "start": 2.0, "end": 3.0},
            {"w": "cue", "start": 3.0, "end": 4.0},
            {"w": "lands", "start": 4.0, "end": 8.0},
        ]
        base = {
            "say": "Cue lands then cue lands",
            "show": {"type": "image", "path": "assets/still.png"},
        }

        for cue, diagnostic in (("never lands", "not found"), ("cue lands", "ambiguous")):
            with self.subTest(cue=cue):
                result, _ = self.run_assemble([{**base, "cue": cue}], words)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("beat 0", result.stderr.lower())
                self.assertIn(diagnostic, result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
