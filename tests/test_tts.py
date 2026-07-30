#!/usr/bin/env python3
import base64
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

import tts  # noqa: E402
import tts_common  # noqa: E402


def aligned_response(text):
    return {
        "audio_base64": base64.b64encode(b"mp3").decode(),
        "alignment": {
            "characters": list(text),
            "character_start_times_seconds": [index * 0.05 for index in range(len(text))],
            "character_end_times_seconds": [(index + 1) * 0.05 for index in range(len(text))],
        },
    }


class PaidTtsTests(unittest.TestCase):
    def test_missing_format_keeps_single_narrator_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            intake = temp / "intake.json"
            output = temp / "out"
            intake.write_text(
                json.dumps(
                    {
                        "voice_id": "narrator-voice",
                        "beats": [
                            {"say": "First thought."},
                            {"say": "Second thought."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(sys, "argv", ["tts.py", str(intake), str(output)]):
                with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"}):
                    with mock.patch.object(
                        tts,
                        "synth",
                        return_value=aligned_response("First thought.\nSecond thought."),
                    ) as synth:
                        with contextlib.redirect_stdout(io.StringIO()):
                            with contextlib.redirect_stderr(io.StringIO()):
                                tts.main()

            synth.assert_called_once_with(
                "First thought.\nSecond thought.", "narrator-voice", "test-key"
            )
            self.assertEqual(
                [word["w"] for word in json.loads(
                    (output / "audio/words.json").read_text()
                )],
                ["First", "thought.", "Second", "thought."],
            )

    def test_dialogue_uses_one_paid_call_per_speaker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            intake = temp / "intake.json"
            output = temp / "out"
            intake.write_text(
                json.dumps(
                    {
                        "format": "dialogue",
                        "speakers": {
                            "host": {"voice_id": "host-voice"},
                            "guest": {"voice_id": "guest-voice"},
                        },
                        "beats": [
                            {"speaker": "host", "say": "First question?"},
                            {"speaker": "guest", "say": "First answer."},
                            {"speaker": "host", "say": "Second question?"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def synth(text, voice, key):
                calls.append((text, voice, key))
                return aligned_response(text)

            with mock.patch.object(sys, "argv", ["tts.py", str(intake), str(output)]):
                with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test-key"}):
                    with mock.patch.object(tts, "synth", side_effect=synth):
                        with mock.patch.object(tts, "stitch_audio") as stitch:
                            with contextlib.redirect_stdout(io.StringIO()):
                                with contextlib.redirect_stderr(io.StringIO()):
                                    tts.main()

            self.assertEqual(
                calls,
                [
                    ("First question?\nSecond question?", "host-voice", "test-key"),
                    ("First answer.", "guest-voice", "test-key"),
                ],
            )
            self.assertEqual(
                [segment["speaker"] for segment in stitch.call_args.args[1]],
                ["host", "guest", "host"],
            )
            words = json.loads((output / "audio/words.json").read_text())
            self.assertEqual(
                [word["w"] for word in words],
                ["First", "question?", "First", "answer.", "Second", "question?"],
            )
            self.assertEqual(
                [beat["audio_start"] for beat in json.loads(
                    (output / "audio/timing.json").read_text()
                )["beats"]],
                sorted(beat["audio_start"] for beat in json.loads(
                    (output / "audio/timing.json").read_text()
                )["beats"]),
            )

    def test_dialogue_rejects_duplicate_voice_assignments(self):
        document = {
            "format": "dialogue",
            "speakers": {
                "host": {"voice_id": "same"},
                "guest": {"voice_id": "same"},
            },
            "beats": [
                {"speaker": "host", "say": "Question?"},
                {"speaker": "guest", "say": "Answer."},
            ],
        }

        with self.assertRaisesRegex(tts_common.ScriptFormatError, "distinct voice_id"):
            tts_common.build_dialogue_groups(document, "voice_id")

    def test_stitch_audio_forces_every_turn_to_mono(self):
        segments = [
            {"speaker": "host", "start": 0.0, "end": 1.0},
            {"speaker": "guest", "start": 0.0, "end": 2.0},
        ]
        with mock.patch.object(tts_common.subprocess, "run") as run:
            tts_common.stitch_audio(
                {"host": "host.mp3", "guest": "guest.mp3"},
                segments,
                "vo.mp3",
            )

        command = run.call_args.args[0]
        filter_graph = command[command.index("-filter_complex") + 1]
        self.assertEqual(filter_graph.count("channel_layouts=mono"), 2)
        self.assertIn("concat=n=2:v=0:a=1", filter_graph)


if __name__ == "__main__":
    unittest.main()
