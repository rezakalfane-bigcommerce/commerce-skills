---
name: screen-capture
description: "Start a local dev server and capture a full-page screenshot, or a short interaction video, of it (or any URL) using Playwright — scrolling through the page first so lazy-loaded sections render, and dismissing the Next.js dev indicator overlay before recording. Trigger: /screen-capture, or requests like \"take a screenshot of the homepage\", \"capture the app\", \"record a video of me clicking X\", \"show me what the page looks like\"."
---

# screen-capture

Capture a full-page screenshot, or a short screen-recording of a UI interaction, from a running (or newly-started) web app with Playwright, then deliver the result to the user via `SendUserFile`.

## When to use

- The user asks to see a running app, a specific page, or "what does X look like now" → **screenshot** flow.
- The user asks to see an interaction, animation, or transition (carousel sliding, hover state, modal open/close) → **video** flow.
- Verifying a UI change actually renders (see also the `run` skill for driving an app interactively).

## Usage

```
/screen-capture                          # start dev server (if not running) + screenshot homepage
/screen-capture <url>                    # screenshot a specific URL of an already-running server
/screen-capture <url> --viewport 375x812 # mobile-sized viewport
/screen-capture <url> --video "<what to click/interact with>"  # short interaction recording
```

## Process

### 1. Find how to start the dev server

Don't assume `pnpm run dev` (or any dev command) works from the package directory that "looks" like the app. In a monorepo/workspace:

- Check the **repo root** `package.json` for a `dev` script — it may wrap `turbo run dev` (or similar) and load a root-level `.env.local` via `dotenv -e .env.local --` before delegating to workspaces. Running the equivalent command inside a sub-package directly often fails with a missing-env-var error (e.g. "Missing store hash") because that sub-package doesn't have its own `.env.local`.
- If a Node version file exists (`.nvmrc`) or the user specifies one, run `nvm use <version>` first: `source ~/.nvm/nvm.sh && nvm use <version>`.
- Start the server **detached and backgrounded** so the turn doesn't block:
  ```bash
  source ~/.nvm/nvm.sh 2>/dev/null; nvm use <version> >/dev/null
  nohup pnpm run dev > /tmp/<project>-dev.log 2>&1 &
  disown
  ```
- Poll the log file (`tail -f` briefly, or repeated `cat`) for a "Local: http://localhost:<port>" or "Ready" line before proceeding — don't guess the port, read it from the log.
- If the log shows an error (missing env var, missing store hash, etc.), that's a strong signal you started the wrong `dev` script — go back and check the workspace root.

### 2. Write and run the Playwright script from inside the target project

Playwright resolution requires being inside a directory whose `node_modules` (or workspace root `node_modules`) contains `@playwright/test` or `playwright`. Two options, in order of preference:

1. If the target project already depends on `@playwright/test` or `playwright` (check `node_modules/.pnpm` or `node -e "require.resolve('@playwright/test')"` from the project dir), write a temporary `.mjs` script **inside that project directory** (e.g. `core/_tmp_screenshot.mjs`), run it with plain `node`, then delete it immediately after.
2. Otherwise, use a scratch directory with its own `npm install --no-save playwright` (slower — prefer option 1 when possible).

Script template:

```js
import { chromium } from '@playwright/test'; // or 'playwright' if that's what's installed

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 60000 });

// Scroll all the way through first - many sites lazy-mount below-the-fold
// sections (images, carousels) on an IntersectionObserver, so a screenshot
// taken immediately after load will show empty gaps for anything not yet
// scrolled into view, even with fullPage: true.
await page.evaluate(async () => {
  const distance = 400;
  const delay = 150;
  let total = 0;
  while (total < document.body.scrollHeight) {
    window.scrollBy(0, distance);
    total += distance;
    await new Promise((r) => setTimeout(r, delay));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1500);
await page.waitForLoadState('networkidle');

await page.screenshot({ path: '<scratchpad>/screenshot.png', fullPage: true });
await browser.close();
console.log('done');
```

Always write the output PNG to the session scratchpad directory, never into the project tree.

### 3. Clean up

