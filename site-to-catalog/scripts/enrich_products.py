"""
Phase 2: enrich the 134 product families with real per-variant SKU/price data,
descriptions, images, and ratings, pulled from live product-detail pages.

Key discovery (see conversation): each product page embeds schema.org
JSON-LD with a Product block whose "offers" array lists EVERY colour/size
variant available on THAT page (with real sku + price + strikethrough list
price) - but LENGTH creates a genuinely separate page/URL per value. So the
fetch plan is: one page per distinct LENGTH value per family (or one page
total for families with no length dimension), not one page per member URL.

Outputs (all local CSVs - no BigCommerce writes in this script):
  enriched_family.csv       - family_id, description, image_urls (|-joined),
                               rating_avg, rating_count, canonical_sku_prefix
  enriched_variants.csv     - family_id, length, colour, size, sku, price,
                               list_price, source_url
  enrich_crawl_log.csv      - url, http_status, note
"""
import csv
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
RAW_DIR = Path("raw/products")
RAW_DIR.mkdir(parents=True, exist_ok=True)


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fetch(url, cache_key):
    """curl with a browser UA, cached to raw/products/<cache_key>.html."""
    dest = RAW_DIR / f"{cache_key}.html"
    if dest.exists() and dest.stat().st_size > 5000:
        return dest.read_text(encoding="utf-8", errors="replace"), 200
    try:
        result = subprocess.run(
            ["curl", "-s", "-A", UA, "-o", str(dest), "-w", "%{http_code}", "--max-time", "30", url],
            capture_output=True, text=True, timeout=40,
        )
        status = int(result.stdout.strip() or "0")
    except Exception:
        return None, 0
    if status != 200 or not dest.exists():
        return None, status
    return dest.read_text(encoding="utf-8", errors="replace"), status


def extract_ldjson_product(html):
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if d.get("@type") == "Product":
            return d
    return None


def extract_variant_images(html):
    """The page's GTM/analytics data layer embeds a 'product' array listing
    every sibling colour-variant SKU with its own real product image
    (distinct from the shared gallery) - anchor: '"product":[{"productInfo"'."""
    anchor = '"product":[{"productInfo"'
    idx = html.find(anchor)
    if idx == -1:
        return {}
    start = idx + len('"product":')
    # Naive bracket counting breaks when a raw "]" appears inside a JSON
    # string value (e.g. escaped HTML in a description field) - use the
    # stdlib decoder's raw_decode, which respects string quoting/escaping
    # and stops exactly where the JSON value ends.
    try:
        data, _ = json.JSONDecoder().raw_decode(html, start)
    except Exception:
        return {}
    if not data:
        return {}
    result = {}
    # data[0] is the CURRENT page's (config) product; its "linkedProduct" list
    # holds every sibling colour variant, each with its own real image.
    candidates = [data[0]] + (data[0].get("linkedProduct") or [])
    for item in candidates:
        pi = item.get("productInfo", item)
        sku = pi.get("sku")
        img = pi.get("productImage")
        if sku and img:
            result[sku] = img
    return result


def extract_description(html):
    """Short top-of-page marketing blurb + the long rich-HTML detailed
    description (features/set-includes/application/aftercare etc, class
    'pdp-description-content'). Returns (short_text, full_html)."""
    short_text, full_html = None, None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(".product-description")
        if el:
            short_text = el.get_text(" ", strip=True)
        full_el = soup.select_one(".pdp-description-content")
        if full_el:
            # drop the redundant leading "<h4>Description</h4>" label
            h4 = full_el.find("h4")
            if h4:
                h4.decompose()
            full_html = full_el.decode_contents().strip()
    except Exception:
        pass
    return short_text, full_html


CUSTOM_FIELD_MAX_LEN = 250
WEIGHT_BY_LENGTH_RE = re.compile(r'(\d{2})\s*[”"]\s*\((\d+(?:\.\d+)?)\s*g\)', re.IGNORECASE)


def extract_description_sections(full_html):
    """Split the full description into (heading, plain_text) sections at each
    <h3> (e.g. 'SET INCLUDES', 'AVAILABLE IN THREE LENGTHS', 'APPLICATION').
    Only short/structured sections become custom-field candidates later -
    the 250-char BC custom-field limit naturally filters out long prose
    (Application/Aftercare instructions), which stay in the full description."""
    if not full_html:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    soup = BeautifulSoup(full_html, "html.parser")
    sections = []
    for h3 in soup.find_all("h3"):
        heading = h3.get_text(" ", strip=True)
        parts = []
        for sib in h3.next_siblings:
            if getattr(sib, "name", None) == "h3":
                break
            text = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
            if text:
                parts.append(text)
        content = "; ".join(parts)
        if heading and content:
            sections.append((heading, content))
    return sections


