#!/usr/bin/env python3
"""Extract non-product visual assets (banners, category/menu images, brand
logos, social icons, background photos, etc.) from beautyworksonline.com -
the homepage plus every category page we already crawled - and download them
locally with metadata for reuse in the BC catalog / Catalyst storefront.

Product images themselves (under /media/catalog/product/) are excluded: this
script is only for the marketing/content imagery, not the product photos
enrich_products.py already handles.
"""
import csv
import hashlib
import os
import re
import subprocess
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

BASE = "/Users/reza.kalfane/Workspaces/beautyworks/catalog-work"
SITE = "https://beautyworksonline.com"  # EDIT PER SITE
ASSETS_DIR = os.path.join(BASE, "site_visuals")
IMG_DIR = os.path.join(ASSETS_DIR, "images")
OUT_CSV = os.path.join(ASSETS_DIR, "site_visuals.csv")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

os.makedirs(IMG_DIR, exist_ok=True)

PRODUCT_IMAGE_MARKERS = ("/media/catalog/product/",)
BG_IMAGE_RE = re.compile(r"background-image\s*:\s*url\((['\"]?)(.*?)\1\)", re.IGNORECASE)


def fetch(url):
    try:
        cp = subprocess.run(
            ["curl", "-sL", "-A", UA, "-w", "\n%{http_code}", "--max-time", "30", url],
            capture_output=True, text=True, timeout=40,
        )
        out = cp.stdout
        idx = out.rfind("\n")
        return out[idx + 1:].strip(), out[:idx]
    except Exception:
        return None, None


def load_pages():
    pages = [("home", SITE + "/")]
    seen = {SITE + "/"}
    with open(os.path.join(BASE, "categories.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row["url"]
            if url and url not in seen:
                seen.add(url)
                pages.append((row["slug"], url))
    return pages


def guess_type(src, alt, parent_classes):
    s = src.lower()
    a = (alt or "").lower()
    classes = " ".join(parent_classes).lower()
    if "logo" in s or "logo" in a:
        return "logo"
    if "menuorganizer" in s or "menu_drop_down" in s or "icon" in s:
        return "menu_icon"
    if "social" in s or any(n in s for n in ("facebook", "instagram", "pinterest", "tiktok", "twitter", "youtube", "/tw.png", "/yt.png")):
        return "social_icon"
    if "banner" in s or "banner" in classes:
        return "banner"
    if "as-seen" in s or "magazine_brands" in s or "as-seen-in" in classes:
        return "press_brand"
    if "swiper" in classes or "slide" in classes:
        return "carousel_photo"
    if any(k in s for k in ("homepage-blocks", "wysiwyg")):
        return "content_photo"
    return "other"


def parent_class_chain(tag, depth=5):
    classes = []
    p = tag.parent
    d = 0
    while p is not None and d < depth:
        cls = p.get("class") if hasattr(p, "get") else None
        if cls:
            classes.append(" ".join(cls))
        p = p.parent
        d += 1
    return classes


def extract_images_from_page(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    found = []

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy")
        if not src:
            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
        if not src:
            continue
        if any(m in src for m in PRODUCT_IMAGE_MARKERS):
            continue
        abs_src = urljoin(page_url, src)
        if "/media/" not in abs_src:
            continue
        parents = parent_class_chain(img)
        found.append({
            "url": abs_src,
            "alt": (img.get("alt") or "").strip(),
            "guessed_type": guess_type(abs_src, img.get("alt"), parents),
        })

    # Background-image URLs from inline style attributes (hero/banner blocks
    # are frequently built this way rather than with a plain <img>).
    for tag in soup.find_all(style=True):
        m = BG_IMAGE_RE.search(tag["style"])
        if not m:
            continue
        src = m.group(2)
        if any(mk in src for mk in PRODUCT_IMAGE_MARKERS):
            continue
        abs_src = urljoin(page_url, src)
        if "/media/" not in abs_src:
            continue
        found.append({
            "url": abs_src,
            "alt": "",
            "guessed_type": "background_image",
        })

    return found


def local_filename(url):
    parsed = urlsplit(url)
    name = os.path.basename(parsed.path) or "image"
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    root, ext = os.path.splitext(name)
    if not ext:
        ext = ".jpg"
    safe_root = re.sub(r"[^A-Za-z0-9_.-]", "_", root)[:80]
    return f"{safe_root}_{h}{ext}"


def main():
    pages = load_pages()
    print(f"Pages to crawl: {len(pages)}")

    seen_urls = {}  # url -> row dict (first-seen page/context wins)
    for i, (slug, url) in enumerate(pages, 1):
        status, html = fetch(url)
        if status != "200" or not html:
            print(f"  [{i}/{len(pages)}] FAILED {status} {url}")
            continue
        images = extract_images_from_page(html, url)
        new_count = 0
        for img in images:
            if img["url"] not in seen_urls:
                seen_urls[img["url"]] = {**img, "source_page": url, "source_slug": slug}
                new_count += 1
        print(f"  [{i}/{len(pages)}] {slug}: {len(images)} imgs ({new_count} new) - {url}")
        time.sleep(0.2)

    print(f"\nTotal unique visual assets found: {len(seen_urls)}")

    rows = []
    downloaded, failed = 0, 0
    for i, (url, meta) in enumerate(seen_urls.items(), 1):
        fname = local_filename(url)
        dest = os.path.join(IMG_DIR, fname)
        if not os.path.exists(dest):
            cp = subprocess.run(
                ["curl", "-sL", "-A", UA, "-o", dest, "-w", "%{http_code}", "--max-time", "30", url],
                capture_output=True, text=True, timeout=40,
            )
            status = cp.stdout.strip()
            if status != "200" or not os.path.exists(dest) or os.path.getsize(dest) == 0:
                failed += 1
                if os.path.exists(dest):
                    os.remove(dest)
                rows.append({**meta, "local_path": "", "download_status": status})
                continue
        downloaded += 1
        rows.append({
            **meta,
            "local_path": os.path.relpath(dest, BASE),
            "download_status": "200",
        })
        if i % 25 == 0:
            print(f"  downloaded {i}/{len(seen_urls)}")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["url", "alt", "guessed_type", "source_page", "source_slug", "local_path", "download_status"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"\nDownloaded {downloaded}, failed {failed}. Metadata: {OUT_CSV}")


if __name__ == "__main__":
    main()
