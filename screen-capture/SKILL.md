---
name: screen-capture
description: "Start a local dev server and capture a full-page screenshot, or a short interaction video, of it (or any URL) using Playwright — scrolling through the page first so lazy-loaded sections render, and dismissing the Next.js dev indicator overlay before recording. Trigger: /screen-capture, or requests like \"take a screenshot of the homepage\", \"capture the app\", \"record a video of me clicking X\", \"show me what the page looks like\"."
---

# screen-capture

Capture a full-page screenshot, or a short screen-recording of a UI interaction, from a running (or newly-started) web app with Playwright, then deliver the result to the user via `SendUserFile`.

**Before any video/interaction recording, read `references/video-capture.md` in this skill's directory** — it covers `recordVideo` mechanics, the synthetic cursor overlay, dev-indicator dismissal, clean-frame trimming, carousel/selector pitfalls, dev-server route warm-up, and safe scrolling. The rest of this file covers the screenshot flow and shared setup.

## When to use

- The user asks to see a running app, a specific page, or "what does X look like now" → **screenshot** flow (this file).
- The user asks to see an interaction, animation, or transition (carousel sliding, hover state, modal open/close) → **video** flow (`references/video-capture.md`).
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
- Poll the log file for a "Local: http://localhost:<port>" or "Ready" line before proceeding — don't guess the port, read it from the log.
- If the log shows an error (missing env var, missing store hash, etc.), that's a strong signal you started the wrong `dev` script — go back and check the workspace root.

### 2. Write and run the Playwright script from inside the target project

Playwright resolution requires being inside a directory whose `node_modules` (or workspace root `node_modules`) contains `@playwright/test` or `playwright`:

1. If the target project already depends on `@playwright/test` or `playwright` (check `node -e "require.resolve('@playwright/test')"` from the project dir), write a temporary `.mjs` script **inside that project directory** (e.g. `core/_tmp_screenshot.mjs`), run it with plain `node`, then delete it immediately after.
2. Otherwise, use a scratch directory with its own `npm install --no-save playwright` (slower — prefer option 1 when possible).

Screenshot script template:

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

// Hide the Next.js dev indicator so it doesn't appear in the shot.
await page.evaluate(() => {
  document.querySelectorAll('nextjs-portal').forEach((el) => {
    el.style.setProperty('display', 'none', 'important');
  });
});

await page.screenshot({ path: '<scratchpad>/screenshot.png', fullPage: true });
await browser.close();
console.log('done');
```

Always write the output PNG to the session scratchpad directory, never into the project tree.

### 3. Clean up

- Delete the temporary `.mjs` script from the project directory immediately after running it — never leave scratch files in the user's repo.
- Leave the dev server running unless the user asks you to stop it (mention that it's still running and how to stop it, e.g. the PID or `pkill -f "turbo run dev"`).

### 4. Deliver the result

Send the PNG/mp4 with `SendUserFile` (`status: "normal"` if replying to a request, `"proactive"` if you're surfacing it unprompted), with a short caption naming the page/URL and any relevant context (viewport, whether it's a re-capture).

## Gotchas learned the hard way

- **Wrong `dev` command → cryptic env errors.** A monorepo's per-package `dev` script may silently assume env vars that only exist at the workspace root. Re-run from the workspace root instead of the package directory.
- **Empty-looking bottom-of-page sections.** If a first screenshot looks truncated or has blank gaps near the bottom despite `fullPage: true`, it's very likely lazy-loaded content that hadn't mounted — re-run with the scroll-through step above rather than assuming something is broken.
- **Module resolution for the script itself.** Running the script from an unrelated directory (e.g. the scratchpad) throws `ERR_MODULE_NOT_FOUND` for `@playwright/test` even if it's installed somewhere in the repo — the script must live inside (or under) the `node_modules` tree that has the package.
- **Don't assume a component isn't live before checking the actual rendered page.** Page-builder (e.g. Makeswift) content is assembled remotely and may already include a component that has no code-side usage. Screenshot/scroll the actual page first before concluding something "isn't there yet."
- **Token-efficient frame verification.** When spot-checking video frames or screenshots yourself, downscale first (`ffmpeg ... -vf scale=640:-1`) — image reads cost tokens proportional to size, and a small frame is enough to verify layout/cursor position.
