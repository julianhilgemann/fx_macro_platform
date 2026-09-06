/* ============================================================================
   FX Macro — Design System · Interactions (behavior layer)
   ----------------------------------------------------------------------------
   Cursor tilt + specular highlight for glass cards. Opt in by adding the
   `data-tilt` attribute to a `.tile` (or any element using the tile styles).

   The feel is driven by the `--tilt-*` tokens in tokens.css; frame-rate
   independent exponential smoothing + a critically-damped spring for lift.
   Respects `prefers-reduced-motion`.

   API:
     FXMacro.initTilt(el)          wire a single element
     FXMacro.initAll(root?)        wire every `[data-tilt]` under a root
   ========================================================================== */
(function (global) {
  "use strict";

  function reducedMotion() {
    return global.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function read(el, prop, fallback) {
    const v = global.getComputedStyle(el).getPropertyValue(prop).trim();
    return v || fallback;
  }

  function initTilt(el) {
    if (!el || el.dataset.tiltInit === "1") return;
    el.dataset.tiltInit = "1";
    if (reducedMotion()) return;

    const perspective = read(el, "--tilt-perspective", "900px");
    const deg = parseFloat(read(el, "--tilt-deg", "5deg")) || 5;
    const lift = parseFloat(read(el, "--tilt-lift", "-6px")) || -6;

    // Motion tuning (ms / spring). Feel knobs, not visual tokens.
    const TAU_TILT = 85;   // tilt smoothing time constant
    const TAU_GLOW = 55;   // specular smoothing time constant
    const STIFFNESS = 170; // lift spring stiffness
    const DAMPING = 2 * Math.sqrt(STIFFNESS);

    const cur = { x: 0, y: 0, lift: 0, liftV: 0, mx: 0, my: 0, active: false, last: 0 };
    const target = { x: 0, y: 0, lift: 0, mx: 0, my: 0, hover: false };

    function frame(now) {
      if (!cur.last) cur.last = now;
      const dt = Math.min(now - cur.last, 64); // clamp tab-switch gaps
      cur.last = now;
      const s = dt / 1000;

      const kTilt = 1 - Math.exp(-dt / TAU_TILT);
      const kGlow = 1 - Math.exp(-dt / TAU_GLOW);

      cur.x += (target.x - cur.x) * kTilt;
      cur.y += (target.y - cur.y) * kTilt;
      cur.mx += (target.mx - cur.mx) * kGlow;
      cur.my += (target.my - cur.my) * kGlow;

      // spring: a = -k·(x − target) − c·v
      cur.liftV += (-STIFFNESS * (cur.lift - target.lift) - DAMPING * cur.liftV) * s;
      cur.lift += cur.liftV * s;

      el.style.transform =
        `perspective(${perspective}) translateY(${cur.lift.toFixed(2)}px) rotateX(${(-cur.y * deg).toFixed(3)}deg) rotateY(${(cur.x * deg).toFixed(3)}deg)`;
      el.style.setProperty("--mx", cur.mx.toFixed(1) + "px");
      el.style.setProperty("--my", cur.my.toFixed(1) + "px");

      const settled =
        !target.hover &&
        Math.abs(cur.x) < 0.001 &&
        Math.abs(cur.y) < 0.001 &&
        Math.abs(cur.lift) < 0.01 &&
        Math.abs(cur.liftV) < 0.01;

      if (settled) {
        cur.active = false;
        cur.lift = 0;
        cur.liftV = 0;
        el.style.transform = "";
      } else {
        global.requestAnimationFrame(frame);
      }
    }

    function setPos(e) {
      const r = el.getBoundingClientRect();
      target.mx = e.clientX - r.left;
      target.my = e.clientY - r.top;
    }

    el.addEventListener("pointerenter", (e) => {
      target.hover = true;
      target.lift = lift;
      setPos(e);
      if (!cur.active) { cur.active = true; global.requestAnimationFrame(frame); }
    });

    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect();
      target.x = (e.clientX - r.left) / r.width - 0.5;
      target.y = (e.clientY - r.top) / r.height - 0.5;
      setPos(e);
      if (!cur.active) { cur.active = true; global.requestAnimationFrame(frame); }
    });

    el.addEventListener("pointerleave", () => {
      target.hover = false;
      target.lift = 0;
      target.x = 0;
      target.y = 0;
    });
  }

  function initAll(root) {
    (root || global.document).querySelectorAll("[data-tilt]").forEach(initTilt);
  }

  global.FXMacro = { initTilt: initTilt, initAll: initAll };

  if (global.document.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", function () { initAll(); });
  } else {
    initAll();
  }
})(window);
