"""
Phase 2 loader: push enriched descriptions/images/ratings and the real
per-variant SKU/price matrix (from enriched_variants.csv) into the 134
BigCommerce products created in phase 1.

Reuses the exact same name-parsing rules as group_families.py so an offer's
parsed (length, colour, size, barrel_mm) matches the option *values* that
were already created on each product.
"""
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv

# --- same parsing rules as group_families.py (kept in sync manually) -------
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
    "silicone", "lined", "pieces", "piece",
}


def looks_like_colour(candidate: str) -> bool:
    last_word = candidate.split()[-1].lower().strip("®™")
    return last_word not in NON_COLOUR_WORDS


def parse_offer_name(raw_name):
    """Return (length, colour, size, barrel_mm) parsed the same way group_families.py did."""
    if not raw_name:
        return None, None, None, None
    name = WORTH_TAG_RE.sub("", raw_name).strip()
    if ATTRIBUTE_TAG_RE.search(name):
        name = re.sub(r"\s+", " ", ATTRIBUTE_TAG_RE.sub(" ", name)).strip()

    size_val = None
    m = SIZE_RE.search(name)
    if m:
        size_val = m.group(1).strip()
        name = name[: m.start()].strip()
    else:
        m = QUANTITY_RE.search(name)
        if m:
            size_val = m.group(1).strip()
            name = name[: m.start()].strip()

    barrel_mm_val = None
    m = BARREL_MM_RE.search(name)
    if m:
        barrel_mm_val = f"{m.group(1)}mm"
        name = name[: m.start()].strip()

    length_val = None
    m = LENGTH_RE.match(name)
    if m:
        length_val = m.group(1)
        name = name[m.end():].strip()

    colour_val = None
    # Use the LAST " - " occurrence, not the first: some base family names
    # themselves contain an internal " - " (e.g. "Celebrity Choice® - Weft
    # Hair Extensions"), so a leftmost greedy match grabs everything from
    # that first dash onward and produces a too-long, rejected candidate.
    seps = list(COLOUR_SEP_RE.finditer(name))
    if seps:
        candidate = name[seps[-1].end():].strip()
        if 1 <= len(candidate.split()) <= 4 and not re.search(r"\d", candidate) and looks_like_colour(candidate):
            colour_val = candidate

    return length_val, colour_val, size_val, barrel_mm_val


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


product_ids = {r["family_id"]: r["bc_product_id"] for r in load_csv("bc_product_ids.csv")}
enriched_family = {r["family_id"]: r for r in load_csv("enriched_family.csv")}
enriched_variants = load_csv("enriched_variants.csv")
family_rows = {r["family_id"]: r for r in load_csv("product_families.csv")}
selected_fields = load_csv("enriched_selected_fields.csv")
weight_rows = load_csv("enriched_weights.csv")

variants_by_family = {}
for r in enriched_variants:
    variants_by_family.setdefault(r["family_id"], []).append(r)

# Ground truth for (length, colour, size, barrel) per (family, raw listing
# name) - computed once by group_families.py, including via its fuzzy-merge
# pass which recovers colours that have no dash separator (e.g. "Aluminium
# Micro Rings Dark Blonde 100 Pieces") and that a regex re-parse of the
# offer name alone cannot find. Look this up FIRST; only fall back to
# parse_offer_name() when a listing name has no exact match.
ground_truth_by_family_name = {}
for r in load_csv("product_family_members.csv"):
    ground_truth_by_family_name[(r["family_id"], r["raw_name_from_listing"])] = (
        r["length"] or None, r["colour"] or None, r["size"] or None, r["barrel_mm"] or None,
    )

selected_fields_by_family = {}
for r in selected_fields:
    selected_fields_by_family.setdefault(r["family_id"], []).append((r["field_name"], r["field_value"]))

GRAMS_TO_OZ = 0.0352739619
weight_by_family_length = {}  # family_id -> {length: weight_oz}
for r in weight_rows:
    weight_by_family_length.setdefault(r["family_id"], {})[r["length"]] = round(float(r["weight_g"]) * GRAMS_TO_OZ, 3)

stats = {"updated": 0, "images_added": 0, "variants_created": 0, "variant_failures": 0, "skipped": []}

print(f"Loading enrichment for {len(product_ids)} products...")

