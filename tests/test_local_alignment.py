import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_alignment import aligned_track, load_aligner, align_audio
from tts_common import ScriptFormatError, build_dialogue_groups, interleave_dialogue, stitch_audio
from tts_local import detect_silences


class AlignmentTests(unittest.TestCase):
    def test_missing_model_is_actionable(self):
        with mock.patch.dict("os.environ", {"GHOSTREEL_ALIGN_MODEL": ""}):
            with self.assertRaisesRegex(ScriptFormatError, "GHOSTREEL_ALIGN_MODEL"):
                load_aligner()

    def test_audio_is_transcribed_with_word_timestamps(self):
        model = mock.Mock()
        model.transcribe.return_value = ([mock.Mock(words=[
            mock.Mock(word="Hello.", start=0.1, end=0.8)
        ])], None)
        track = align_audio(model, "speaker.wav", "Hello.", [(0, 6)], 1, [])
        model.transcribe.assert_called_once_with(
            "speaker.wav", word_timestamps=True, vad_filter=False
        )
        self.assertEqual([(0.0, 1)], track["windows"])


    def test_rejects_missing_words_and_unsafe_times(self):
        for words in ([], [{"word": "Wrong", "start": 0, "end": 1}],
                      [{"word": "Hello", "start": 0, "end": float("nan")}],
                      [{"word": "Hello", "start": 0, "end": 3}]):
            with self.assertRaises(ScriptFormatError):
                aligned_track("Hello", [(0, 5)], 2, words, [])

    def test_rejects_no_silence_or_ambiguous_silence(self):
        words = [{"word": "One", "start": 0, "end": 1},
                 {"word": "Two", "start": 2, "end": 3}]
        for silences in ([], [{"start": 1.1, "end": 1.3}, {"start": 1.5, "end": 1.8}]):
            with self.assertRaisesRegex(ScriptFormatError, "safe quiet boundary"):
                aligned_track("One\nTwo", [(0, 3), (4, 7)], 3, words, silences)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_unequal_audio_turns_stay_intact_and_timestamps_follow_audio(self):
        document = {"speakers": {"host": {"local_voice": "a"},
                                  "guest": {"local_voice": "b"}},
                    "beats": [{"speaker": "host", "say": "Short."},
                              {"speaker": "guest", "say": "Answer."},
                              {"speaker": "host", "say": "Several more words follow."}]}
        groups = build_dialogue_groups(document, "local_voice")
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for speaker, parts in {"host": [(3, 300), (1, 0), (1, 900)],
                                   "guest": [(1, 600)]}.items():
                path = str(Path(directory) / (speaker + ".wav"))
                samples = array.array("h")
                for duration, frequency in parts:
                    samples.extend(int(12000 * math.sin(2 * math.pi * frequency * i / 24000))
                                   for i in range(duration * 24000))
                with wave.open(path, "wb") as output:
                    output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                    output.writeframes(samples.tobytes())
                paths[speaker] = path
            tracks = {}
            for speaker, times in {"host": [(0, 3), (4, 4.25), (4.25, 4.5),
                                               (4.5, 4.75), (4.75, 5)],
                                   "guest": [(0, 1)]}.items():
                group = groups[speaker]
                recognized = [dict(word=word, start=start, end=end)
                              for word, (start, end) in zip(group["text"].split(), times)]
                tracks[speaker] = aligned_track(group["text"], group["spans"],
                                                times[-1][1], recognized,
                                                detect_silences(paths[speaker]))
            words, timing, segments = interleave_dialogue(document["beats"], groups, tracks)
            self.assertAlmostEqual(3.5, segments[0]["end"], places=3)
            self.assertEqual([0, 3.5, 5], [beat["audio_start"] for beat in timing["beats"]])
            self.assertEqual(6, timing["duration"])
            self.assertEqual([0, 3.5, 5, 5.25, 5.5, 5.75], [word["start"] for word in words])
            output = str(Path(directory) / "output.mp3")
            stitch_audio(paths, segments, output)
            pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", output,
                                           "-f", "s16le", "-ac", "1", "-ar", "24000", "-"])
            samples = array.array("h", pcm)
            # Count zero crossings in each complete tone, including late in the
            # first turn where the former proportional cut would insert the guest.
            for start, frequency in [(0.5, 300), (2.5, 300), (3.6, 600), (5.1, 900)]:
                chunk = samples[int(start * 24000):int((start + .2) * 24000)]
                crossings = sum(a < 0 <= b for a, b in zip(chunk, chunk[1:]))
                self.assertAlmostEqual(frequency, crossings / .2, delta=10)


if __name__ == "__main__":
    unittest.main()
