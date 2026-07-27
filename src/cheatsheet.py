#!/usr/bin/env python3
"""cheatsheet.py — write a self-contained "here's what I did + what it cost" receipt.

Computes the cost from the REAL counts of this run (voiceover chars, images, music
seconds). Two columns: pay-as-you-go vs marginal-if-already-subscribed. All numbers are
approximate and dated — verify provider pricing before you quote it.

Usage: python3 src/cheatsheet.py --out out/x/cheatsheet.html --title "..." --theme "..." \
         --chars 280 --images 4 --imgsize 1024x1536 --imgquality medium \
         --music-seconds 28 --duration 28 --voice "my clone"
"""
import sys

# ---- unit costs -----------------------------------------------------------
# Published list prices. Update RATES_AS_OF whenever you touch these; the date
# is printed on the receipt so a stale number is obvious instead of invisible.
RATES_AS_OF = "2026-07-27"
EL_USD_PER_1K_CHARS = 0.10          # ElevenLabs TTS, pay-as-you-go
EL_MUSIC_USD_PER_MIN = 0.15         # ElevenLabs Music
IMG_USD = {"1024x1024": {"low": .011, "medium": .042, "high": .167},
           "1024x1536": {"low": .016, "medium": .063, "high": .25},
           "1536x1024": {"low": .016, "medium": .063, "high": .25}}


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


def main():
    out = arg("--out", "cheatsheet.html")
    title = arg("--title", "Demo"); theme = arg("--theme", "")
    chars = int(arg("--chars", "0")); images = int(arg("--images", "0"))
    imgsize = arg("--imgsize", "1024x1536"); imgq = arg("--imgquality", "medium")
    music_s = float(arg("--music-seconds", "0")); duration = float(arg("--duration", "0"))
    voice = arg("--voice", "AI voice")

    vo_usd = chars / 1000.0 * EL_USD_PER_1K_CHARS
    mus_usd = music_s / 60.0 * EL_MUSIC_USD_PER_MIN
    img_each = IMG_USD.get(imgsize, IMG_USD["1024x1536"]).get(imgq, .063)
    img_usd = images * img_each

    payg = vo_usd + mus_usd + img_usd      # everything billed
    marginal = img_usd                     # voice+music come from the plan pool

    rows = [
        ("Script", "one LLM prompt (or you write it)", "~free", "~free"),
        ("Voice", f"{chars} chars · ElevenLabs ({voice})", f"${vo_usd:.2f}", "~$0 (from plan)"),
        (f"Images ({images})", f"gpt-image {imgsize} {imgq}", f"${img_usd:.2f}", f"${img_usd:.2f}"),
        ("Music", f"{music_s:.0f}s · ElevenLabs Music", f"${mus_usd:.2f}", "~$0 (from plan)"),
        ("Assemble · caption", "ffmpeg · Playwright · Python", "$0", "$0"),
    ]
    tr = "".join(
        f" · rates as of {RATES_AS_OF}<tr><td>{a}</td><td class='d'>{b}</td><td class='n'>{c}</td><td class='n'>{d}</td></tr>"
        for a, b, c, d in rows)

    html = f"""<!doctype html><meta charset=utf-8><title>{title} — receipt</title>
<style>
:root{{--bg:#0a0a0f;--fg:#ececf2;--mut:#9a9aae;--ac:#22d3ee;--ok:#34d399;--line:rgba(255,255,255,.1)}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;padding:6vw}}
h1{{font-size:2.4rem;letter-spacing:-.02em;margin:0 0 .2em}}.theme{{color:var(--ac);font-weight:600}}
.sub{{color:var(--mut);margin-bottom:2em}}
table{{width:100%;max-width:760px;border-collapse:collapse;margin:1em 0}}
th,td{{text-align:left;padding:.7em .6em;border-bottom:1px solid var(--line)}}
th{{color:var(--mut);font-size:.75rem;text-transform:uppercase;letter-spacing:.1em}}
td.d{{color:var(--mut)}}td.n{{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}}
.tot td{{border-top:2px solid var(--line);font-weight:700;font-size:1.1rem}}
.big{{color:var(--ok)}}.note{{color:var(--mut);font-size:.85rem;max-width:760px;margin-top:1.5em}}
</style>
<h1>Here's what I did <span style="color:var(--mut)">→</span> <span class="big">${payg:.2f}</span></h1>
<div class="sub">"{theme}" · a {duration:.0f}s vertical short, built by <b>ghostreel</b> — no camera, no editor.</div>
<table>
<tr><th>Step</th><th>What</th><th>Pay-as-you-go</th><th>If subscribed</th></tr>
{tr}
<tr class="tot"><td>Total</td><td class="d">one short</td><td class="n big">${payg:.2f}</td><td class="n big">${marginal:.2f}</td></tr>
</table>
<div class="note">Approximate, mid-2026 pricing. The voice and music come "free" from a monthly
ElevenLabs plan once you hold one, so the real out-of-pocket is mostly the images. ffmpeg,
Playwright and Python are free and open source. Verify provider prices before you quote them.</div>
"""
    open(out, "w").write(html)
    print(f"cheatsheet -> {out}  (PAYG ${payg:.2f} / marginal ${marginal:.2f})")


if __name__ == "__main__":
    main()
