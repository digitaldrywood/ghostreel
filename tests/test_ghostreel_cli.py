#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
            json.dumps(
                {
                    "title": "Test Short",
                    "beats": [
                        {
                            "say": (
                                "Start with one clear idea. Then connect each scene to "
                                "the sentence that gives it meaning."
                            )
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.project / "node_modules" / "playwright").mkdir(parents=True)
        (self.project / "src").mkdir()
        for module in ("lint_script.py", "prose_script.py", "tts_common.py"):
            shutil.copy2(ROOT / "src" / module, self.project / "src" / module)
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
            "if sys.argv[1] == '--preflight':\n"
            "    print('LOCAL_VOICE_ENGINE=kokoro')\n"
            "    raise SystemExit(0)\n"
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

    def _install_real_local_tts(self):
        for module in ("tts_local.py", "voices.py"):
            shutil.copy2(ROOT / "src" / module, self.project / "src" / module)

    def _existing_run(self):
        run = self.project / "out" / "test-short"
        (run / "nested").mkdir(parents=True)
        (run / "keep.txt").write_text("existing rough cut\n", encoding="utf-8")
        (run / "nested" / "frame.bin").write_bytes(b"existing frame\n")
        snapshot = {
            path.relative_to(run): path.read_bytes()
            for path in run.rglob("*")
            if path.is_file()
        }
        return run, snapshot

    def _assert_run_unchanged(self, run, snapshot):
        actual = {
            path.relative_to(run): path.read_bytes()
            for path in run.rglob("*")
            if path.is_file()
        }
        self.assertEqual(snapshot, actual)

    def _fake_kokoro_artifacts(self):
        root = self.project / "kokoro"
        python = root / "venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        (root / "kokoro-v1.0.onnx").touch()
        (root / "voices-v1.0.bin").touch()
        self.env["KOKORO_DIR"] = str(root)
        self.env["SCRATCH_ENGINE"] = "kokoro"

    def _write_dialogue_intake(self, host_voice="af_heart", guest_voice="am_michael"):
        (self.project / "examples" / "intake.json").write_text(
            json.dumps(
                {
                    "title": "Test Short",
                    "format": "dialogue",
                    "speakers": {
                        "host": {"local_voice": host_voice},
                        "guest": {"local_voice": guest_voice},
                    },
                    "beats": [
                        {"speaker": "host", "say": "Start with one clear idea."},
                        {
                            "speaker": "guest",
                            "say": "Then connect each scene to the sentence that gives it meaning.",
                        },
                    ],
                }
            ),
            encoding="utf-8",
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

    def test_missing_kokoro_and_piper_preserve_existing_rough_cut(self):
        self._install_real_local_tts()
        run, snapshot = self._existing_run()
        self.env.update(
            {
                "SCRATCH_ENGINE": "kokoro",
                "KOKORO_DIR": str(self.project / "missing-kokoro"),
                "PIPER_BIN": str(self.project / "missing-piper"),
                "PIPER_VOICE": str(self.project / "missing-voice.onnx"),
            }
        )

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python interpreter", result.stderr)
        self.assertIn("PIPER_BIN", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_invalid_kokoro_voice_preserves_existing_rough_cut(self):
        self._install_real_local_tts()
        self._fake_kokoro_artifacts()
        self.env["KOKORO_VOICE"] = "not_a_voice"
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown Kokoro voice", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_installed_bundle_missing_selected_voice_preserves_existing_rough_cut(self):
        self._install_real_local_tts()
        self._fake_kokoro_artifacts()
        kokoro_python = Path(self.env["KOKORO_DIR"]) / "venv" / "bin" / "python"
        kokoro_python.unlink()
        self._write_executable(
            kokoro_python,
            f"#!{sys.executable}\n"
            "print('MISSING_VOICES=af_heart')\n"
            "raise SystemExit(2)\n",
        )
        self.env["KOKORO_VOICE"] = "af_heart"
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("voices-v1.0.bin", result.stderr)
        self.assertIn("af_heart", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_missing_kokoro_runtime_dependency_preserves_existing_rough_cut(self):
        self._install_real_local_tts()
        self._fake_kokoro_artifacts()
        kokoro_python = Path(self.env["KOKORO_DIR"]) / "venv" / "bin" / "python"
        kokoro_python.unlink()
        self._write_executable(
            kokoro_python,
            f"#!{sys.executable}\n"
            "import sys\n"
            "print(\"IMPORT_ERROR=ModuleNotFoundError: No module named 'soundfile'\", file=sys.stderr)\n"
            "raise SystemExit(3)\n",
        )
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("soundfile", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_dialogue_missing_kokoro_preserves_existing_rough_cut(self):
        self._install_real_local_tts()
        self._write_dialogue_intake()
        self.env.update(
            {
                "SCRATCH_ENGINE": "kokoro",
                "KOKORO_DIR": str(self.project / "missing-kokoro"),
            }
        )
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dialogue rough cuts require Kokoro", result.stderr)
        self.assertIn("Piper cannot provide two voices", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_dialogue_rejects_explicit_piper_before_replacing_output(self):
        self._install_real_local_tts()
        self._write_dialogue_intake()
        self.env["SCRATCH_ENGINE"] = "piper"
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dialogue rough cuts require Kokoro", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_dialogue_duplicate_voices_preserve_existing_rough_cut(self):
        self._install_real_local_tts()
        self._fake_kokoro_artifacts()
        self._write_dialogue_intake(guest_voice="af_heart")
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("distinct local_voice", result.stderr)
        self._assert_run_unchanged(run, snapshot)

    def test_dialogue_invalid_voice_preserves_existing_rough_cut(self):
        self._install_real_local_tts()
        self._fake_kokoro_artifacts()
        self._write_dialogue_intake(guest_voice="not_a_voice")
        run, snapshot = self._existing_run()

        result = self._run("--rough", "examples/intake.json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown Kokoro voice", result.stderr)
        self._assert_run_unchanged(run, snapshot)


if __name__ == "__main__":
    unittest.main()
