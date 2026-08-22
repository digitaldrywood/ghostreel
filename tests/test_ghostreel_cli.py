#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GhostreelCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        shutil.copy2(ROOT / "ghostreel.sh", self.project / "ghostreel.sh")
        (self.project / "examples").mkdir()
        (self.project / "examples" / "intake.json").write_text(
            json.dumps({"title": "Test Short", "beats": [{"say": "Hello."}]}),
            encoding="utf-8",
        )
        (self.project / "node_modules" / "playwright").mkdir(parents=True)
        (self.project / "src").mkdir()
        self._write_pipeline_stubs()
        self.env = os.environ.copy()
        self.env.pop("ELEVENLABS_API_KEY", None)
        self.env.pop("OPENAI_API_KEY", None)
        self.env.pop("GHOSTREEL_NODE_PATH", None)
        self.env["PATH"] = str(self._make_path_without_convert())

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_executable(self, path, contents):
        path.write_text(contents, encoding="utf-8")
        path.chmod(0o755)

    def _make_path_without_convert(self):
        fake_bin = self.project / "bin"
        fake_bin.mkdir()
        for command in ("bash", "sh", "dirname", "sed", "awk", "rm", "mkdir", "cp", "python3"):
            target = shutil.which(command)
            self.assertIsNotNone(target, f"test dependency missing: {command}")
            (fake_bin / command).symlink_to(target)

        self._write_executable(
            fake_bin / "node",
            "#!/bin/sh\n: > \"$3\"\n",
        )
        self._write_executable(
            fake_bin / "ffmpeg",
            "#!/bin/sh\n"
            "last=\n"
            "for arg in \"$@\"; do last=\"$arg\"; done\n"
            ': > "$last"\n',
        )
        self.assertFalse((fake_bin / "convert").exists())
        return fake_bin

    def _write_pipeline_stubs(self):
        self._write_executable(
            self.project / "src" / "tts_local.py",
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            "out = pathlib.Path(sys.argv[2]) / 'audio'\n"
            "out.mkdir(parents=True, exist_ok=True)\n"
            "(out / 'vo.mp3').touch()\n"
            "(out / 'words.json').write_text(json.dumps([{'w': 'Hello.', 'start': 0.0, 'end': 1.0}]))\n"
            "print('VO_CHARS=6')\n",
        )
        self._write_executable(
            self.project / "src" / "build_kinetic.py",
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "(pathlib.Path(sys.argv[2]) / 'ad.html').touch()\n"
            "print('DURATION=1')\n",
        )
        self._write_executable(
            self.project / "src" / "cheatsheet.py",
            "#!/usr/bin/env python3\n"
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[sys.argv.index('--out') + 1]).touch()\n",
        )
        (self.project / "src" / "record_html.mjs").touch()

    def _run(self, *args):
        return subprocess.run(
            [str(self.project / "ghostreel.sh"), *args],
            cwd=self.project,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_rough_cut_completes_without_convert(self):
        result = self._run("--rough", "examples/intake.json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DONE -> out/test-short/short.mp4", result.stdout)
        self.assertTrue((self.project / "out" / "test-short" / "short.mp4").is_file())

    def test_paid_run_requires_convert_before_replacing_output(self):
        previous = self.project / "out" / "test-short" / "keep.txt"
        previous.parent.mkdir(parents=True)
        previous.write_text("keep", encoding="utf-8")

        result = self._run("examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing dependency: convert", result.stdout)
        self.assertEqual(previous.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
