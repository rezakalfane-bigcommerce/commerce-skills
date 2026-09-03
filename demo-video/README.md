# demo-video

A [Claude Code](https://claude.com/claude-code) skill for recording polished, multi-step product-demo videos of a locally-running web app from a small declarative **scenario file** — no bespoke Playwright script per demo.

The bundled runner (`scripts/record_scenario.mjs`) bakes in everything that makes dev-server screen recordings reliable in practice:

- A visible synthetic cursor with smooth, human-paced movement
- Next.js dev-indicator dismissal + clean-frame polling before the trim point
- Route warm-up so a Turbopack compile never triggers a mid-recording Fast Refresh reload
- Window-scoped scrolling (no `mouse.wheel` nested-container traps)
- Navigation-aware clicks (cursor holds on the target before a real `<a>` navigation fires)
- Trim timestamping + single-segment verification

## Scenario example

```json
{
  "baseUrl": "http://localhost:3000",
  "outDir": "/tmp/demo-out",
  "warmup": ["/", "/products/some-product"],
  "steps": [
    { "action": "goto", "url": "/" },
    { "action": "wait", "ms": 2000 },
    { "action": "scrollToBottom" },
    { "action": "click", "role": "button", "name": "Specifications" },
    { "action": "click", "selector": "a[href*='some-product']", "expectNavigation": true, "hold": 900 }
  ]
}
```

Run from inside a project that has `@playwright/test` in its `node_modules`:

```bash
node record_scenario.mjs scenario.json
# then trim + convert:
TRIM=$(awk '{print $1+0.3}' /tmp/demo-out/trim_seconds.txt)
ffmpeg -y -i /tmp/demo-out/raw.webm -ss "$TRIM" -c:v libx264 -pix_fmt yuv420p -movflags +faststart demo.mp4
```

See `SKILL.md` for the full step vocabulary and workflow.

## Prerequisites

- A target project with `@playwright/test` (or `playwright`) installed.
- `ffmpeg` for trim/convert.
- The [`screen-capture`](../screen-capture) skill's `references/video-capture.md` documents the underlying techniques if you need to go off-script.

## Install

Part of the [`commerce-skills`](https://github.com/rezakalfane-bigcommerce/commerce-skills) monorepo:

```bash
npx degit rezakalfane-bigcommerce/commerce-skills/demo-video ~/.claude/skills/demo-video
```

## License

MIT
