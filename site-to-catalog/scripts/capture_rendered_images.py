#!/usr/bin/env python3
"""Capture real image sources from pages after browser rendering.

Useful for JS-heavy stores where requests/BeautifulSoup see placeholders while
the browser loads the actual CDN image. Output is JSONL with page provenance.

Usage:
  python3 capture_rendered_images.py urls.txt --output captured.jsonl
  python3 capture_rendered_images.py products.csv --column product_url \
      --host digitalassets.example.com --min-width 200 --min-height 200

Requires Playwright and an installed Chromium browser.
"""
import argparse
import asyncio
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright


def read_urls(path, column):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            return [r[column].strip() for r in csv.DictReader(f) if r.get(column, "").strip()]
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


async def capture(page, url, args):
    await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
    await page.wait_for_timeout(args.wait_ms)
    for _ in range(args.scrolls):
        await page.evaluate("window.scrollBy(0, Math.max(500, window.innerHeight * .8))")
        await page.wait_for_timeout(args.scroll_wait_ms)
    rows = await page.locator("img").evaluate_all("""
      els => els.map(e => ({src: e.currentSrc || e.src || e.dataset.src || '',
                             alt: e.alt || '', w: e.naturalWidth || 0,
                             h: e.naturalHeight || 0}))
    """)
    seen = set()
    images = []
    for row in rows:
        src = row["src"]
        host = urlparse(src).netloc.lower()
        if (not src or src in seen or row["w"] < args.min_width or
                row["h"] < args.min_height or
                (args.host and host not in args.host)):
            continue
        seen.add(src)
        images.append(row)
    return {"page_url": url, "images": images}


async def main(args):
    urls = read_urls(args.input, args.column)
    if not urls:
        raise SystemExit("no URLs found")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1200},
                                      user_agent=args.user_agent)
        with open(args.output, "w", encoding="utf-8") as out:
            for i, url in enumerate(urls, 1):
                try:
                    result = await capture(page, url, args)
                except Exception as exc:
                    result = {"page_url": url, "error": str(exc), "images": []}
                out.write(json.dumps(result, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(urls)}] {url}: {len(result['images'])} images" +
                      (f" ({result['error']})" if result.get("error") else ""))
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--column", default="product_url")
    ap.add_argument("--output", default="captured_images.jsonl")
    ap.add_argument("--host", action="append", default=[], help="allowed image host; repeatable")
    ap.add_argument("--min-width", type=int, default=200)
    ap.add_argument("--min-height", type=int, default=200)
    ap.add_argument("--wait-ms", type=int, default=5000)
    ap.add_argument("--scroll-wait-ms", type=int, default=1000)
    ap.add_argument("--scrolls", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--user-agent", default="Mozilla/5.0 (compatible; CatalogCapture/1.0)")
    asyncio.run(main(ap.parse_args()))
