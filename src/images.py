#!/usr/bin/env python3
"""images.py — generate one image per image-beat with OpenAI's image API (gpt-image-1).

Clean-room, no framework. Sequential with retry/backoff (the image API rate-limits).
Vertical 1024x1536 by default to match a 9:16 reel. Skips beats that aren't images.

Env:   OPENAI_API_KEY
Usage: python3 src/images.py <intake.json> <run_dir> [--size 1024x1536] [--quality medium]
Writes: <run_dir>/assets/img_<i>.png   Prints: IMAGES=<count>

Style guards keep AI images photoreal/cinematic (or "comic" for a flat cartoon look) and
forbid baked-in text — overlay any words yourself; image models garble type.
"""
import base64, json, os, sys, time, urllib.request, urllib.error

API = "https://api.openai.com/v1/images/generations"
GUARDS = {
    "photoreal": ("photorealistic, cinematic, real-world photography, natural light, shallow depth "
                  "of field, vertical composition. ABSOLUTELY NO TEXT, NO WORDS, NO LETTERS, NO LOGOS."),
    "comic": ("bold flat modern cartoon illustration, bright airy background, high contrast, one clear "
              "subject. ABSOLUTELY NO TEXT, NO WORDS, NO LETTERS, NO LOGOS."),
}


def gen(prompt, style, size, quality, key, out):
    full = f"{prompt}. {GUARDS.get(style, GUARDS['photoreal'])}"
    body = json.dumps({"model": "gpt-image-1", "prompt": full, "size": size,
                       "quality": quality, "n": 1}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    open(out, "wb").write(base64.b64decode(data["data"][0]["b64_json"]))


def main():
    args = sys.argv[1:]
    intake_path, run = args[0], args[1]
    size = "1024x1536"; quality = "medium"
    if "--size" in args:
        size = args[args.index("--size") + 1]
    if "--quality" in args:
        quality = args[args.index("--quality") + 1]
    key = os.environ.get("OPENAI_API_KEY") or sys.exit("error: OPENAI_API_KEY not set (cp .envrc.example .envrc; direnv allow)")

    beats = json.load(open(intake_path))["beats"]
    os.makedirs(os.path.join(run, "assets"), exist_ok=True)
    n = 0
    for i, b in enumerate(beats):
        sh = b.get("show", {})
        if sh.get("type") != "image":
            continue
        out = os.path.join(run, "assets", f"img_{i}.png")
        for attempt in range(4):
            try:
                gen(sh["prompt"], sh.get("style", "photoreal"), size, quality, key, out)
                print(f"  img_{i}: {sh.get('badge',{}).get('label','') or sh.get('style','photoreal')}", file=sys.stderr)
                n += 1
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:160]
                print(f"  img_{i} attempt {attempt+1} HTTP {e.code}: {msg}", file=sys.stderr)
                time.sleep(20)
            except Exception as e:  # noqa
                print(f"  img_{i} attempt {attempt+1}: {e}", file=sys.stderr)
                time.sleep(15)
        else:
            sys.exit(f"error: image generation failed for beat {i}")
        time.sleep(3)  # stay under the per-minute image rate limit
    print(f"IMAGES={n}")


if __name__ == "__main__":
    main()