- Delete the temporary `.mjs` script from the project directory immediately after running it — never leave scratch files in the user's repo.
- Leave the dev server running unless the user asks you to stop it (mention that it's still running and how to stop it, e.g. the PID or `pkill -f "turbo run dev"`).

### 4. Deliver the result

Send the PNG with `SendUserFile` (`status: "normal"` if replying to a request, `"proactive"` if you're surfacing it unprompted), with a short caption naming the page/URL and any relevant context (viewport, whether it's a re-capture).

## Video capture (interaction recordings)

For "record a video of X happening" requests, use a Playwright `context` with `recordVideo` instead of (or in addition to) a screenshot.

### Key facts about `recordVideo`

- Recording starts the instant the **context** is created (i.e. from `browser.newContext({ recordVideo: {...} })`), not from when you start "doing the interesting part." Anything that happens between context creation and the interaction you actually want — page load, dismissing dev overlays, initial scrolling — gets recorded too and has to be trimmed out afterward. There is no way to pause/resume or start recording mid-context.
- Output is written as `.webm` only after `context.close()` — the file doesn't exist (and can't be read/copied) while the context is still open.
- Convert to `.mp4` for delivery (much broader compatibility than `.webm`): `ffmpeg -y -i input.webm -c:v libx264 -pix_fmt yuv420p -movflags +faststart output.mp4`.

### Making the mouse visible in the recording

Headless Chromium never paints a cursor, so any click/hover demo is invisible without one. Inject a synthetic cursor element via `context.addInitScript` (so it re-attaches on every navigation, including the PDP landing at the end of a click-through) and drive real, gradual `page.mouse.move` calls rather than jumping straight to click targets:

```js
await context.addInitScript(() => {
  const cursor = document.createElement('div');
  Object.assign(cursor.style, {
    position: 'fixed', left: '0px', top: '0px', width: '18px', height: '18px',
    borderRadius: '50%', background: 'rgba(255,30,30,0.85)', border: '2px solid white',
    pointerEvents: 'none', zIndex: '2147483647', transform: 'translate(-50%, -50%)',
  });
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(cursor));
  if (document.body) document.body.appendChild(cursor);
  document.addEventListener('mousemove', (e) => {
    cursor.style.left = `${e.clientX}px`;
    cursor.style.top = `${e.clientY}px`;
  });
});

// Track position yourself (no getter exists) and interpolate with real waits
// between steps - Playwright's built-in `steps` option on mouse.move dispatches
// all intermediate events instantly, which looks like a jump cut, not a glide.
let currentPos = { x: 720, y: 450 };
async function slowMoveTo(x, y, duration = 900, steps = 16) {
  const start = { ...currentPos };
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    await page.mouse.move(start.x + (x - start.x) * t, start.y + (y - start.y) * t);
    await page.waitForTimeout(duration / steps);
  }
  currentPos = { x, y };
}
```

**Getting the cursor to a known starting position (e.g. dead-center) is two separate problems, not one:**

1. Just setting a `currentPos` tracking variable doesn't move anything — the *real* mouse (and thus the synthetic cursor, which only updates on genuine `mousemove` events) starts wherever Chromium's internal cursor state already is (often `(0,0)`, or wherever an earlier interaction like `dismissDevIndicator()` left it — that function's `.click({force: true})` on the dev-indicator badge silently moves the real mouse to the badge's position first). A literal `page.mouse.move(x, y)` call can also be a no-op if Playwright's internal cursor-position bookkeeping already thinks it's at `(x, y)` from an earlier call, so force a guaranteed dispatch by passing through an adjacent point first:

```js
async function forceMoveTo(x, y) {
  await page.mouse.move(x - 1, y - 1);
  await page.mouse.move(x, y);
  currentPos = { x, y };
}
```

2. Even once the event genuinely dispatches (verify with a `document.addEventListener('mousemove', ...)` debug probe if unsure — the DOM event fires essentially instantly), **the video encoder's frame capture is not instantaneous.** If you compute the trim timestamp immediately after `forceMoveTo`, the actual first captured video frame at/after that instant can still show the *previous* cursor position, because Chromium's screencast samples frames on its own cadence, independent of DOM mutations. Add a short settle delay (300–400ms) after any deliberate cursor reposition before marking that moment as the trim point:

```js
await forceMoveTo(720, 450);
await page.waitForTimeout(400); // let the encoder actually capture a frame at the new position
const trimSeconds = (Date.now() - recordingStart) / 1000;
```

For a click that triggers real navigation (a plain `<a>`, not a client-routed `Link`), add a deliberate hold (700–1000ms) after the move and *before* `mouse.down()` — otherwise the navigation can fire before the next captured video frame shows the cursor actually resting on the target, so the recording jumps straight from "cursor elsewhere" to "new page," looking like nothing was clicked.

### Dismissing the Next.js dev indicator before recording

