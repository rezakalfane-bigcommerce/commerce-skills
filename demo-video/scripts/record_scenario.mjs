#!/usr/bin/env node
// Scenario-driven demo recorder. Usage:
//   node record_scenario.mjs /absolute/path/to/scenario.json
//
// MUST be run from inside (or copied into) a project whose node_modules
// contains @playwright/test - Node resolves imports relative to this file's
// location, not the cwd.
//
// Writes raw.webm + trim_seconds.txt to scenario.outDir. Convert with:
//   ffmpeg -y -i raw.webm -ss "$(cat trim_seconds.txt | awk '{print $1+0.3}')" \
//     -c:v libx264 -pix_fmt yuv420p -movflags +faststart out.mp4
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const scenarioPath = process.argv[2];
if (!scenarioPath) {
  console.error('usage: node record_scenario.mjs <scenario.json>');
  process.exit(1);
}
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
const {
  baseUrl,
  outDir,
  viewport = { width: 1440, height: 900 },
  warmup = [],
  steps = [],
} = scenario;
if (!baseUrl || !outDir || steps.length === 0) {
  console.error('scenario needs baseUrl, outDir, and steps[]');
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });

const CURSOR_INIT_SCRIPT = () => {
  const cursor = document.createElement('div');
  cursor.id = '__pw_cursor__';
  Object.assign(cursor.style, {
    position: 'fixed', left: '0px', top: '0px', width: '18px', height: '18px',
    borderRadius: '50%', background: 'rgba(255, 30, 30, 0.85)', border: '2px solid white',
    boxShadow: '0 0 0 1px rgba(0,0,0,0.3), 0 2px 6px rgba(0,0,0,0.4)',
    pointerEvents: 'none', zIndex: '2147483647', transform: 'translate(-50%, -50%)',
  });
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(cursor));
  if (document.body) document.body.appendChild(cursor);
  document.addEventListener('mousemove', (e) => {
    cursor.style.left = `${e.clientX}px`;
    cursor.style.top = `${e.clientY}px`;
  });
};

const abs = (u) => (u.startsWith('http') ? u : baseUrl.replace(/\/$/, '') + u);

const browser = await chromium.launch();

// Warm-up pass (dev servers compile routes on first hit; a compile mid-recording
// triggers a Fast Refresh reload that wrecks the take).
{
  const w = await browser.newPage({ viewport });
  for (const u of warmup) {
    await w.goto(abs(u), { waitUntil: 'networkidle', timeout: 60000 });
    await w.waitForTimeout(300);
  }
  await w.close();
}

const context = await browser.newContext({
  viewport,
  recordVideo: { dir: outDir, size: viewport },
});
await context.addInitScript(CURSOR_INIT_SCRIPT);
const page = await context.newPage();
const recordingStart = Date.now();

let currentPos = { x: viewport.width / 2, y: viewport.height / 2 };

async function forceMoveTo(x, y) {
  await page.mouse.move(x - 1, y - 1);
  await page.mouse.move(x, y);
  currentPos = { x, y };
}

async function slowMoveTo(x, y, duration = 900, mvSteps = 16) {
  const start = { ...currentPos };
  for (let i = 1; i <= mvSteps; i++) {
    const t = i / mvSteps;
    await page.mouse.move(start.x + (x - start.x) * t, start.y + (y - start.y) * t);
    await page.waitForTimeout(duration / mvSteps);
  }
  currentPos = { x, y };
}

async function slowScrollBy(distance, step = 200, delay = 260) {
  const dir = Math.sign(distance);
  let remaining = Math.abs(distance);
  let guard = 0;
  while (remaining > 0 && guard < 500) {
    const thisStep = Math.min(step, remaining);
    await page.evaluate((d) => window.scrollBy(0, d), dir * thisStep);
    remaining -= thisStep;
    guard += 1;
    await page.waitForTimeout(delay);
  }
}

function resolveLocator(s) {
  if (s.role) return page.getByRole(s.role, { name: s.name, exact: s.exact !== false });
  if (s.text) return page.getByText(s.text, { exact: s.exact === true }).first();
  if (s.selector) {
    let loc = page.locator(s.selector);
    if (typeof s.nth === 'number') loc = loc.nth(s.nth);
    return loc;
  }
  return null;
}

