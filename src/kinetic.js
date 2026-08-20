/* kinetic.js — ghostreel's original timeline + particle engine (MIT). Clean-room.
 *
 * Model: a video is a list of scenes stacked in #stage. A timeline T = [[ms, fn], ...]
 * shows/hides scenes and staggers text in, synced to the voiceover's word timings
 * (the build script computes the ms values). The recorder calls window.__startTL()
 * once fonts have decoded, so frame 0 is always fully painted.
 *
 * Globals you can set before this loads:
 *   window.FXCOLORS  -> array of hex colors for the particle bursts.
 */
(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const COLORS = window.FXCOLORS || ['#ffd23f', '#37e3ff', '#4ade80', '#ffffff'];

  // --- particles ---
  const cv = document.getElementById('fx');
  const cx = cv ? cv.getContext('2d') : null;
  let parts = [];
  function burst(x, y, n, power) {
    if (!cx) return;
    for (let i = 0; i < n; i++) {
      const a = (Math.PI * 2 * i) / n + Math.random() * 0.4;
      const s = power * (0.5 + Math.random());
      parts.push({
        x, y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1,
        col: Math.random() < 0.22 ? '#fff' : COLORS[(Math.random() * COLORS.length) | 0],
        r: 3 + Math.random() * 3,
      });
    }
  }
  function tick() {
    if (!cx) return;
    cx.clearRect(0, 0, 1080, 1920);
    cx.globalCompositeOperation = 'lighter';
    for (const p of parts) {
      p.vy += 0.05; p.vx *= 0.99; p.vy *= 0.99;
      p.x += p.vx; p.y += p.vy; p.life -= 0.013;
      if (p.life > 0) {
        cx.globalAlpha = Math.max(0, p.life);
        cx.fillStyle = p.col;
        cx.beginPath(); cx.arc(p.x, p.y, p.r * p.life, 0, 7); cx.fill();
      }
    }
    cx.globalAlpha = 1; cx.globalCompositeOperation = 'source-over';
    parts = parts.filter((p) => p.life > 0);
    requestAnimationFrame(tick);
  }
  if (cx) tick();

  // --- scene + text helpers (exposed on window for the timeline) ---
  window.fxBurst = (big) => burst(180 + Math.random() * 720, 360 + Math.random() * 560, big ? 64 : 36, big ? 9 : 6);
  window.show = (sel) => { const e = $(sel); if (e) e.classList.add('on'); };
  window.hide = (sel) => { const e = $(sel); if (e) e.classList.remove('on'); };
  window.inn = (sel, d = 0) => setTimeout(() => { const e = $(sel); if (e) e.classList.add('in'); }, d);
  // stagger every [data-k] child of a scene into view
  window.reveal = (sceneSel, gap = 170, t0 = 0) =>
    $$(sceneSel + ' [data-k]').forEach((el, i) => setTimeout(() => el.classList.add('in'), t0 + i * gap));

  let amb = null;
  window.startAmbient = (ms = 650, big = false) => { stopAmbient(); amb = setInterval(() => window.fxBurst(big), ms); };
  window.stopAmbient = () => { if (amb) { clearInterval(amb); amb = null; } };

  // --- timeline runner ---
  window.runTimeline = function (T) {
    let started = false;
    window.__startTL = function () {
      if (started) return; started = true;
      T.forEach(([ms, fn]) => setTimeout(fn, ms));
    };
    // Direct previews auto-start once the page is painted. The recorder sets
    // its marker before navigation and calls the same hook after asset settling.
    Promise.all([
      new Promise((r) => (document.readyState === 'complete' ? r() : addEventListener('load', r))),
      document.fonts ? document.fonts.ready : Promise.resolve(),
    ]).then(() => {
      if (!window.__GHOSTREEL_RECORDING__) setTimeout(window.__startTL, 260);
    });
  };
})();