Local Next.js dev servers show a floating "N — n Issue(s)" badge (bottom-left, inside a `<nextjs-portal>` custom element with an open shadow root — Playwright's normal locators pierce it automatically). It will show up in any recording unless dismissed first:

```js
const issueBadge = page.getByText(/issue/i).first();
if (await issueBadge.count() > 0) {
  await issueBadge.click({ force: true }).catch(() => {});
  await page.waitForTimeout(500);
}
const closeButton = page.getByRole('button', { name: /close/i }).first();
if (await closeButton.count() > 0) {
  await closeButton.click({ force: true }).catch(() => {});
  await page.waitForTimeout(300);
}
// Belt-and-suspenders: force-hide the host element too, in case a click didn't
// fully close it (e.g. it re-renders, or opens an error panel instead of closing).
await page.evaluate(() => {
  document.querySelectorAll('nextjs-portal').forEach((el) => {
    el.style.setProperty('display', 'none', 'important');
  });
});
```

### Trimming the recording to the part that matters

Since recording can't start "late," get the equivalent by **timestamping** the moment the important part begins, then trimming with ffmpeg after the fact:

```js
const recordingStart = Date.now();
await page.goto(url, { waitUntil: 'networkidle' });
// ... dismiss dev indicator, any other setup ...
const trimSeconds = (Date.now() - recordingStart) / 1000;
// ... continue with the interaction to actually capture (wait, scroll, click, etc.) ...
await context.close(); // .webm only exists after this
```

```bash
ffmpeg -y -i raw.webm -ss "$trimSeconds" -c:v libx264 -pix_fmt yuv420p -movflags +faststart output.mp4
```

**Add ~0.3s of buffer past the measured timestamp** as a first pass, but a fixed buffer is a guess, not a guarantee — some overlays are transient and unrelated to the dev indicator (e.g. a `<video>` element briefly throwing "Runtime NotSupportedError / Failed to load because no supported source was found" while its `src` is still resolving) and can appear *after* the buffer window. Prefer actively polling for a clean frame before trusting the timestamp:

```js
async function waitForCleanFrame(maxAttempts = 25) {
  for (let i = 0; i < maxAttempts; i++) {
    const errorCount = await page
      .locator('text=/NotSupportedError|Failed to load because no supported source/i')
      .count();
    const portalVisible = await page.locator('nextjs-portal').first().isVisible().catch(() => false);
    if (errorCount === 0 && !portalVisible) break;
    await page.evaluate(() => {
      document.querySelectorAll('nextjs-portal').forEach((el) => el.style.setProperty('display', 'none', 'important'));
    });
    await page.waitForTimeout(150);
  }
}
// call this right after dismissing the dev indicator, BEFORE recording trimSeconds
```

If the delivered clip still shows a sliver of an overlay, re-trim a further 0.2–0.3s later rather than trying to hit the timestamp exactly.

### Triggering interactions (e.g. carousels)

To click a specific slide relative to others (e.g. "the one right of center" in a carousel), locate all matching elements (`page.locator('video')`, `.locator('[class*="..."]')`, etc.), read `.count()`, and index off the middle (`Math.floor(count / 2)`) rather than guessing a fixed index — carousel implementations often render more DOM nodes than visually-distinct slides (cloned/looped slides), so the "visual center" isn't necessarily index 0.

**A numeric slide index goes stale after any click.** Libraries like Embla re-clone/re-order slides internally once the carousel moves, so an index computed once at the start (e.g. "slide 8 is centered") can silently point at a different, possibly off-screen slide by the time you use it a few steps later for a *different* interaction (clicking its chevron, reading its product list). Symptoms: the cursor visibly moves to a plausible-looking spot but nothing happens, or a click "succeeds" but on the wrong element. Fix: re-derive "whichever slide is centered" fresh, right before each interaction, from live geometry (e.g. whichever `video`'s midpoint is currently closest to the viewport's horizontal center) rather than reusing an index:

```js
function findCenteredContainer() {
  const videos = [...document.querySelectorAll('video')];
  const vw = window.innerWidth;
  let best = null, bestDist = Infinity, bestIndex = -1;
  videos.forEach((v, i) => {
    const r = v.getBoundingClientRect();
    if (r.width === 0) return;
    const dist = Math.abs((r.left + r.width / 2) - vw / 2);
    if (dist < bestDist) { bestDist = dist; best = r; bestIndex = i; }
  });
  if (!best) return null;
  let el = videos[bestIndex];
  while (el && !el.className?.includes?.('cursor-pointer')) el = el.parentElement; // walk up to the slide container
  return { container: el, videoBox: best };
}
```

**And when clicking something found *inside* that container (a chevron, a nested product link), scope the query to that same container — never search the whole page for it.** Multiple slides/cards on a page can legitimately link to the same target (two carousel slides tagging the same product, two cards linking the same URL); an unscoped `document.querySelector('a[href*="..."]')` returns whichever match happens to come first in DOM order, which is often a *different* element than the one you just found inside your target's container — the click can still "succeed" (real navigation happens) while visibly landing on the wrong on-screen element first, which is worse than an outright failure because nothing errors and it can go unnoticed without frame-by-frame review.

### Warm up every route/page you'll touch *before* recording, on a dev server

On a Next.js/Turbopack (or similar) **dev** server, each route is compiled on first request. If the recorded interaction is the *first* thing to hit a route — including indirectly, e.g. hovering a `Link` that prefetches on `mouseenter` — the compile finishes mid-recording and triggers a Fast Refresh **full page reload**. The recording doesn't fail or split cleanly; the page visibly resets to its initial scroll position and re-plays part of the interaction, which reads as a jarring "duplicate sequence" in the final clip (and can also split Playwright's video into multiple `.webm` files for one page, which then have to be stitched together — much more fragile than avoiding the reload in the first place).

