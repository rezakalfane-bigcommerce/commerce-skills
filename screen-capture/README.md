# screen-capture

A [Claude Code](https://claude.com/claude-code) skill for capturing full-page screenshots and short interaction-video recordings of a locally-running web app using [Playwright](https://playwright.dev/).

## What it does

- Starts (or reuses) a local dev server and takes a full-page screenshot, scrolling through the page first so lazy-loaded/below-the-fold sections actually render before the shot is taken.
- Records short "interaction" videos — clicking through a carousel, filling a form, navigating from a listing page to a detail page — with a synthetic on-screen cursor so viewers can follow what's being clicked.
- Bakes in a number of hard-won fixes for gotchas specific to recording against a **dev server** (Next.js/Turbopack and similar), not just a static build.

## Install

See the [repo root README](../README.md#install) for install commands (single-skill or all-skills).

## Usage

```
/screen-capture                          # start dev server (if not running) + screenshot homepage
/screen-capture <url>                    # screenshot a specific URL of an already-running server
/screen-capture <url> --viewport 375x812 # mobile-sized viewport
/screen-capture <url> --video "<what to click/interact with>"  # short interaction recording
```

## What's covered

See `SKILL.md` for the full details, but at a glance:

- **Finding the right dev command** in a monorepo/workspace (root scripts often load env vars a sub-package's own script won't have).
- **Scrolling through the whole page** before a screenshot, since many sites lazy-mount below-the-fold sections.
- **Recording interaction videos** with `recordVideo`, including converting to `.mp4` for delivery.
- **A synthetic, visible cursor overlay** (headless Chromium never paints one), driven by smooth, human-paced mouse movement instead of instant jumps.
- **Dismissing the Next.js dev indicator** overlay before/during recording.
- **Actively polling for a "clean" frame** before trimming, rather than trusting a fixed time buffer — some overlays (e.g. a video-source error) can appear later than expected.
- **Warming up every route the recording will touch** on a throwaway, unrecorded page first, to avoid a dev-server compile-triggered Fast Refresh reload splitting or corrupting the recording mid-take.
- **Scrolling via `window.scrollBy` instead of `page.mouse.wheel`**, since wheel events fire at the current cursor position and can silently scroll the wrong (nested) element forever.
- **Re-deriving "what's currently centered"** fresh before every interaction in a carousel, rather than trusting a numeric slide index — carousel libraries like Embla re-clone/reorder slides after each click.
- **Scoping nested-element lookups to their container**, never searching the whole page, since multiple elements can legitimately link to the same target.

## License

MIT