INCLUDES_HEADINGS = {"SET CONTAINS", "SET INCLUDES", "PACK CONTAINS", "CONTAINS", "WEFT CONTAINS", "INCLUDES"}
INGREDIENT_TAGS = [
    "Argan Oil", "Keratin", "Biotin", "Collagen", "Vitamin E", "Coconut Oil",
    "Shea Butter", "Aloe Vera", "Tea Tree", "Hyaluronic Acid", "Panthenol",
    "Sulfate Free", "Sulphate Free", "Paraben Free", "Silicone Free", "Vegan",
    "Cruelty Free", "Alcohol Free", "UV Filter", "Sun Protection", "Jojoba Oil",
]


def normalize_heading(h):
    return h.strip().upper().rstrip(":").strip()


def extract_ingredient_tags(content):
    found = [tag for tag in INGREDIENT_TAGS if tag.lower() in content.lower()]
    return ", ".join(dict.fromkeys(found))  # de-dup, keep order


def build_custom_fields_for_family(sections):
    """Decide which extracted sections become BC custom fields. Short
    structured facts pass through directly; long prose (Application,
    Aftercare, Directions, How To Use, Product Information, Storage,
    Guarantee, Technical Points) is skipped here since it stays intact in
    the full description - duplicating it as a (truncated) custom field
    would be misleading. Ingredients and heat-setting guidance get purpose-
    built extraction instead of the raw prose."""
    fields = {}
    for heading, content in sections:
        norm = normalize_heading(heading)
        if norm in INCLUDES_HEADINGS:
            fields.setdefault("What's Included", content[:CUSTOM_FIELD_MAX_LEN])
        elif norm == "INGREDIENTS":
            tags = extract_ingredient_tags(content)
            if tags:
                fields.setdefault("Key Ingredients", tags[:CUSTOM_FIELD_MAX_LEN])
        elif norm == "SHADE":
            fields.setdefault("Shade", content[:CUSTOM_FIELD_MAX_LEN])
        elif norm in ("FEATURES", "AVAILABLE IN THREE LENGTHS", "AVAILABLE IN TWO LENGTHS") and len(content) <= CUSTOM_FIELD_MAX_LEN:
            fields.setdefault(heading.strip().rstrip(":").title(), content)
    return fields


def extract_weight_by_length(full_html_or_text):
    """Pull '18” (160g)' style pairs into {length_inches: weight_grams}."""
    if not full_html_or_text:
        return {}
    return {m.group(1): float(m.group(2)) for m in WEIGHT_BY_LENGTH_RE.finditer(full_html_or_text)}


def slug_for_url(url):
    path = urlparse(url).path.strip("/")
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "page"


families = load_csv("product_families.csv")
family_members = load_csv("product_family_members.csv")

members_by_family = defaultdict(list)
for m in family_members:
    members_by_family[m["family_id"]].append(m)

crawl_log = []
enriched_family_rows = []
enriched_variant_rows = []
enriched_custom_field_rows = []
enriched_selected_field_rows = []
enriched_weight_rows = []

print(f"Enriching {len(families)} families...")

