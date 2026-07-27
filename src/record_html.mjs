// record_html.mjs — record a self-playing HTML animation to mp4 at 2x sharpness.
//
//   node src/record_html.mjs src/kinetic.html out/card.mp4 1920 1080 4
//
// Why this exists: anything with text or labels should be real HTML, never an AI image
// (image models garble text). Build the animation in HTML/CSS/JS, record it crisp.
//
// Requires: npm i playwright  &&  npx playwright install chromium  (and ffmpeg on PATH)
import { chromium } from "playwright";
import { execSync } from "node:child_process";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [file, out, W, H, secs] = [
  resolve(process.argv[2]),
  resolve(process.argv[3]),
  +process.argv[4] || 1920,
  +process.argv[5] || 1080,
  +process.argv[6] || 4,
];

const dir = mkdtempSync(join(tmpdir(), "ghostreel-"));
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 2, // render at 2x so text is sharp, then downsample
  recordVideo: { dir, size: { width: W, height: H } },
});
const page = await ctx.newPage();
const t0 = Date.now();
await page.goto("file://" + file, { waitUntil: "load" });
// Everything the first frames depend on has to be decoded BEFORE we measure the
// lead-in, or the trim lands in the wrong place and the video opens on blank
// frames. Fonts alone are not enough — CSS background images decode lazily.
await page.evaluate(async () => {
  await document.fonts.ready;
  const urls = [...document.querySelectorAll('[style*="background-image"]')]
    .map((el) => (getComputedStyle(el).backgroundImage.match(/url\("?(.+?)"?\)/) || [])[1])
    .filter(Boolean);
  await Promise.all(
    urls.map((u) => new Promise((res) => { const i = new Image(); i.onload = i.onerror = res; i.src = u; })),
  );
  // two rAFs = the browser has actually painted a settled frame
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
});
await page.waitForTimeout(220);
const lead = (Date.now() - t0) / 1000; // trim the loading lead-in off the front
await page.evaluate(() => window.__startTL && window.__startTL()); // start the animation
await page.waitForTimeout(secs * 1000 + 300);
await page.close();
await ctx.close();
await browser.close();

const webm = join(dir, readdirSync(dir).find((f) => f.endsWith(".webm")));
execSync(
  `ffmpeg -y -loglevel error -ss ${lead.toFixed(3)} -i "${webm}" -t ${secs} ` +
    `-r 30 -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -an "${out}"`,
);
console.log("wrote", out);
