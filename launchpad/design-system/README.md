# FX Macro — Design System

A small, dependency-free design system extracted from the launchpad's visual
style so future platform pages share one consistent look without copying HTML
or inline CSS. It is **atomic**: every component reads from a single set of
tokens, and pages only compose components.

Served statically by the `launchpad` nginx container (docroot `./launchpad`),
so any page in that docroot can reference it with a relative path.

## Layers

| File | Layer | What it owns |
|---|---|---|
| `design-system.css` | entry | `@import`s the three layers below — link this one file |
| `tokens.css` | **atoms** | every raw value: color, glass/shade tints, spacing, radius, type, elevation, motion, depth |
| `base.css` | elements | reset, `html`/`body` defaults, the page gradient, reduced-motion |
| `components.css` | **molecules** | `.ambient`, `.stage`, `.grid`, `.tile`, `.icon`, `.meta/.name/.role`, `.status` |
| `design-system.js` | behavior | cursor tilt + specular highlight (opt in with `data-tilt`) |

**Rule:** components and pages reference tokens (`var(--…)`) — they never
hardcode a color, size, or duration. Change a token, change the whole site.

## Quick start

```html
<link rel="stylesheet" href="design-system/design-system.css" />
<script src="design-system/design-system.js" defer></script>
```

```html
<div class="ambient" aria-hidden="true">
  <div class="blob b1"></div>
  <div class="blob b2"></div>
  <div class="blob b3"></div>
</div>

<main class="stage">
  <div class="grid">
    <a class="tile" data-tilt href="https://…">
      <div class="icon"><!-- svg --></div>
      <div class="meta">
        <div class="name">Dagster</div>
        <div class="role">Orchestration</div>
      </div>
      <div class="status" data-state="online"><span class="dot"></span><span class="label">live</span></div>
    </a>
  </div>
</main>
```

For dynamically-added tiles, call `FXMacro.initTilt(el)` after inserting (see
`launchpad/index.html`); static `data-tilt` elements are auto-wired on
`DOMContentLoaded`. `defer` is fine for static pages; if your own inline
script calls `FXMacro.*`, load `design-system.js` without `defer`, before that
script (as `index.html` does).

## Tokens (atoms)

Tint tokens use an opacity-percentage suffix: `--glass-72` = white @ 72%,
`--shade-45` = black @ 4.5%.

- **Palette** — `--gray-50…900`, `--green-500/700`, `--amber-500`.
- **Semantic color** — `--bg-top/mid/bot`, `--text`, `--text-muted`,
  `--accent`, `--success`, `--success-fg`, `--warning`.
- **Glass (white tints)** — `--glass-40…100`.
- **Shade (black tints)** — `--shade-4…24`, `--shade-45`.
- **Status glow** — `--success-18`, `--success-40`.
- **Elevation** — `--shadow-rest/hover/icon`, `--inset-rest/icon/hover`.
- **Spacing** — `--space-1…8` (3 → 48px).
- **Radius** — `--radius-md` (11), `--radius-lg` (18), `--radius-round`.
- **Type** — `--font-sans`, `--text-xs/sm/md`.
- **Size** — `--size-icon`, `--size-glyph`, `--size-dot`, `--grid-max`,
  `--tile-min`.
- **Motion** — `--ease-out`, `--dur-*`, `--rise-distance`, `--pulse-spread`,
  `--stagger-tile`.
- **Depth** — `--blur-glass`, `--blur-ambient`, `--perspective-stage`.
- **Tilt** — `--tilt-perspective`, `--tilt-deg`, `--tilt-lift` (read by
  `design-system.js`).
- **Z-index** — `--z-bg`, `--z-stage`, `--z-overlay`.

## Components (molecules)

- **`.ambient`** — fixed full-viewport layer holding drifting `.blob`s
  (`.b1/.b2/.b3`). Decorative; add once per page.
- **`.stage`** — centered, full-height page layout (`position: relative`,
  `min-height: 100vh`, flex centering).
- **`.grid`** — auto-fitting tile grid: every tile lands in a single row at
  full width (7 across), stepping to 3 → 2 → 1 columns on smaller screens.
- **`.tile`** — the glass card. Styled for `display: flex; flex-direction:
  column` with a bottom-aligned `.status`. Add `data-tilt` for the hover
  tilt/glow. Set `--i` for staggered entrance.
- **`.icon`** — 40px rounded badge; drop a 24×24 stroke SVG inside (renders
  at 19px). Turns `--accent` on tile hover.
- **`.meta` / `.name` / `.role`** — title + subtitle text block.
- **`.status`** — health pill with `.dot` + `.label`. State is driven by
  `data-state="online | offline | checking"`.

## Status states

```html
<div class="status" data-state="online">   → green dot, green label
<div class="status" data-state="offline">  → muted dot, muted label
<div class="status" data-state="checking"> → amber pulsing dot
```

## Adding a page

Create a new `launchpad/foo.html`, link `design-system.css`, compose the
molecules above, and (optionally) `data-tilt` your tiles. That's it — no
copied CSS, and any future token change propagates to every page.
