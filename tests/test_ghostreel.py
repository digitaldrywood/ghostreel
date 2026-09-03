#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


class GhostreelTests(unittest.TestCase):
    def test_rejected_paid_intake_preserves_output_and_skips_generators(self):
        slug = f"lint-rejection-{uuid.uuid4().hex}"
        run_dir = ROOT / "out" / slug
        run_dir.mkdir(parents=True)
        marker = run_dir / "keep.txt"
        marker.write_text("existing run\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            intake = temp / "rejected.json"
            intake.write_text(
                json.dumps(
                    {
                        "title": slug,
                        "beats": [
                            {
                                "say": "Every sentence stays short. The rhythm never changes.",
                                "show": {"type": "text", "lines": ["FLAT"]},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            invocation_log = temp / "python-invocations.txt"
            shim_dir = temp / "bin"
            shim_dir.mkdir()
            python_shim = shim_dir / "python3"
            python_shim.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$GHOSTREEL_TEST_INVOCATIONS\"\n"
                "exec \"$GHOSTREEL_TEST_PYTHON\" \"$@\"\n",
                encoding="utf-8",
            )
            python_shim.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "ELEVENLABS_API_KEY": "test-value",
                    "OPENAI_API_KEY": "test-value",
                    "GHOSTREEL_TEST_INVOCATIONS": str(invocation_log),
                    "GHOSTREEL_TEST_PYTHON": sys.executable,
                    "PATH": f"{shim_dir}{os.pathsep}{env['PATH']}",
                }
            )

            try:
                result = subprocess.run(
                    ["bash", str(ROOT / "ghostreel.sh"), str(intake)],
                    capture_output=True,
                    cwd=ROOT,
                    env=env,
                    text=True,
                )
                invocations = invocation_log.read_text(encoding="utf-8")
                marker_contents = marker.read_text(encoding="utf-8")
            finally:
                shutil.rmtree(run_dir)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("== narration lint (short vertical reel) ==", result.stdout)
        self.assertIn("Lint failed", result.stdout)
        self.assertEqual(marker_contents, "existing run\n")
        self.assertIn("src/lint_script.py --short-reel", invocations)
        self.assertNotIn("src/tts.py", invocations)
        self.assertNotIn("src/images.py", invocations)
        self.assertNotIn("src/music.py", invocations)


if __name__ == "__main__":
    unittest.main()
