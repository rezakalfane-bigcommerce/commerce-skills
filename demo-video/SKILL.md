---
name: demo-video
description: "Record a polished multi-step product-demo video of a locally-running web app from a small declarative scenario file (goto/scroll/hover/click steps), with a visible synthetic cursor, dev-overlay dismissal, route warm-up, and trim timestamping all built into a stored runner. Trigger: /demo-video, or requests like \"record a demo of the checkout flow\", \"make a product tour video\", \"record a video walking through X then Y\"."
---

# demo-video

Record scripted, viewer-paced demo videos of a local web app **without writing a new Playwright script each time**. You write a ~15-line scenario JSON; the bundled runner (`scripts/record_scenario.mjs`) handles everything proven hard in practice: synthetic cursor overlay, smooth mouse movement, Next.js dev-indicator dismissal, clean-frame polling, dev-server route warm-up (prevents mid-recording Fast Refresh reloads), safe window scrolling, navigation-click holds, and trim timestamping.

Use `screen-capture` for one-off screenshots or ad-hoc recordings that need custom logic; use this skill whenever the recording is a multi-step tour expressible as scenario steps. For background on *why* the runner works the way it does, see `../screen-capture/references/video-capture.md`.

## Workflow

1. **Ensure the dev server is running** (see `screen-capture` step 1 for monorepo/env pitfalls — root `dev` script, `.env.local` location, read the port from the log).
2. **Write a scenario JSON** to the session scratchpad (never the project tree). Include in `warmup` every route the steps will touch, including pages only reached by clicking through.
3. **Run the runner from inside the target project** (Node resolves `@playwright/test` relative to the script, so copy it in temporarily):
   ```bash
   cp ~/.claude/skills/demo-video/scripts/record_scenario.mjs <project>/_tmp_record.mjs
   cd <project> && node _tmp_record.mjs <scratchpad>/scenario.json
   rm <project>/_tmp_record.mjs
   ```
   The runner exits non-zero with a warning if the recording split into multiple segments (a route was compiled mid-take — add it to `warmup` and rerun).
4. **Trim + convert** (add ~0.3s buffer past the recorded trim point):
   ```bash
   cd <outDir>
   TRIM=$(awk '{print $1+0.3}' trim_seconds.txt)
   ffmpeg -y -i raw.webm -ss "$TRIM" -c:v libx264 -pix_fmt yuv420p -movflags +faststart demo.mp4
   ```
5. **Verify** 2–3 frames before delivering (downscale to keep token cost low): `ffmpeg -i demo.mp4 -ss <t> -frames:v 1 -vf scale=640:-1 chk.png`, then Read. Check: no dev overlay at the start, cursor starts centered, key interactions visible.
6. **Deliver** the mp4 with `SendUserFile` and a caption describing the sequence.

## Scenario format

```json
{
  "baseUrl": "http://localhost:3000",
  "viewport": { "width": 1440, "height": 900 },
  "outDir": "/absolute/scratchpad/dir",
  "warmup": ["/", "/products/some-product"],
  "steps": [
    { "action": "goto", "url": "/" },
    { "action": "wait", "ms": 2000 },
    { "action": "scrollToBottom" },
    { "action": "centerElement", "selector": "video", "nth": 0 },
    { "action": "hover", "role": "radio", "name": "Amalfi Blonde", "wait": 900 },
    { "action": "click", "role": "button", "name": "Specifications" },
    { "action": "click", "selector": "a[href*='some-product']", "expectNavigation": true, "hold": 900 },
    { "action": "scrollBy", "px": 900 },
    { "action": "scrollToTop" },
    { "action": "wait", "ms": 2000 }
  ]
}
```

- **First step must be `goto`** — the runner wraps it with dev-indicator dismissal, clean-frame polling, cursor centering, and the trim timestamp.
- **Targeting** (for `move`/`hover`/`click`/`scrollToElement`/`centerElement`): `role`+`name` (preferred, uses `getByRole`), `text`, or `selector` (+ optional `nth`); `click`/`move` also accept raw `x`/`y`.
- **`click` options**: `hold` (ms cursor rests on target before mousedown — raise to 700–1000 for real `<a>` navigations), `expectNavigation: true` (waits for networkidle after), `wait` (pause after).
- **Pacing**: `duration` on move/hover/click controls cursor glide time; `step`/`delay` on scroll actions control scroll speed; `wait` pauses after any step. Defaults are viewer-friendly.

## Gotchas

- Selector-addressed clicks inside repeated components (carousel slides, product cards): scope precisely or use `nth` — carousels clone slides, and indexes go stale after any carousel click. For dynamic "click whatever is centered" logic, fall back to a custom script per `screen-capture`'s reference doc.
- `<video>` elements won't actually play in the bundled headless Chromium (no H.264 decoder) — posters show, playback doesn't. Environment artifact, not a site bug.
- If the run reports multiple `.webm` segments, a route compiled mid-recording: add the missing route (including hover-prefetch targets) to `warmup` and rerun.