Fix: do a throwaway warm-up pass on a *separate, unrecorded* page first — visit every URL/route the real recording will touch (including ones only reached via hover-triggered prefetch, not just `.goto()`), then close that page and start the real `recordVideo` context fresh:

```js
const browser = await chromium.launch();

// Warm-up (no recording) - compiles every route the real run will touch.
const warmup = await browser.newPage();
await warmup.goto(categoryUrl, { waitUntil: 'networkidle' });
await warmup.goto(pdpUrl, { waitUntil: 'networkidle' });
// also warm up anything only reached by hover-prefetch, e.g. swatch links:
for (const label of colorLabels) {
  await warmup.getByRole('radio', { name: label, exact: true }).hover();
}
await warmup.close();

// Real recording - everything's already compiled, no mid-recording reload.
const context = await browser.newContext({ recordVideo: { dir: outDir } });
```

If a recording still comes out split into more than one `.webm` file despite this, that's a signal something got compiled live during the "real" pass too — check for routes/prefetches the warm-up missed rather than trying to manually stitch the segments back together.

### Scroll with `window.scrollBy` via `page.evaluate`, not `page.mouse.wheel`

`page.mouse.wheel(dx, dy)` fires a wheel event at the browser's *current cursor position*, wherever that last was — not "the page" in general. If a prior step clicked or hovered something inside a nested scroll container (a carousel's own scroll track, a modal, an overflow panel), the cursor is still parked there, and every subsequent `mouse.wheel()` call scrolls *that inner container* instead of the window. A "scroll back to top" loop written as `while (await page.evaluate(() => window.scrollY) > 0) { await page.mouse.wheel(0, -step); ... }` can then spin forever, because `window.scrollY` never changes — this is silent (no error, no timeout) and will hang the script indefinitely if the loop has no iteration cap.

Prefer scrolling the window directly, which is unaffected by cursor position:

```js
await page.evaluate((d) => window.scrollBy(0, d), delta);
```

And always cap position-based scroll loops with a hard iteration limit regardless of the exit condition, as a safety net:

```js
let guard = 0;
while (remaining > 0 && guard < 500) {
  // ...
  guard += 1;
}
```

## Gotchas learned the hard way

- **Wrong `dev` command → cryptic env errors.** A monorepo's per-package `dev` script may silently assume env vars that only exist at the workspace root. If `generate`/`dev` fails with something like "Missing store hash" or any "missing config" error, re-run from the workspace root instead of the package directory.
- **Empty-looking bottom-of-page sections.** If a first screenshot looks truncated or has blank gaps near the bottom despite `fullPage: true`, it's very likely lazy-loaded content that hadn't mounted — re-run with the scroll-through step above rather than assuming something is broken.
- **Module resolution for the screenshot/video script itself.** Running the script from an unrelated directory (e.g. the scratchpad) throws `ERR_MODULE_NOT_FOUND` for `@playwright/test` even if it's installed somewhere in the repo — Node resolves relative to the script's own location, so the script must live inside (or under) the `node_modules` tree that has the package.
- **Don't assume a component isn't live before checking the actual rendered page.** A component only existing in source/registration code doesn't mean it's unused — Makeswift (and similar page-builder) content is assembled remotely and may already have it placed on a real page. Screenshot/scroll the actual page first before concluding something "isn't there yet."
