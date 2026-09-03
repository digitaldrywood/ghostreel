#!/usr/bin/env python3
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MusicStageTests(unittest.TestCase):
    def test_prebuilt_stereo_bed_changes_final_mono_audio_for_full_duration(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg and ffprobe are required")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            out = temp / "out"
            out.mkdir()
            scenes = temp / "scenes.json"
            scenes.write_text(json.dumps({"music_prompt": "unused test prompt"}))

            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=navy:s=320x180:r=30:d=6",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=mono:sample_rate=44100",
                    "-t",
                    "6",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-ac",
                    "1",
                    str(out / "final.mp4"),
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
                    "sine=frequency=880:duration=1",
                    "-filter_complex",
                    "[0:a]asplit=2[left][right];[left][right]join=inputs=2:channel_layout=stereo",
                    "-c:a",
                    "libmp3lame",
                    str(out / "music.mp3"),
                ],
                check=True,
            )

            before_volume = self.mean_volume(ffmpeg, out / "final.mp4")
            result = subprocess.run(
                ["bash", str(ROOT / "src" / "music.sh"), str(scenes), str(out)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("reusing", result.stdout)
            self.assertIn("mixed", result.stdout)

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
                        str(out / "final.mp4"),
                    ],
                    text=True,
                )
            )
            audio_streams = [
                stream for stream in probe["streams"] if stream["codec_type"] == "audio"
            ]
            self.assertEqual(len(audio_streams), 1)
            self.assertEqual(audio_streams[0]["channels"], 1)
            self.assertAlmostEqual(float(probe["format"]["duration"]), 6.0, delta=0.1)

            after_volume = self.mean_volume(ffmpeg, out / "final.mp4")
            ending_volume = self.mean_volume(
                ffmpeg, out / "final.mp4", start=5.0, duration=0.5
            )
            self.assertLess(before_volume, -80.0)
            self.assertGreater(after_volume, -50.0)
            self.assertGreater(ending_volume, -50.0)

    def test_pipeline_map_runs_music_after_assembly(self):
        pipeline = (ROOT / "src" / "run.sh").read_text()

        assemble = pipeline.index("bash src/assemble.sh $SCENES $OUT")
        music = pipeline.index("bash src/music.sh $SCENES $OUT")
        caption = pipeline.index("==> 9. caption")
        self.assertLess(assemble, music)
        self.assertLess(music, caption)

    @staticmethod
    def mean_volume(ffmpeg, media, *, start=None, duration=None):
        command = [ffmpeg, "-hide_banner", "-nostats"]
        if start is not None:
            command.extend(["-ss", str(start)])
        command.extend(["-i", str(media)])
        if duration is not None:
            command.extend(["-t", str(duration)])
        command.extend(["-af", "volumedetect", "-f", "null", "-"])
        result = subprocess.run(command, capture_output=True, text=True)
        match = re.search(r"mean_volume: (-?\w+(?:\.\w+)?) dB", result.stderr)
        if not match:
            raise AssertionError(result.stderr)
        return float(match.group(1))


if __name__ == "__main__":
    unittest.main()