for i, (fid, pid) in enumerate(product_ids.items(), start=1):
    pid = int(pid)
    fam = family_rows.get(fid)
    enr = enriched_family.get(fid)
    if not fam or not enr:
        stats["skipped"].append((fid, "missing family/enrichment row"))
        continue

    short_desc = enr["short_description"]
    full_desc = enr["full_description_html"]
    # BC description field is rich HTML: lead with the short marketing blurb
    # as an intro paragraph, then the full features/application/aftercare
    # content underneath.
    description = "\n".join(p for p in (f"<p>{short_desc}</p>" if short_desc else "", full_desc) if p)
    images = [u for u in enr["images"].split("|") if u]
    rating_avg = enr["rating_avg"]
    rating_count = enr["rating_count"]
    sku_prefix = enr["sku_prefix"]

    has_length = fam["has_length_option"] == "True"
    has_colour = fam["has_colour_option"] == "True"
    has_size = fam["has_size_option"] == "True"
    has_barrel = fam["has_barrel_size_option"] == "True"
    has_any_option = has_length or has_colour or has_size or has_barrel

    update_body = {}
    if description:
        update_body["description"] = description
    if not has_any_option and sku_prefix:
        update_body["sku"] = sku_prefix[:255]

    if DRY_RUN:
        print(f"[{fid}->{pid}] update={list(update_body.keys())} images={len(images)} "
              f"rating={rating_avg}/{rating_count} variants_to_try={len(variants_by_family.get(fid, []))}")
    else:
        # Per-step idempotency: fetch current state once and only perform
        # each step (description, images, custom fields, variants) if it
        # looks incomplete - so a rerun after an interruption fills in
        # exactly what's missing instead of blanket-skipping or duplicating.
        cstatus, cresp = request(
            "GET", f"/v3/catalog/products/{pid}",
            params={"include": "images,variants,custom_fields"},
        )
        if cstatus >= 300:
            # Never proceed on an unknown state - a failed pre-check (e.g.
            # exhausted 429 retries) previously fell through to "nothing
            # exists" and re-attempted variant creates that already existed,
            # causing global SKU-uniqueness collisions. Skip and retry later.
            print(f"  [{i}/{len(product_ids)}] family {fid} -> product {pid}: could not fetch current state ({cresp}), skipping this run")
            continue
        existing = cresp["data"]
        existing_images = existing.get("images", [])
        existing_variant_skus = {v["sku"] for v in existing.get("variants", []) if v.get("sku")}
        existing_field_names = {cf["name"] for cf in existing.get("custom_fields", [])}

        if update_body:
            status, resp = request("PUT", f"/v3/catalog/products/{pid}", body=update_body)
            if status >= 300:
                print(f"  FAILED update product {pid} (family {fid}): {resp}")
            else:
                stats["updated"] += 1

        if not existing_images:
            for idx, img_url in enumerate(images[:12]):
                istatus, iresp = request(
                    "POST", f"/v3/catalog/products/{pid}/images",
                    body={"image_url": img_url, "is_thumbnail": idx == 0, "sort_order": idx},
                )
                if istatus >= 300:
                    print(f"  FAILED image {idx} for product {pid}: {iresp}")
                else:
                    stats["images_added"] += 1
                time.sleep(0.1)

        custom_fields_to_set = []
        if rating_avg:
            custom_fields_to_set += [("source_rating_avg", rating_avg), ("source_rating_count", rating_count)]
        custom_fields_to_set += selected_fields_by_family.get(fid, [])
        for key, val in custom_fields_to_set:
            if key in existing_field_names:
                continue
            cstatus2, cresp2 = request(
                "POST", f"/v3/catalog/products/{pid}/custom-fields",
                body={"name": key[:250], "value": str(val)[:250]},
            )
            if cstatus2 >= 300 and "already exists" not in str(cresp2):
                print(f"  FAILED custom field {key} for product {pid}: {cresp2}")

    # --- discover colours missing from phase-1 grouping -----------------
    # Some families only had 1 URL during the category crawl (so got no
    # Hair Palette option) but the product page itself reveals real colour
    # offers. Family 14 is a known "hub/landing page" false-positive (its
    # representative URL aggregates unrelated sibling products' offers) -
    # excluded explicitly rather than via a fragile count-based heuristic.
    # Matched by NAME, not family_id: family numbering shifts every time
    # group_families.py reruns, and a stale numeric ID here would silently
    # stop excluding the real hub page (this exact bug happened once already).
    HUB_PAGE_FALSE_POSITIVES = {"BARELY THERE® Mix & Match"}
    discovered_colours = set()
    discovered_lengths = set()
    if fam["family_name"] not in HUB_PAGE_FALSE_POSITIVES:
        for offer in variants_by_family.get(fid, []):
            l, c, s, b = parse_offer_name(offer["offer_name"])
            l = offer["length"] or l
            if not has_colour and c:
                discovered_colours.add(c)
            if not has_length and l:
                discovered_lengths.add(l)
        if len(discovered_colours) > 1:
            has_colour = True  # use the freshly-discovered option below
        if len(discovered_lengths) > 1:
            has_length = True

    # --- variant matrix -------------------------------------------------
    if (has_any_option or discovered_colours or discovered_lengths) and not DRY_RUN:
        if discovered_colours:
            opt_body = {
                "display_name": "Hair Palette",
                "type": "dropdown",
                "option_values": [{"label": c, "sort_order": i} for i, c in enumerate(sorted(discovered_colours))],
            }
            nstatus, nresp = request("POST", f"/v3/catalog/products/{pid}/options", body=opt_body)
            if nstatus >= 300 and "already been used" not in str(nresp):
                print(f"  FAILED to create discovered Hair Palette option for product {pid}: {nresp}")
        if discovered_lengths:
            opt_body = {
                "display_name": "Length",
                "type": "rectangles",
                "option_values": [{"label": f'{l}"', "sort_order": i} for i, l in enumerate(sorted(discovered_lengths, key=int))],
            }
            nstatus, nresp = request("POST", f"/v3/catalog/products/{pid}/options", body=opt_body)
            if nstatus >= 300 and "already been used" not in str(nresp):
                print(f"  FAILED to create discovered Length option for product {pid}: {nresp}")

        ostatus, oresp = request("GET", f"/v3/catalog/products/{pid}/options")
        if ostatus >= 300:
            print(f"  FAILED to fetch options for product {pid}: {oresp}")
            continue
        value_id_by = {}  # (option_display_name_lower, value_label_lower) -> (option_id, value_id)
        option_id_by_name = {}
        next_sort_order = {}
        for opt in oresp.get("data", []):
            option_id_by_name[opt["display_name"].lower()] = opt["id"]
            next_sort_order[opt["id"]] = len(opt.get("option_values", []))
            for v in opt.get("option_values", []):
                value_id_by[(opt["display_name"].lower(), norm(v["label"]))] = (opt["id"], v["id"])

        def get_or_create_value(option_name, label):
            """The original crawl sometimes missed a colour/size that the
            live page now offers (e.g. a shade added since); the family's
            option already exists but that one value doesn't. Add it rather
            than dropping the dimension, which would break BC's "must supply
            a value for every option" rule for this variant."""
            key = (option_name.lower(), norm(label))
            pair = value_id_by.get(key)
            if pair:
                return pair
            opt_id = option_id_by_name.get(option_name.lower())
            if not opt_id:
                return None
            sort_order = next_sort_order.get(opt_id, 0)
            next_sort_order[opt_id] = sort_order + 1
            vstatus, vresp = request(
                "POST", f"/v3/catalog/products/{pid}/options/{opt_id}/values",
                body={"label": label, "sort_order": sort_order},
            )
            if vstatus >= 300:
                print(f"  FAILED to add missing '{option_name}' value {label!r} for product {pid}: {vresp}")
                return None
            new_pair = (opt_id, vresp["data"]["id"])
            value_id_by[key] = new_pair
            return new_pair

        for offer in variants_by_family.get(fid, []):
            sku = offer["sku"]
            if not sku:
                continue  # standalone-style offer with no distinct sku, nothing to add as a variant
            if sku in existing_variant_skus:
                continue  # already created in a prior run
            gt = ground_truth_by_family_name.get((fid, offer["offer_name"].strip()))
            if gt:
                length, colour, size, barrel = gt
            else:
                length, colour, size, barrel = parse_offer_name(offer["offer_name"])
            # the group's own length/barrel (page-level truth) is more reliable
            # than re-parsing the offer name for those two dimensions
            length = offer["length"] or length
            barrel = offer["barrel_mm"] or barrel

            option_values = []
            if has_length and length:
                pair = get_or_create_value("length", f'{length}"')
                if pair:
                    option_values.append({"option_id": pair[0], "id": pair[1]})
            if has_colour and colour:
                pair = get_or_create_value("hair palette", colour)
                if pair:
                    option_values.append({"option_id": pair[0], "id": pair[1]})
            if has_size and size:
                pair = get_or_create_value("size", size)
                if pair:
                    option_values.append({"option_id": pair[0], "id": pair[1]})
            if has_barrel and barrel:
                pair = get_or_create_value("barrel size", barrel)
                if pair:
                    option_values.append({"option_id": pair[0], "id": pair[1]})

            if not option_values:
                stats["variant_failures"] += 1
                continue

            price = offer["price"]
            list_price = offer["list_price"]
            vbody = {"sku": sku[:255], "option_values": option_values}
            if offer.get("image_url"):
                vbody["image_url"] = offer["image_url"]
            fam_weights = weight_by_family_length.get(fid, {})
            if length and length in fam_weights:
                vbody["weight"] = fam_weights[length]
            try:
                if price:
                    vbody["price"] = float(price)
                if list_price:
                    vbody["price"] = float(list_price)
                    vbody["sale_price"] = float(price)
            except ValueError:
                pass

            vstatus, vresp = request("POST", f"/v3/catalog/products/{pid}/variants", body=vbody)
            if vstatus >= 300:
                stats["variant_failures"] += 1
                if stats["variant_failures"] <= 15:
                    print(f"  FAILED variant sku={sku} product {pid}: {vresp}")
            else:
                stats["variants_created"] += 1
            time.sleep(0.15)

    if i % 15 == 0:
        print(f"  ...{i}/{len(product_ids)} products processed")

print("\n--- Summary ---")
print(stats)
