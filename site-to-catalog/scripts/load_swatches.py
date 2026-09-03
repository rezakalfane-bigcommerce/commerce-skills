"""Upgrade every product's 'Hair Palette' option from BC type 'dropdown' to
'swatch', using the real per-colour images we already extracted (from the
GTM/analytics 'linkedProduct' data on each product page). Catalyst's
data-transformers/product-options-transformer.ts already renders BC's
'Swatch' displayStyle as the swatch-radio-group UI + connects it to the
dropdown value automatically - no frontend code change needed."""
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

# --- same parsing rules as load_enrichment.py (kept in sync manually) ------
LENGTH_RE = re.compile(r'^\s*(\d{2})\s*"\s*[-–]?\s*')
COLOUR_SEP_RE = re.compile(r'\s*[-–]\s+')
WORTH_TAG_RE = re.compile(r'\s*\(Worth\s*£[\d.]+\)\s*$', re.IGNORECASE)
ATTRIBUTE_TAG_RE = re.compile(r'\s*\(\s*(Sulfate Free)\s*\)\s*', re.IGNORECASE)
SIZE_RE = re.compile(r'\s+(\d+(?:\.\d+)?\s?(?:ml|Ltr|[Ll]itre|L)s?)\s*$')
QUANTITY_RE = re.compile(r'\s*[-–]?\s*(\d+\s*(?:pieces?|pack))\s*$', re.IGNORECASE)
BARREL_MM_RE = re.compile(r'\s*[-–]?\s*(\d+)\s*mm\s*$', re.IGNORECASE)
NON_COLOUR_WORDS = {
    "weft", "extensions", "extension", "hair", "dryer", "dryers", "tape", "clip",
    "clips", "ring", "rings", "tip", "tips", "set", "sets", "kit", "kits", "brush",
    "brushes", "straightener", "straighteners", "tong", "tongs", "waver", "wavers",
    "styler", "stylers", "tool", "tools", "spray", "serum", "shampoo", "conditioner",
    "mask", "masks", "oil", "oils", "palette", "swatch", "swatches", "tester",
    "testers", "bundle", "bundles", "pack", "packs", "system", "device", "machine",
    "gown", "gowns", "pliers", "disk", "disks", "disc", "discs", "accessories",
    "accessory", "tabs", "tab", "collection", "duo", "trio", "volumiser", "fringe",
    "fringes", "bangs", "topper", "toppers", "ponytail", "ponytails", "wig", "wigs",
    "digital", "lightweight", "travel", "mini", "minis", "professional", "salon",
    "silicone", "lined", "pieces", "piece", "jumbo", "bond",
}


def looks_like_colour(candidate):
    return candidate.split()[-1].lower().strip("®™") not in NON_COLOUR_WORDS


def parse_colour(raw_name):
    if not raw_name:
        return None
    name = WORTH_TAG_RE.sub("", raw_name).strip()
    if ATTRIBUTE_TAG_RE.search(name):
        name = re.sub(r"\s+", " ", ATTRIBUTE_TAG_RE.sub(" ", name)).strip()
    m = SIZE_RE.search(name)
    if m:
        name = name[: m.start()].strip()
    else:
        m = QUANTITY_RE.search(name)
        if m:
            name = name[: m.start()].strip()
    m = BARREL_MM_RE.search(name)
    if m:
        name = name[: m.start()].strip()
    m = LENGTH_RE.match(name)
    if m:
        name = name[m.end():].strip()
    seps = list(COLOUR_SEP_RE.finditer(name))
    if seps:
        candidate = name[seps[-1].end():].strip()
        if 1 <= len(candidate.split()) <= 4 and not re.search(r"\d", candidate) and looks_like_colour(candidate):
            return candidate
    return None


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


product_ids = {r["family_id"]: r["bc_product_id"] for r in load_csv("bc_product_ids.csv")}
variants = load_csv("enriched_variants.csv")
ground_truth = {
    (r["family_id"], r["raw_name_from_listing"]): r["colour"]
    for r in load_csv("product_family_members.csv")
}

# family_id -> {normalized colour label: image_url} (first-seen wins), plus a
# GLOBAL colour -> image fallback (first-seen wins) for families whose own
# enrichment fetch came back empty/broken (e.g. a family with real BC option
# values from phase 1 but zero usable offers in phase 2) - the same named
# shade (e.g. "Barley Blonde") is reused across many product lines, so
# borrowing another family's photo for that shade beats no image at all.
image_by_family_colour = {}
image_by_colour_global = {}
for r in variants:
    if not r["image_url"]:
        continue
    colour = ground_truth.get((r["family_id"], r["offer_name"].strip())) or parse_colour(r["offer_name"])
    if not colour:
        continue
    key = (r["family_id"], norm(colour))
    image_by_family_colour.setdefault(key, r["image_url"])
    image_by_colour_global.setdefault(norm(colour), r["image_url"])

upgraded, no_images, failed = 0, 0, 0

for fid, pid in product_ids.items():
    pid = int(pid)
    ostatus, oresp = request("GET", f"/v3/catalog/products/{pid}/options")
    if ostatus >= 300:
        print(f"  FAILED to fetch options for product {pid}: {oresp}")
        failed += 1
        continue

    for opt in oresp.get("data", []):
        if opt["display_name"] != "Hair Palette" or opt["type"] == "swatch":
            continue

        new_values = []
        missing = []
        fallback_used = []
        for v in opt["option_values"]:
            norm_label = norm(v["label"])
            img = image_by_family_colour.get((fid, norm_label))
            if not img:
                img = image_by_colour_global.get(norm_label)
                if img:
                    fallback_used.append(v["label"])
            if not img:
                missing.append(v["label"])
                continue
            new_values.append({
                "id": v["id"],
                "label": v["label"],
                "sort_order": v["sort_order"],
                "value_data": {"image_url": img},
            })

        if missing:
            no_images += 1
            print(f"  product {pid}: {len(missing)}/{len(opt['option_values'])} colours have no image at all "
                  f"({missing[:3]}{'...' if len(missing) > 3 else ''}) - skipping swatch upgrade for this product")
            continue

        if fallback_used:
            print(f"  product {pid}: using another product's photo for {len(fallback_used)} shade(s) "
                  f"without their own image ({fallback_used[:3]}{'...' if len(fallback_used) > 3 else ''})")

        status, resp = request(
            "PUT", f"/v3/catalog/products/{pid}/options/{opt['id']}",
            body={"type": "swatch", "option_values": new_values},
        )
        if status >= 300:
            print(f"  FAILED to upgrade Hair Palette for product {pid}: {resp}")
            failed += 1
        else:
            upgraded += 1
    time.sleep(0.1)

print(f"\nUpgraded {upgraded} products to real swatches, {no_images} skipped (missing images), {failed} failed")
