# Known issues

Track these as GitHub issues once the repo is published.

## 1. `cheatsheet.py` rate constants have drifted (cost receipt overstates)

The receipt prices both voice and music at `$22 / 100,000 credits`
(`src/cheatsheet.py:14-20`, `src/cheatsheet.py:36-42`). Current published rates are
per-character for TTS and per-minute for music, and image pricing has its own tier.

Observed on the 2026-07-18 run (494 chars voice, 3× 1024×1536 medium images, 33s music):

| | receipt said | recomputed at published rates |
|---|---|---|
| voice | — | ≈ $0.05 |
| images | — | ≈ $0.19 |
| music | — | ≈ $0.08 |
| **total PAYG** | **$0.41** | **≈ $0.32** |

The **counts** the receipt records are correct — only the multipliers are stale.

**Fix:** move the rates into a small dated table (e.g. `RATES = {"as_of": "...", ...}`),
price voice per character and music per second, print the `as_of` date on the receipt,
and add a test that pins the arithmetic for a known run.

## 2. `--rough` crossfade shows a brief prior-scene overlap

At a scene transition (~0.3s window) the outgoing scene's text/badge can still be visible
under the incoming one. Cosmetic; fine for flow review, but it should cut clean.

## 3. `ghostreel.sh` wipes the run directory before it validates keys

`RUN="out/$SLUG"; rm -rf "$RUN"` happens near the top, but the API-key check happens later,
inside the voice step. A paid run started without `ELEVENLABS_API_KEY` therefore destroys a
previously good rough cut before failing.

**Fix:** validate every required key (and `node_modules`) up front, before touching `out/`.
