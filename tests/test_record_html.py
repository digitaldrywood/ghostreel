#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD_HTML = ROOT / "src" / "record_html.mjs"
KINETIC_HTML = ROOT / "src" / "kinetic.html"
BUILD_KINETIC = ROOT / "src" / "build_kinetic.py"
WIDTH = 320
HEIGHT = 180


def recorder_available():
    return all(
        (
            shutil.which("ffmpeg"),
            shutil.which("ffprobe"),
            shutil.which("node"),
            (ROOT / "node_modules" / "playwright" / "package.json").is_file(),
        )
    )


@unittest.skipUnless(
    recorder_available(),
    "recording tests require ffmpeg, ffprobe, Node, and npm-installed Playwright",
)
class RecordHtmlTests(unittest.TestCase):
    def standalone_states(self):
        script = r"""
import { chromium } from "playwright";
const source = process.argv[1];
const browser = await chromium.launch({ headless: true });
const recording = await browser.newContext({ viewport: { width: 320, height: 180 } });
const recordingPage = await recording.newPage();
await recordingPage.addInitScript(() => { window.__GHOSTREEL_RECORDING__ = true; });
await recordingPage.goto(source, { waitUntil: "load" });
await recordingPage.waitForTimeout(700);
const before = await recordingPage.locator(".line.in").count();
const hook = await recordingPage.evaluate(() => typeof window.__startTL);
if (hook === "function") await recordingPage.evaluate(() => window.__startTL());
await recordingPage.waitForTimeout(220);
const after = await recordingPage.locator(".line.in").count();
await recording.close();

const preview = await browser.newContext({ viewport: { width: 320, height: 180 } });
const previewPage = await preview.newPage();
await previewPage.goto(source, { waitUntil: "load" });
await previewPage.waitForTimeout(700);
const previewStarted = await previewPage.locator(".line.in").count();
await preview.close();
await browser.close();
console.log(JSON.stringify({ before, hook, after, previewStarted }));
"""
        source = KINETIC_HTML.resolve().as_uri() + "#FIRST|SECOND"
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script, source],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def record(self, source, output, seconds=1.0):
        result = subprocess.run(
            [
                "node",
                str(RECORD_HTML),
                str(source),
                str(output),
                str(WIDTH),
                str(HEIGHT),
                str(seconds),
            ],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return output

    def frame_pixels(self, video, at=None):
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if at is not None:
            command.extend(["-ss", str(at)])
        command.extend(
            ["-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "ppm", "-"]
        )
        result = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr.decode())
        header_end = result.stdout.index(b"\n255\n") + len(b"\n255\n")
        pixels = result.stdout[header_end:]
        self.assertEqual(WIDTH * HEIGHT * 3, len(pixels))
        return pixels

    def assert_duration(self, video, expected):
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        self.assertAlmostEqual(expected, float(result.stdout), delta=0.1)

    def test_documented_kinetic_card_keeps_the_start_of_its_reveal(self):
        with tempfile.TemporaryDirectory(prefix="ghostreel-record-test-") as temp:
            output = Path(temp) / "standalone.mp4"
            source = f"{KINETIC_HTML}#FIRST|SECOND"

            states = self.standalone_states()
            self.assertEqual(0, states["before"])
            self.assertEqual("function", states["hook"])
            self.assertGreaterEqual(states["after"], 1)
            self.assertGreaterEqual(states["previewStarted"], 1)
            self.record(source, output)

            pixels = self.frame_pixels(output, at=0.25)
            bright_pixels = sum(
                1
                for index in range(0, len(pixels), 3)
                if max(pixels[index:index + 3]) >= 80
            )
            self.assertGreater(bright_pixels, 80)
            self.assert_duration(output, 1.0)

    def test_generated_page_waits_for_delayed_image_before_timeline_start(self):
        with tempfile.TemporaryDirectory(prefix="ghostreel-record-test-") as temp:
            run = Path(temp)
            (run / "audio").mkdir()
            (run / "assets").mkdir()
            intake = {
                "title": "Recorder Contract",
                "style": {"bg": "rgb(0,0,24)", "fx": "party"},
                "beats": [
                    {
                        "say": "First scene.",
                        "show": {
                            "type": "text",
                            "lines": [{"t": "FIRST", "cls": "big white"}],
                        },
                    },
                    {"say": "Second scene.", "show": {"type": "image"}},
                ],
            }
            timing = {
                "duration": 0.9,
                "beats": [
                    {"audio_start": 0.0, "audio_end": 0.4},
                    {"audio_start": 0.4, "audio_end": 0.9},
                ],
            }
            intake_path = run / "intake.json"
            intake_path.write_text(json.dumps(intake))
            (run / "audio" / "timing.json").write_text(json.dumps(timing))
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=16x16",
                    "-frames:v",
                    "1",
                    str(run / "assets" / "img_1.png"),
                ],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["python3", str(BUILD_KINETIC), str(intake_path), str(run)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            page = run / "ad.html"
            html = page.read_text()
            self.assertEqual(1, html.count("startAmbient(680,false);"))
            self.assertLess(html.index("const T=["), html.index("startAmbient(680,false);"))
            delayed_asset = """
<style>
html,body,#stage { width:320px !important; height:180px !important; }
.scene { gap:4px !important; padding:0 20px !important; }
.line.big { font-size:44px !important; }
.scrim { background:none !important; }
</style>
<script>
window.Image = class DelayedImage {
  set src(value) { setTimeout(() => this.onload && this.onload(), 1100); }
};
</script>
"""
            page.write_text(html.replace("</head>", delayed_asset + "</head>"))
            output = run / "generated.mp4"

            self.record(page, output)

            pixels = self.frame_pixels(output)
            sample = []
            for y in range(60, 120):
                for x in range(5, 45):
                    offset = (y * WIDTH + x) * 3
                    sample.append(tuple(pixels[offset:offset + 3]))
            mean_red = sum(pixel[0] for pixel in sample) / len(sample)
            self.assertLess(mean_red, 60)
            self.assert_duration(output, 1.0)


if __name__ == "__main__":
    unittest.main()
