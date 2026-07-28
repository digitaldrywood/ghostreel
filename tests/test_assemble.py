#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AssembleTests(unittest.TestCase):
    def test_cue_uses_tts_word_schema_to_set_visual_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            scenes_path = temp / "scenes.json"
            out = temp / "out"
            render = out / "render"
            render.mkdir(parents=True)

            scenes_path.write_text(
                json.dumps(
                    {
                        "aspect": "16:9",
                        "beats": [
                            {"say": "Alpha opens"},
                            {"say": "Beta cue lands here", "cue": "lands"},
                            {"say": "Gamma finishes"},
                        ],
                    }
                )
            )
            (out / "words.json").write_text(
                json.dumps(
                    [
                        {"w": "Alpha", "start": 0.0, "end": 0.5},
                        {"w": "opens", "start": 0.5, "end": 1.0},
                        {"w": "Beta", "start": 1.0, "end": 1.5},
                        {"w": "cue", "start": 1.5, "end": 2.0},
                        {"w": "lands", "start": 2.0, "end": 2.5},
                        {"w": "here", "start": 2.5, "end": 3.0},
                        {"w": "Gamma", "start": 3.0, "end": 3.5},
                        {"w": "finishes", "start": 3.5, "end": 4.0},
                    ]
                )
            )
            for index in range(3):
                (render / f"{index:02d}.png").touch()

            fake_bin = temp / "bin"
            fake_bin.mkdir()
            fake_ffmpeg = fake_bin / "ffmpeg"
            fake_ffmpeg.write_text(
                "#!/bin/sh\n"
                "last=\n"
                'for arg in "$@"; do\n'
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
                    "1 2.000 1.000",
                    "2 3.000 1.000",
                ],
            )


if __name__ == "__main__":
    unittest.main()
