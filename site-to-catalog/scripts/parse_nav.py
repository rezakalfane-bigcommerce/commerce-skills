import csv
import re
from collections import defaultdict
from urllib.parse import urlparse
from bs4 import BeautifulSoup

with open("nav_raw.html", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

SITE_HOST = "beautyworksonline.com"  # EDIT PER SITE
BRAND_HOST = "beautyworks.com"

# ---- classification helpers -------------------------------------------------

WEIGHT_RE = re.compile(r"\(\s*\d+\s*g", re.IGNORECASE)          # (48g), (75g-95g)
MM_RE = re.compile(r"\b\d+\s*mm\b", re.IGNORECASE)                # 32mm, 45mm
MARKETING_TAG_RE = re.compile(r"\((NEW!?|UPGRADED!?)\)", re.IGNORECASE)
BRAND_PREFIX_RE = re.compile(r"^Beauty Works\b", re.IGNORECASE)

# Known collection/category names that happen to start with "Beauty Works" or
# contain a brand mark but are NOT single-SKU product pages - allowlist so the
# brand-prefix heuristic below doesn't misfire on real categories.
CATEGORY_ALLOWLIST = {
    "beauty works x huda hairdrobe®",
    "beauty works x huda",
    "beauty works x huda shades",
}


def is_product_like(name: str) -> bool:
    n = name.strip()
    key = n.lower()
    if key in CATEGORY_ALLOWLIST:
        return False
    if MARKETING_TAG_RE.search(n):
        return True
    if WEIGHT_RE.search(n):
        return True
    if MM_RE.search(n):
        return True
    if BRAND_PREFIX_RE.search(n):
        return True
    return False


def classify_link(url: str):
    """Return (include: bool, reason: str). Product-like check is separate."""
    if "#" in url:
        return False, "in-page-anchor"
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if "whatsapp.com" in host:
        return False, "external-whatsapp"
    if host == BRAND_HOST:
        return False, "external-brand-site"
    if host and SITE_HOST not in host:
        return False, "external"
    if path.startswith("/blog"):
        return False, "blog"
    if path in (
        "/contact-us", "/salon-locator", "/colour-match", "/help-centre",
        "/colour-match-me-tester", "/hair-extensions-aftercare-advice",
    ):
        return False, "informational-page"
    return True, "category"


MAGENTO_CATEGORY_RE = re.compile(r"/catalog/category/view/s/([^/]+)/id/\d+/?$")


def slug_from_path(path: str) -> str:
    m = MAGENTO_CATEGORY_RE.search(path)
    if m:
        return m.group(1)
    slug = path.strip("/")
    if slug.endswith(".html"):
        slug = slug[:-5]
    return slug.split("/")[-1] if slug else ""


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "category"


# ---- parse the nav -----------------------------------------------------------

rows = []          # final category rows to load into BC
excluded = []       # (level, name, url, reason)
next_id = 1
slug_seen = set()   # global slug registry to keep every category's slug unique
url_occurrence = defaultdict(int)  # url -> how many times already placed as a category


def register_slug(base_slug: str, parent_slug: str, is_dupe_occurrence: bool) -> str:
    """First placement keeps the natural slug. Repeat placements (same landing
    page reused in another menu branch) get a parent-qualified slug so BC's
    unique-URL constraint is never violated, while the folder keeps the same
    display name."""
    slug = base_slug
    if is_dupe_occurrence or slug in slug_seen:
        candidate = f"{base_slug}-{parent_slug}" if parent_slug else base_slug
        slug = candidate
        i = 2
        while slug in slug_seen:
            slug = f"{candidate}-{i}"
            i += 1
    slug_seen.add(slug)
    return slug


def next_category_id():
    global next_id
    cid = next_id
    next_id += 1
    return cid


def add_category(name, url, parent_id, parent_slug, level, sort_order):
    base_slug = slug_from_path(urlparse(url).path) or slugify(name)
    occurrence = url_occurrence[url]
    url_occurrence[url] += 1
    slug = register_slug(base_slug, parent_slug, occurrence > 0)
    cid = next_category_id()
    rows.append({
        "id": cid,
        "name": name,
        "slug": slug,
        "url": url,
        "parent_id": parent_id,
        "level": level,
        "sort_order": sort_order,
        "duplicate_of_url": url if occurrence > 0 else "",
    })
    return cid, slug


top_lis = soup.select("ul > li.level-0")
print(f"Found {len(top_lis)} level-0 items")

for sort0, li in enumerate(top_lis):
    top_a = li.find("a", recursive=False) or li.find("a")
    if not top_a:
        continue
    top_url = top_a.get("href", "").strip()
    top_name = (top_a.get("title") or top_a.get_text(strip=True)).strip()

    ok, reason = classify_link(top_url)
    if not ok:
        excluded.append((0, top_name, top_url, reason))
        continue
    if is_product_like(top_name):
        excluded.append((0, top_name, top_url, "product-page"))
        continue

    top_id, top_slug = add_category(top_name, top_url, 0, "", 1, sort0)

    submenu = li.select_one("div.submenu")
    if not submenu:
        continue

    l2_sort = 0
    for l2_div in submenu.select("div.mb-5"):
        l2_a = None
        for a in l2_div.find_all("a", recursive=False):
            l2_a = a
            break
        if l2_a is None:
            continue

        l2_url = l2_a.get("href", "").strip()
        l2_name = (l2_a.get("title") or l2_a.get_text(strip=True)).strip()

        ok, reason = classify_link(l2_url)
        l2_id = None
        l2_slug = ""
        if not ok:
            excluded.append((1, l2_name, l2_url, reason))
        elif is_product_like(l2_name):
            excluded.append((1, l2_name, l2_url, "product-page"))
        else:
            l2_id, l2_slug = add_category(l2_url and l2_name, l2_url, top_id, top_slug, 2, l2_sort)
            l2_sort += 1

        pt_div = None
        for d in l2_div.find_all("div"):
            cls = d.get("class") or []
            if any("pt-[15px]" in c for c in cls):
                pt_div = d
                break

        if pt_div:
            l3_sort = 0
            for l3_a in pt_div.find_all("a", recursive=False):
                l3_url = l3_a.get("href", "").strip()
                l3_name = (l3_a.get("title") or l3_a.get_text(strip=True)).strip()

                ok, reason = classify_link(l3_url)
                if not ok:
                    excluded.append((2, l3_name, l3_url, reason))
                    continue
                if is_product_like(l3_name):
                    excluded.append((2, l3_name, l3_url, "product-page"))
                    continue
                if l2_id is None:
                    excluded.append((2, l3_name, l3_url, "parent-excluded"))
                    continue

                add_category(l3_name, l3_url, l2_id, l2_slug, 3, l3_sort)
                l3_sort += 1

print(f"Included rows: {len(rows)}")
print(f"Excluded rows: {len(excluded)}")
print(f"Excluded as product-page: {sum(1 for r in excluded if r[3] == 'product-page')}")

with open("categories.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["id", "name", "slug", "url", "parent_id", "level", "sort_order", "duplicate_of_url"],
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

with open("excluded.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["level", "name", "url", "reason"])
    for lvl, name, url, reason in excluded:
        writer.writerow([lvl, name, url, reason])

print("Wrote categories.csv and excluded.csv")
