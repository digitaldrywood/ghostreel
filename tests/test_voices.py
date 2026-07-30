import contextlib
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import voices  # noqa: E402


class VoiceCatalogTests(unittest.TestCase):
    def test_catalog_has_every_bundled_voice_once(self):
        self.assertEqual(54, len(voices.VOICE_INDEX))
        self.assertEqual(54, len(set(voices.VOICE_INDEX)))
        self.assertEqual(
            [(11, 9), (4, 4), (1, 2), (1, 0), (2, 2), (1, 1), (4, 1), (1, 2), (4, 4)],
            [(len(language.female), len(language.male)) for language in voices.LANGUAGES],
        )

    def test_voice_prefix_matches_catalog_gender(self):
        for voice, (language, gender) in voices.VOICE_INDEX.items():
            with self.subTest(voice=voice):
                self.assertEqual("f" if gender == "female" else "m", voice[1])
                self.assertTrue(language.sample)
                self.assertTrue(language.espeak_code)

    def test_voice_details_returns_language_and_gender(self):
        language, gender = voices.voice_details("jf_alpha")
        self.assertEqual("Japanese", language.name)
        self.assertEqual("ja", language.espeak_code)
        self.assertEqual("female", gender)

    def test_cli_list_does_not_require_the_model_or_video_dependencies(self):
        result = subprocess.run(
            [str(ROOT / "ghostreel.sh"), "--voices"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("| American English |", result.stdout)
        self.assertIn("af_heart", result.stdout)
        self.assertIn("zm_yunyang", result.stdout)
        self.assertIn("54 voices", result.stdout)

    def test_unknown_sample_voice_fails_before_loading_model(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "src/voices.py"), "sample", "not_a_voice"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("unknown Kokoro voice", result.stderr)
        self.assertIn("./ghostreel.sh --voices", result.stderr)

    def test_kokoro_paths_honor_the_configured_root(self):
        with mock.patch.dict("os.environ", {"KOKORO_DIR": "/tmp/kokoro-test"}):
            python, model, catalog = voices._kokoro_paths()
        self.assertEqual(Path("/tmp/kokoro-test/venv/bin/python"), python)
        self.assertEqual(Path("/tmp/kokoro-test/kokoro-v1.0.onnx"), model)
        self.assertEqual(Path("/tmp/kokoro-test/voices-v1.0.bin"), catalog)

    def test_missing_kokoro_install_lists_every_missing_path(self):
        missing = (
            Path("/missing/venv/bin/python"),
            Path("/missing/kokoro-v1.0.onnx"),
            Path("/missing/voices-v1.0.bin"),
        )
        with mock.patch.object(voices, "_kokoro_paths", return_value=missing):
            with self.assertRaisesRegex(SystemExit, "Kokoro is not installed") as raised:
                voices._load_kokoro()
        for path in missing:
            self.assertIn(str(path), str(raised.exception))

    def test_write_wav_uses_the_voice_language_and_configured_speed(self):
        kokoro = mock.Mock()
        kokoro.create.return_value = ([0.0], 24000)
        soundfile = mock.Mock()
        with mock.patch.dict(sys.modules, {"soundfile": soundfile}):
            with mock.patch.dict("os.environ", {"KOKORO_SPEED": "1.25"}):
                voices._write_wav(kokoro, "pf_dora", Path("sample.wav"))
        kokoro.create.assert_called_once_with(
            voices.VOICE_INDEX["pf_dora"][0].sample,
            voice="pf_dora",
            speed=1.25,
            lang="pt-br",
        )
        soundfile.write.assert_called_once_with(Path("sample.wav"), [0.0], 24000)

    def test_player_command_supports_override_and_detected_player(self):
        sample = Path("sample.wav")
        with mock.patch.dict("os.environ", {"GHOSTREEL_SAMPLE_PLAYER": "player --quiet"}):
            self.assertEqual(["player", "--quiet", "sample.wav"], voices._player_command(sample))
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(
                voices.shutil,
                "which",
                side_effect=lambda executable: "/usr/bin/ffplay" if executable == "ffplay" else None,
            ):
                self.assertEqual(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "sample.wav"],
                    voices._player_command(sample),
                )

    def test_play_sample_synthesizes_then_invokes_player(self):
        with mock.patch.object(voices, "_load_kokoro", return_value=object()):
            with mock.patch.object(voices, "_write_wav") as write_wav:
                with mock.patch.object(voices, "_player_command", return_value=["player"]):
                    with mock.patch.object(voices.subprocess, "run") as run:
                        with contextlib.redirect_stderr(io.StringIO()):
                            voices.play_sample("af_heart")
        self.assertEqual("af_heart", write_wav.call_args.args[1])
        run.assert_called_once_with(["player"], check=True)

    def test_gallery_html_references_every_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = voices.render_gallery(Path(temp_dir))
            page = output.read_text(encoding="utf-8")
        self.assertEqual(54, page.count("<audio "))
        for voice in voices.VOICE_INDEX:
            with self.subTest(voice=voice):
                self.assertIn(f'src="{voice}.mp3"', page)
                self.assertIn(f'href="{voice}.mp3"', page)

    def test_gallery_command_encodes_every_voice_and_writes_the_page(self):
        def fake_wav(_kokoro, _voice, path):
            path.write_bytes(b"wav")

        def fake_ffmpeg(command, check):
            self.assertTrue(check)
            Path(command[-1]).write_bytes(b"mp3")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "voices"
            with mock.patch.object(voices.shutil, "which", return_value="/usr/bin/ffmpeg"):
                with mock.patch.object(voices, "_load_kokoro", return_value=object()):
                    with mock.patch.object(voices, "_write_wav", side_effect=fake_wav):
                        with mock.patch.object(voices.subprocess, "run", side_effect=fake_ffmpeg):
                            with contextlib.redirect_stdout(io.StringIO()):
                                with contextlib.redirect_stderr(io.StringIO()):
                                    voices.generate_gallery(output)
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual(set(voices.VOICE_INDEX), {path.stem for path in output.glob("*.mp3")})

    def test_readme_has_a_raw_fallback_link_for_every_sample(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for voice in voices.VOICE_INDEX:
            with self.subTest(voice=voice):
                self.assertEqual(1, readme.count(f"docs/voices/{voice}.mp3?raw=1"))

    def test_printed_table_contains_every_voice_once(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            voices.print_voice_table()
        listed = re.findall(r"\b[a-z]{2}_[a-z]+\b", output.getvalue())
        self.assertEqual(set(voices.VOICE_INDEX), set(listed))
        self.assertEqual(len(voices.VOICE_INDEX), len(listed))


if __name__ == "__main__":
    unittest.main()