for fam in families:
    fid = fam["family_id"]
    members = members_by_family[fid]

    # Group members by (length, barrel_mm) only - confirmed via live pages that
    # colour AND size are both bundled into one page's JSON-LD "offers" array,
    # so fetching one URL per distinct size value is redundant (it just
    # re-fetches offers we already captured). Length creates genuinely
    # separate pages; barrel_mm likely does too (different physical tools).
    groups = defaultdict(list)
    for m in members:
        key = (m["length"], m["barrel_mm"])
        groups[key].append(m)

    fam_short_description = None
    fam_full_description = None
    fam_images = []
    fam_rating_avg = None
    fam_rating_count = None
    fam_sku_prefix = None
    fam_variant_images = {}  # sku -> image_url

    for key, group_members in groups.items():
        rep = group_members[0]
        url = rep["product_url"]
        cache_key = slug_for_url(url)
        html, status = fetch(url, cache_key)
        crawl_log.append({"family_id": fid, "url": url, "http_status": status, "note": ""})
        if not html:
            crawl_log[-1]["note"] = "fetch failed"
            continue

        product = extract_ldjson_product(html)
        if not product:
            crawl_log[-1]["note"] = "no ld+json Product block found"
            continue

        if fam_short_description is None or fam_full_description is None:
            short_text, full_html = extract_description(html)
            fam_short_description = fam_short_description or short_text or product.get("description")
            fam_full_description = fam_full_description or full_html
        if not fam_images:
            imgs = product.get("image")
            fam_images = imgs if isinstance(imgs, list) else ([imgs] if imgs else [])
        fam_variant_images.update(extract_variant_images(html))
        if fam_rating_avg is None and product.get("aggregateRating"):
            fam_rating_avg = product["aggregateRating"].get("ratingValue")
            fam_rating_count = product["aggregateRating"].get("reviewCount")
        if fam_sku_prefix is None:
            fam_sku_prefix = product.get("sku")

        offers = product.get("offers")
        offers = offers if isinstance(offers, list) else ([offers] if offers else [])
        if not offers:
            crawl_log[-1]["note"] = "no offers array on this page"
            continue

        # Match each offer back to a colour by name suffix, since offers don't
        # carry the length/size dimensions explicitly (those are page-level).
        for o in offers:
            sku = o.get("sku")
            price = o.get("price")
            list_price = None
            ps = o.get("priceSpecification")
            if isinstance(ps, dict) and ps.get("priceType", "").endswith("StrikethroughPrice"):
                list_price = ps.get("price")
            availability = o.get("availability") or ""
            in_stock = "InStock" in availability if availability else ""
            enriched_variant_rows.append({
                "family_id": fid,
                "length": key[0],
                "barrel_mm": key[1],
                "offer_name": o.get("name") or "",
                "sku": sku or "",
                "price": price if price is not None else "",
                "list_price": list_price if list_price is not None else "",
                "image_url": "",  # filled in below once all this family's pages are fetched
                "in_stock": in_stock,
                "source_url": url,
            })
        time.sleep(0.25)

    # Backfill per-variant images now that fam_variant_images has been built
    # from every length-group page fetched for this family.
    if fam_variant_images:
        for row in enriched_variant_rows:
            if row["family_id"] == fid and row["sku"] in fam_variant_images:
                row["image_url"] = fam_variant_images[row["sku"]]

    weight_by_length = extract_weight_by_length(fam_full_description)
    sections = extract_description_sections(fam_full_description)
    for heading, content in sections:
        enriched_custom_field_rows.append({
            "family_id": fid,
            "field_name": heading[:250],
            "field_value": content,
            "usable_as_custom_field": len(content) <= CUSTOM_FIELD_MAX_LEN,
        })
    for name, value in build_custom_fields_for_family(sections).items():
        enriched_selected_field_rows.append({"family_id": fid, "field_name": name, "field_value": value})
    for length, grams in weight_by_length.items():
        enriched_weight_rows.append({"family_id": fid, "length": length, "weight_g": grams})

    enriched_family_rows.append({
        "family_id": fid,
        "short_description": fam_short_description or "",
        "full_description_html": fam_full_description or "",
        "images": "|".join(fam_images[:20]),
        "rating_avg": fam_rating_avg or "",
        "rating_count": fam_rating_count or "",
        "sku_prefix": fam_sku_prefix or "",
    })

    if int(fid) % 10 == 0:
        print(f"  ...family {fid}/{len(families)} done")

with open("enriched_family.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "short_description", "full_description_html", "images", "rating_avg", "rating_count", "sku_prefix"])
    w.writeheader()
    w.writerows(enriched_family_rows)

with open("enriched_variants.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "length", "barrel_mm", "offer_name", "sku", "price", "list_price", "image_url", "in_stock", "source_url"])
    w.writeheader()
    w.writerows(enriched_variant_rows)

with open("enriched_custom_fields.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "field_name", "field_value", "usable_as_custom_field"])
    w.writeheader()
    w.writerows(enriched_custom_field_rows)

with open("enriched_selected_fields.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "field_name", "field_value"])
    w.writeheader()
    w.writerows(enriched_selected_field_rows)

with open("enriched_weights.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "length", "weight_g"])
    w.writeheader()
    w.writerows(enriched_weight_rows)

with open("enrich_crawl_log.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["family_id", "url", "http_status", "note"])
    w.writeheader()
    w.writerows(crawl_log)

print(f"\nDone. {len(enriched_family_rows)} families enriched, {len(enriched_variant_rows)} variant offers captured.")
print(f"Fetches attempted: {len(crawl_log)}")
