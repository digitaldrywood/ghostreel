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
                        {"w": "Alpha", "start": 0.0, "end": 0.5},
                        {"w": "Beta", "start": 0.5, "end": 1.0},
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
                    "1",
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
                self.assertAlmostEqual(float(probe["format"]["duration"]), 0.5, delta=0.04)

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
                json.dumps([{"w": "Alpha", "start": 0.0, "end": 1.0}])
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

    def test_paragraph_and_sentence_beats_render_with_internal_cue(self):
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
                            {"say": "Alpha opens"},
                            {"say": "Beta begins. Cue lands here", "cue": "Cue"},
                            {"say": "Gamma finishes"},
                        ],
                    }
                )
            )
            (audio / "words.json").write_text(
                json.dumps(
                    [
                        {"w": "Alpha", "start": 0.0, "end": 0.5},
                        {"w": "opens", "start": 0.5, "end": 1.0},
                        {"w": "Beta", "start": 1.0, "end": 1.5},
                        {"w": "begins.", "start": 1.5, "end": 2.0},
                        {"w": "Cue", "start": 2.0, "end": 2.5},
                        {"w": "lands", "start": 2.5, "end": 3.0},
                        {"w": "here", "start": 3.0, "end": 3.5},
                        {"w": "Gamma", "start": 3.5, "end": 4.0},
                        {"w": "finishes", "start": 4.0, "end": 4.5},
                    ]
                )
            )
            (audio / "vo.mp3").touch()
            for index in range(3):
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

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (out / "windows.txt").read_text().splitlines(),
                [
                    "0 0.000 2.000",
                    "1 2.000 1.500",
                    "2 3.500 1.000",
                ],
            )


if __name__ == "__main__":
    unittest.main()