async function targetCenter(s) {
  if (typeof s.x === 'number' && typeof s.y === 'number') return { x: s.x, y: s.y };
  const loc = resolveLocator(s);
  if (!loc) return null;
  const box = await loc.boundingBox();
  if (!box) return null;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function dismissDevIndicator() {
  const issueBadge = page.getByText(/issue/i).first();
  if (await issueBadge.count() > 0) {
    await issueBadge.click({ force: true }).catch(() => {});
    await page.waitForTimeout(400);
  }
  const closeButton = page.getByRole('button', { name: /close/i }).first();
  if (await closeButton.count() > 0) {
    await closeButton.click({ force: true }).catch(() => {});
    await page.waitForTimeout(200);
  }
  await page.evaluate(() => {
    document.querySelectorAll('nextjs-portal').forEach((el) => {
      el.style.setProperty('display', 'none', 'important');
    });
  });
}

async function waitForCleanFrame(maxAttempts = 25) {
  for (let i = 0; i < maxAttempts; i++) {
    const errorCount = await page
      .locator('text=/NotSupportedError|Failed to load because no supported source/i')
      .count();
    const portalVisible = await page.locator('nextjs-portal').first().isVisible().catch(() => false);
    if (errorCount === 0 && !portalVisible) break;
    await page.evaluate(() => {
      document.querySelectorAll('nextjs-portal').forEach((el) => {
        el.style.setProperty('display', 'none', 'important');
      });
    });
    await page.waitForTimeout(150);
  }
}

// First step must be a goto; the runner handles dismiss/clean/trim around it.
const first = steps[0];
if (first.action !== 'goto') {
  console.error('first step must be {"action":"goto", ...}');
  process.exit(1);
}
await page.goto(abs(first.url || '/'), { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(500);
await dismissDevIndicator();
await waitForCleanFrame();
await forceMoveTo(viewport.width / 2, viewport.height / 2);
await page.waitForTimeout(400);
const trimSeconds = (Date.now() - recordingStart) / 1000;
console.log('trim start (seconds into raw recording):', trimSeconds.toFixed(2));

for (const s of steps.slice(1)) {
  console.log('step:', JSON.stringify(s));
  switch (s.action) {
    case 'goto': {
      await page.goto(abs(s.url), { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(s.wait ?? 800);
      break;
    }
    case 'wait': {
      await page.waitForTimeout(s.ms ?? 1000);
      break;
    }
    case 'scrollBy': {
      await slowScrollBy(s.px, s.step ?? 200, s.delay ?? 260);
      break;
    }
    case 'scrollToBottom': {
      const dist = await page.evaluate(() => document.body.scrollHeight - window.scrollY - window.innerHeight);
      await slowScrollBy(Math.max(0, dist), s.step ?? 220, s.delay ?? 220);
      await page.waitForLoadState('networkidle').catch(() => {});
      await page.waitForTimeout(s.wait ?? 800);
      break;
    }
    case 'scrollToTop': {
      const pos = await page.evaluate(() => window.scrollY);
      await slowScrollBy(-pos, s.step ?? 220, s.delay ?? 220);
      break;
    }
    case 'scrollToElement': {
      const loc = resolveLocator(s);
      await loc.scrollIntoViewIfNeeded({ timeout: 10000 });
      await page.waitForTimeout(s.wait ?? 500);
      break;
    }
    case 'centerElement': {
      // Scroll so the element's vertical midpoint sits at the viewport middle.
      const loc = resolveLocator(s);
      await loc.scrollIntoViewIfNeeded({ timeout: 10000 });
      await page.waitForTimeout(200);
      const box = await loc.boundingBox();
      if (box) {
        const delta = box.y + box.height / 2 - viewport.height / 2;
        await slowScrollBy(delta, s.step ?? 200, s.delay ?? 200);
      }
      await page.waitForTimeout(s.wait ?? 600);
      break;
    }
    case 'move': {
      const c = await targetCenter(s);
      if (c) await slowMoveTo(c.x, c.y, s.duration ?? 900);
      await page.waitForTimeout(s.wait ?? 300);
      break;
    }
    case 'hover': {
      const c = await targetCenter(s);
      if (c) await slowMoveTo(c.x, c.y, s.duration ?? 700);
      await page.waitForTimeout(s.wait ?? 800);
      break;
    }
    case 'click': {
      const c = await targetCenter(s);
      if (!c) {
        console.log('WARNING: click target not found, skipping');
        break;
      }
      await slowMoveTo(c.x, c.y, s.duration ?? 900);
      // Longer default hold: if the click triggers a real navigation, the
      // encoder needs a frame showing the cursor resting on the target first.
      await page.waitForTimeout(s.hold ?? 400);
      await page.mouse.down();
      await page.waitForTimeout(90);
      await page.mouse.up();
      if (s.expectNavigation) {
        await page.waitForLoadState('networkidle').catch(() => {});
        await page.waitForTimeout(s.wait ?? 1000);
      } else {
        await page.waitForTimeout(s.wait ?? 800);
      }
      break;
    }
    default:
      console.log('WARNING: unknown action', s.action);
  }
}

await page.waitForTimeout(1000);
await context.close();
await browser.close();

const files = fs.readdirSync(outDir).filter((f) => f.endsWith('.webm'));
console.log('recorded files:', files);
if (files.length === 1) {
  fs.renameSync(`${outDir}/${files[0]}`, `${outDir}/raw.webm`);
  fs.writeFileSync(`${outDir}/trim_seconds.txt`, trimSeconds.toFixed(2));
  console.log('saved raw.webm + trim_seconds.txt (single segment)');
} else {
  console.log('WARNING: unexpected segment count (mid-recording reload? missing warm-up route?):', files);
  process.exit(2);
}
