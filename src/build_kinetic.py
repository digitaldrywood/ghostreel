#!/usr/bin/env python3
"""build_kinetic.py — turn an intake + the voiceover's timing into a kinetic HTML page.

Reads:  <intake.json>  and  <run>/audio/timing.json  (per-beat audio_start/audio_end)
        image beats expect  <run>/assets/img_<i>.png  (if missing, a colored card is used
        so a FREE rough cut still renders)
Writes: <run>/ad.html        (references src/kinetic.css + src/kinetic.js — clean-room)
Prints: DURATION=<seconds>    (for the orchestrator)

The timeline is built programmatically from the word-synced beat windows, so every
visual is cut to the exact moment its line is spoken. No proprietary engine involved.

Usage: python3 src/build_kinetic.py <intake.json> <run_dir>
"""
import json, os, sys, urllib.parse

SRC = os.path.dirname(os.path.abspath(__file__))


def furl(path):
    return "file://" + urllib.parse.quote(os.path.abspath(path))


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    intake = json.load(open(sys.argv[1]))
    run = sys.argv[2]
    timing = json.load(open(os.path.join(run, "audio", "timing.json")))
    beats = intake["beats"]
    tb = timing["beats"]

    style = intake.get("style", {})
    bg = style.get("bg", "radial-gradient(120% 80% at 50% 16%,#16224e 0%,#0a1230 45%,#05070f 100%)")
    fxcolors = style.get("fxcolors", ["#ffd23f", "#37e3ff", "#4ade80", "#ffffff"])
    # Particle FX. "subtle" (default) bursts only on scene changes; "none" turns
    # particles off entirely; "party" adds the constant ambient burst loop, which
    # suits a fireworks ad and almost nothing else.
    fx = str(style.get("fx", "subtle")).lower()
    if fx not in ("none", "subtle", "party"):
        fx = "subtle"

    scenes, T = [], []
    end_ms = 0.0
    for i, b in enumerate(beats):
        sid = f"s{i}"
        a0 = tb[i]["audio_start"] if i < len(tb) else 0.0
        a1 = tb[i]["audio_end"] if i < len(tb) else a0 + 2.0
        start = 0 if i == 0 else int(round(a0 * 1000))
        end_ms = a1 * 1000
        show = b.get("show", {})
        typ = show.get("type", "text")
        img_path = os.path.join(run, "assets", f"img_{i}.png")
        have_img = (typ == "image" and os.path.exists(img_path))

        badge = show.get("badge")
        badge_html = ""
        if badge:
            label = esc(badge.get("label", ""))
            price = esc(badge.get("price", ""))
            inner = (f'<span class="label">{label}</span>' if label else "")
            inner += (f'<div class="price">{price}</div>' if price else "")
            badge_html = f'<div class="badge" id="bg{i}"><div class="pill">{inner}</div></div>'

        if typ == "image":
            if have_img:
                bgimg = f"background-image:url('{furl(img_path)}')"
                klass = "scene image"
            else:
                # FREE rough-cut fallback: a colored card instead of a paid image
                hue = (i * 67) % 360
                bgimg = f"background:linear-gradient(160deg,hsl({hue} 55% 22%),hsl({(hue+40)%360} 60% 10%))"
                klass = "scene"
            tag = show.get("tag")
            tag_html = f'<div class="tag"><span class="line mid cream glow" data-k>{esc(tag)}</span></div>' if tag else ""
            scenes.append(f'<div class="{klass}" id="{sid}" style="{bgimg}"><div class="scrim"></div>{tag_html}{badge_html}</div>')
            acts = []
            if i:
                acts.append(f"hide('#s{i-1}')")
            acts.append(f"show('#{sid}')")
            if tag:
                acts.append(f"reveal('#{sid}',160)")
            if badge:
                acts.append(f"inn('#bg{i}',240)" + ("" if fx == "none" else ";fxBurst(true)"))
            T.append((start, ";".join(acts)))
        else:
            lines = show.get("lines") or [{"t": b["say"].upper(), "cls": "big gold glow"}]
            line_html = "".join(
                f'<div class="line {ln.get("cls","big cream glow")}" data-k'
                + (f' style="font-size:{ln["size"]}px"' if ln.get("size") else "")
                + f'>{esc(ln["t"])}</div>'
                for ln in lines
            )
            # Beat 0 ships already-visible: frame 0 is the thumbnail, and a scene
            # that fades in from nothing gives you a blank one.
            first = i == 0
            cls = "scene on" if first else "scene"
            if first:
                line_html = line_html.replace(" data-k", " data-k class-in")
                line_html = line_html.replace('class="line ', 'class="in line ').replace(" class-in", "")
            scenes.append(f'<div class="{cls}" id="{sid}">{line_html}</div>')
            acts = []
            if i:
                acts.append(f"hide('#s{i-1}')")
            acts.append(f"show('#{sid}')" if first else f"show('#{sid}');reveal('#{sid}',180)")
            if fx != "none" and (i == 0 or show.get("burst")):
                acts.append("fxBurst(false)")
            T.append((start, ";".join(acts)))

    # Ambient particles are part of the timeline too. Starting their interval
    # while the recorder is still settling assets would discard early bursts.
    if fx == "party" and T:
        start, acts = T[0]
        T[0] = (start, f"startAmbient(680,false);{acts}")

    total = max(end_ms / 1000.0, timing.get("duration", 0.0)) + 0.4
    tl = ",\n ".join(f"[{ms},()=>{{{acts}}}]" for ms, acts in T)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{furl(os.path.join(SRC,'kinetic.css'))}">
<style>#stage{{background:{bg}}}</style></head>
<body><div id="stage">
  <canvas id="fx" width="1080" height="1920"></canvas>
{chr(10).join('  '+s for s in scenes)}
</div>
<script>window.FXCOLORS={json.dumps(fxcolors)};</script>
<script src="{furl(os.path.join(SRC,'kinetic.js'))}"></script>
<script>
const T=[
 {tl}
];
runTimeline(T);
</script></body></html>"""
    out = os.path.join(run, "ad.html")
    open(out, "w").write(html)
    print(f"ad.html -> {out}")
    print(f"DURATION={total:.2f}")


if __name__ == "__main__":
    main()
