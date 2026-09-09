/* ============================================================================
   Deutschland · Macro Pulse — animated background gradient
   ----------------------------------------------------------------------------
   A slow-moving, gently-morphing colour field rendered on a plain 2D canvas
   (no WebGL, nothing to compile — so it always animates). Soft radial blobs in
   the theme palette drift and breathe on a deep-ink base, then the whole layer
   is blurred in CSS for a frosted, understated look behind the glass cards.
   ========================================================================== */
(function () {
  "use strict";

  var canvas = document.getElementById("bg");
  if (!canvas) return;
  var ctx = canvas.getContext("2d");
  if (!ctx) return;

  var INK = "#05070d";

  // colour, anchor (x,y in 0..1), drift amplitude, drift speeds, radius +
  // radius pulse, phase, and peak alpha. "lighter" blending stacks the glows.
  var blobs = [
    { c: [91, 140, 255],  x: 0.28, y: 0.30, ax: 0.13, ay: 0.10, s1: 0.30, s2: 0.24, r: 0.42, ra: 0.08, rs: 0.28, ph: 0.0, a: 0.30 },
    { c: [246, 185, 75], x: 0.74, y: 0.26, ax: 0.11, ay: 0.09, s1: 0.22, s2: 0.31, r: 0.38, ra: 0.07, rs: 0.34, ph: 1.8, a: 0.26 },
    { c: [157, 140, 255], x: 0.54, y: 0.80, ax: 0.14, ay: 0.08, s1: 0.18, s2: 0.26, r: 0.46, ra: 0.09, rs: 0.24, ph: 3.2, a: 0.28 },
    { c: [77, 214, 193],  x: 0.14, y: 0.72, ax: 0.10, ay: 0.12, s1: 0.26, s2: 0.19, r: 0.34, ra: 0.06, rs: 0.32, ph: 4.6, a: 0.18 },
    { c: [255, 122, 162], x: 0.86, y: 0.62, ax: 0.09, ay: 0.11, s1: 0.20, s2: 0.28, r: 0.36, ra: 0.07, rs: 0.26, ph: 5.9, a: 0.17 },
  ];

  var W = 0, H = 0, S = 0;

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    W = Math.max(1, Math.floor(canvas.clientWidth * dpr));
    H = Math.max(1, Math.floor(canvas.clientHeight * dpr));
    S = Math.min(W, H);
    canvas.width = W;
    canvas.height = H;
  }
  window.addEventListener("resize", resize);
  resize();

  var start = performance.now();

  function frame(now) {
    var t = (now - start) / 1000;

    // deep ink base (covers the CSS fallback)
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = INK;
    ctx.fillRect(0, 0, W, H);

    // drifting, breathing colour fields
    ctx.globalCompositeOperation = "lighter";
    for (var i = 0; i < blobs.length; i++) {
      var b = blobs[i];
      var cx = (b.x + b.ax * Math.sin(t * b.s1 + b.ph)) * W;
      var cy = (b.y + b.ay * Math.cos(t * b.s2 + b.ph * 1.3)) * H;
      var r = (b.r + b.ra * Math.sin(t * b.rs + b.ph)) * S;
      var rgb = b.c.join(",");
      var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, "rgba(" + rgb + "," + b.a + ")");
      g.addColorStop(1, "rgba(" + rgb + ",0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  // gradient is live — hide the static CSS ambient fallback
  var ambient = document.querySelector(".ambient");
  if (ambient) ambient.style.display = "none";
})();
