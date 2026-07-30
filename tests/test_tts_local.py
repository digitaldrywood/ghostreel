#!/usr/bin/env python3
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import tts_local  # noqa: E402


class LocalTtsTests(unittest.TestCase):
    def test_transcript_and_timings_keep_one_continuous_read(self):
        text, spans = tts_local.build_transcript(
            [{"say": "  First thought.  "}, {"say": "Second thought."}]
        )
        self.assertEqual("First thought.\nSecond thought.", text)
        self.assertEqual([(0, 14), (15, 30)], spans)

        words, timing = tts_local.approximate_timings(text, spans, 3.0)
        self.assertEqual(3.0, timing["duration"])
        self.assertEqual(0.0, timing["beats"][0]["audio_start"])
        self.assertEqual(3.0, timing["beats"][1]["audio_end"])
        self.assertEqual(["First", "thought", "Second", "thought"], [word["w"] for word in words])

    def test_make_kokoro_routes_the_selected_voice_language(self):
        soundfile = mock.Mock()
        kokoro = mock.Mock()
        kokoro.create.return_value = ([0.0], 24000)
        kokoro_module = mock.Mock()
        kokoro_module.Kokoro.return_value = kokoro

        with mock.patch.object(tts_local, "reexec_into_kokoro_venv"):
            with mock.patch.dict(
                sys.modules,
                {"soundfile": soundfile, "kokoro_onnx": kokoro_module},
            ):
                with mock.patch.dict(
                    os.environ,
                    {"KOKORO_VOICE": "jf_alpha", "KOKORO_SPEED": "1.1"},
                ):
                    speak = tts_local.make_kokoro()
                    speak("sample", "sample.wav")

        kokoro_module.Kokoro.assert_called_once_with(tts_local.KOKORO_MODEL, tts_local.KOKORO_VOICES)
        kokoro.create.assert_called_once_with(
            "sample", voice="jf_alpha", speed=1.1, lang="ja"
        )
        soundfile.write.assert_called_once_with("sample.wav", [0.0], 24000)

    def test_make_kokoro_rejects_an_unknown_voice(self):
        kokoro_module = mock.Mock()
        with mock.patch.object(tts_local, "reexec_into_kokoro_venv"):
            with mock.patch.dict(
                sys.modules,
                {"soundfile": mock.Mock(), "kokoro_onnx": kokoro_module},
            ):
                with mock.patch.dict(os.environ, {"KOKORO_VOICE": "not_a_voice"}):
                    with self.assertRaisesRegex(SystemExit, "unknown Kokoro voice"):
                        tts_local.make_kokoro()

    def test_pick_engine_falls_back_only_when_kokoro_is_missing(self):
        with mock.patch.dict(os.environ, {"SCRATCH_ENGINE": "kokoro"}):
            with mock.patch.object(tts_local.os.path, "exists", return_value=False):
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    self.assertEqual("piper", tts_local.pick_engine())
        self.assertIn("falling back to piper", stderr.getvalue())

        with mock.patch.dict(os.environ, {"SCRATCH_ENGINE": "kokoro"}):
            with mock.patch.object(tts_local.os.path, "exists", return_value=True):
                self.assertEqual("kokoro", tts_local.pick_engine())

    def test_make_piper_passes_text_to_the_configured_voice(self):
        with mock.patch.dict(
            os.environ,
            {"PIPER_BIN": "/usr/bin/piper", "PIPER_VOICE": "/voices/test.onnx"},
        ):
            with mock.patch.object(tts_local.subprocess, "run") as run:
                speak = tts_local.make_piper()
                speak("hello", "sample.wav")
        run.assert_called_once_with(
            ["/usr/bin/piper", "--model", "/voices/test.onnx", "--output_file", "sample.wav"],
            input="hello",
            text=True,
            check=True,
            stdout=tts_local.subprocess.DEVNULL,
            stderr=tts_local.subprocess.DEVNULL,
        )

    def test_duration_reads_ffprobe_output(self):
        completed = mock.Mock(stdout="2.750\n")
        with mock.patch.object(tts_local.subprocess, "run", return_value=completed) as run:
            self.assertEqual(2.75, tts_local.dur("sample.wav"))
        self.assertEqual("ffprobe", run.call_args.args[0][0])

    def test_main_synthesizes_the_joined_script_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            intake = temp / "intake.json"
            output = temp / "out"
            intake.write_text(
                json.dumps({"beats": [{"say": "First."}, {"say": "Second."}]}),
                encoding="utf-8",
            )
            calls = []

            def speak(text, wav):
                calls.append(text)
                Path(wav).write_bytes(b"wav")

            with mock.patch.object(sys, "argv", ["tts_local.py", str(intake), str(output)]):
                with mock.patch.object(tts_local, "pick_engine", return_value="kokoro"):
                    with mock.patch.object(tts_local, "make_kokoro", return_value=speak):
                        with mock.patch.object(tts_local, "dur", return_value=2.0):
                            with mock.patch.object(tts_local.subprocess, "run") as run:
                                with contextlib.redirect_stdout(io.StringIO()):
                                    with contextlib.redirect_stderr(io.StringIO()):
                                        tts_local.main()

            self.assertEqual(["First.\nSecond."], calls)
            self.assertEqual(1, run.call_count)
            words = json.loads((output / "audio/words.json").read_text())
            timing = json.loads((output / "audio/timing.json").read_text())
            self.assertEqual(["First", "Second"], [word["w"] for word in words])
            self.assertEqual(2.0, timing["duration"])


if __name__ == "__main__":
    unittest.main()
