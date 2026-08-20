---
name: test-recorder-trim-races
description: Build deterministic regressions for HTML recorder races between asset settling, timeline start, and front trimming.
when_to_use: Use when changing record_html.mjs, kinetic timeline startup, asset settling, or video front-trim behavior.
---

# Test recorder trim races

Exercise the real `record_html.mjs` command instead of testing timers in isolation. Keep
all generated pages, browser state, and videos under the Detent-provided temporary path.

For an asset race, generate a two-scene page through `build_kinetic.py`. Make scene zero
visually dark and scene one a bright solid image scheduled shortly after timeline zero.
Inject a page-local `Image` replacement whose `src` setter calls `onload` after a fixed
delay. This delays the recorder's explicit background-image settling without relying on
disk speed, while the real CSS background still renders. Before the fix, an eager
timeline advances to the bright second scene during that delay; after the fix, the first
encoded frame remains the dark first scene.

Decode the first MP4 frame to PPM with ffmpeg and compare pixels from a region outside
the scene-zero text. Also probe the final duration with ffprobe. For standalone templates,
open the real page once with the recording marker set and once without it: recording mode
must remain idle until `window.__startTL()` is called, while direct preview mode must still
auto-start. Run the documented recorder command too so hook-name drift cannot hide behind
the browser-only check.

Use distinctive scene colors and generous timing gaps so assertions survive frame-rate
quantization and normal process jitter. Keep Playwright dependencies optional at test
discovery time, but run the test fully whenever the repository's Node dependency and
browser are installed.
