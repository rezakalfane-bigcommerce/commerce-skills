import csv
import re
from collections import defaultdict

LENGTH_RE = re.compile(r'^\s*(\d{2})\s*"\s*[-–]?\s*')  # require the inch mark so "100%"/"10-in-1" never match
COLOUR_SEP_RE = re.compile(r'\s*[-–]\s+')  # matches the separator only (not "+rest"), so finditer can find every occurrence - a greedy "(.+)$" capture would always consume to the string end, making a second match impossible even via finditer
WORTH_TAG_RE = re.compile(r'\s*\(Worth\s*£[\d.]+\)\s*$', re.IGNORECASE)
# Attribute tags that appear inconsistently positioned/worded across listings
# (e.g. "...Shampoo (Sulfate Free)" vs "...(Sulfate Free) Shampoo...") -
# strip wherever found so family-name matching isn't broken by word order,
# and record as a boolean facet-candidate attribute instead.
ATTRIBUTE_TAG_RE = re.compile(r'\s*\(\s*(Sulfate Free)\s*\)\s*', re.IGNORECASE)
SIZE_RE = re.compile(r'\s+(\d+(?:\.\d+)?\s?(?:ml|Ltr|[Ll]itre|L)s?)\s*$')  # bare "L" only matches directly after a digit (case-sensitive, no space) e.g. "1L"
QUANTITY_RE = re.compile(r'\s*[-–]?\s*(\d+\s*(?:pieces?|pack))\s*$', re.IGNORECASE)  # trailing "- 100 Pieces" / "500 Pieces"
BARREL_MM_RE = re.compile(r'\s*[-–]?\s*(\d+)\s*mm\s*$', re.IGNORECASE)  # trailing "- 32mm" (styling tool barrel size)

# Generic product-type/descriptor words that mean a " - <suffix>" split is NOT a
# hair colour (e.g. "Celebrity Choice® - Weft Hair Extensions",
# "AERIS® - Lightweight Digital Hair Dryer") - reject the split if any appear.
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


def looks_like_colour(candidate: str) -> bool:
    # Only reject when the blacklisted word is the TRAILING word: "Clip-In Set"
    # and "Lightweight Digital Hair Dryer" end in a product-type noun, but
    # "Jet Set Black" (a real shade name) has "Set" in the middle with a real
    # colour word ("Black") at the end - checking only the last word tells
    # these apart correctly.
    last_word = candidate.split()[-1].lower().strip("®™")
    return last_word not in NON_COLOUR_WORDS

with open("products_seen.csv", newline="", encoding="utf-8") as f:
    all_rows = list(csv.DictReader(f))

# Drop promo-banner false positives: relative URL (not a real product page) and no name/price.
rows = []
dropped_banners = []
for r in all_rows:
    if r["product_url"].startswith("/") and not r["name_from_listing"] and not r["list_price_from_listing"]:
        dropped_banners.append(r)
        continue
    if not r["name_from_listing"].strip():
        dropped_banners.append(r)
        continue
    rows.append(r)

print(f"Dropped {len(dropped_banners)} promo-banner / nameless rows")
print(f"Remaining real product rows: {len(rows)}")


def parse_name(raw_name):
    """Return (family_name, family_key, length_val, colour_val, size_val, attributes)."""
    name = WORTH_TAG_RE.sub("", raw_name).strip()

    attributes = []
    if ATTRIBUTE_TAG_RE.search(name):
        attributes.append("Sulfate Free")
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
    # Use the LAST " - " occurrence: some base names contain an internal
    # " - " themselves (e.g. "Celebrity Choice® - Weft Hair Extensions"), so
    # a leftmost match would grab everything from that first dash onward.
    seps = list(COLOUR_SEP_RE.finditer(name))
    if seps:
        m = seps[-1]
        candidate = name[m.end():].strip()
        # Guard against false splits: a colour suffix should be short-ish (<=4 words)
        # and not itself contain digits (which would indicate a size spec, not a shade).
        if 1 <= len(candidate.split()) <= 4 and not re.search(r"\d", candidate) and looks_like_colour(candidate):
            colour_val = candidate
            name = name[: m.start()].strip()

    family_key = re.sub(r"\s+", " ", name).strip().lower()
    # Some SKUs are listed with a "Beauty Works" brand prefix on one category
    # page and without it on another (e.g. "10-in-1 Miracle Spray 250ml" vs
    # "Beauty Works 10-in-1 Miracle Spray 50ml") - normalize the key only, so
    # they collapse into one family, but keep the fuller name for display.
    family_key = re.sub(r"^beauty works\s+", "", family_key)
    return name, family_key, length_val, colour_val, size_val, attributes, barrel_mm_val


families = defaultdict(lambda: {
    "display_name": None,
    "members": [],       # list of row dicts with parsed length/colour/size
    "lengths": set(),
    "colours": set(),
    "sizes": set(),
    "attributes": set(),
    "barrel_sizes": set(),
})

for r in rows:
    display_name, family_key, length_val, colour_val, size_val, attrs, barrel_mm_val = parse_name(r["name_from_listing"])
    fam = families[family_key]
    if fam["display_name"] is None or len(display_name) < len(fam["display_name"]):
        fam["display_name"] = display_name
    fam["members"].append({
        **r,
        "parsed_display_name": display_name,
        "length": length_val,
        "colour": colour_val,
        "size": size_val,
        "attributes": attrs,
        "barrel_mm": barrel_mm_val,
    })
    if length_val:
        fam["lengths"].add(length_val)
    if colour_val:
        fam["colours"].add(colour_val)
    if size_val:
        fam["sizes"].add(size_val)
    if barrel_mm_val:
        fam["barrel_sizes"].add(barrel_mm_val)
    fam["attributes"].update(attrs)

print(f"Grouped into {len(families)} product families (before fuzzy-merge pass)")


def name_tokens(text):
    text = re.sub(r'[®™"()%]', "", text.lower())
    return set(re.findall(r"[a-z0-9]+", text))


def name_tokens_ordered(text):
    text = re.sub(r'[®™"()%]', "", text.lower())
    return re.findall(r"[a-z0-9]+", text)


# --- Fuzzy-merge pass -------------------------------------------------------
# Iteratively merge family B into family A whenever A's token set is a STRICT
# SUBSET of B's, with the leftover (B's extra words) being 1-3 short,
# non-blacklisted, non-numeric words. This is safe by construction: a
# *replaced* token (e.g. Aluminium <-> Copper, a different material/product)
# never forms a subset relation, only an *added* token does (e.g. "+Black"),
# so this can only merge "same base product, one extra descriptor" pairs -
# verified against real product SKUs for the Micro Rings cluster (MR-AL-* vs
# MR-SAL-* stayed separate; colour-only variants merged), see conversation.
# Runs to a fixpoint since a merge can enable further merges (multi-hop
# chains, e.g. "Rings" -> "Rings Black" -> "Rings Black 100 Pieces" already
# collapsed by size-stripping, but similar chains can occur elsewhere).
merge_count = 0
for _round in range(6):
    keys = list(families.keys())
    tok_cache = {k: name_tokens(k) for k in keys}
    did_merge = False
    consumed = set()
    for i, sk in enumerate(keys):
        if sk in consumed or sk not in families:
            continue
        s_tok = tok_cache[sk]
        best = None
        for tk in keys:
            if tk == sk or tk in consumed or tk not in families:
                continue
            t_tok = tok_cache[tk]
            if t_tok and t_tok.issubset(s_tok) and t_tok != s_tok:
                leftover = s_tok - t_tok
                if not leftover or len(leftover) > 3:
                    continue
                if leftover & NON_COLOUR_WORDS:
                    continue
                if any(w.isdigit() for w in leftover):
                    continue
                # Prefer the SMALLEST valid target (the most generic base
                # name) - picking a larger one risks landing on a sibling
                # colour family (e.g. "...Rings Blonde" is also a subset of
                # "...Rings Dark Blonde"), which would swallow "Blonde" into
                # the target's identity and leave only "Dark" as leftover.
                cand = (len(t_tok), tk, leftover)
                if best is None or cand[0] < best[0]:
                    best = cand
        if best:
            tk, leftover = best[1], best[2]
            src, dst = families[sk], families[tk]
            # Preserve the singleton's own word order (e.g. "Light Brown", not
            # the alphabetically-sorted "Brown Light") when reconstructing the
            # colour phrase from the leftover tokens.
            ordered_leftover = [w for w in name_tokens_ordered(sk) if w in leftover]
            colour_phrase = " ".join(w.capitalize() for w in ordered_leftover)
            for m in src["members"]:
                m["colour"] = m["colour"] or colour_phrase
                dst["members"].append(m)
                if m["length"]:
                    dst["lengths"].add(m["length"])
                if m["size"]:
                    dst["sizes"].add(m["size"])
                if m["barrel_mm"]:
                    dst["barrel_sizes"].add(m["barrel_mm"])
            dst["colours"].add(colour_phrase)
            dst["attributes"].update(src["attributes"])
            del families[sk]
            consumed.add(sk)
            merge_count += 1
            did_merge = True
    if not did_merge:
        break

print(f"Fuzzy-merge pass: {merge_count} merges across up to 6 rounds")
print(f"Grouped into {len(families)} product families (after fuzzy-merge pass)")

multi_variant_families = {k: v for k, v in families.items() if len(v["members"]) > 1}
single_families = {k: v for k, v in families.items() if len(v["members"]) == 1}
print(f"  families with >1 URL (true variant groups): {len(multi_variant_families)}")
print(f"  families with exactly 1 URL (standalone products): {len(single_families)}")

# Pick a representative member per family: prefer the one with the smallest
# length (or first-seen if no length), as the "canonical" URL to fetch full
# detail from in a later phase.
def variant_sort_key(m):
    try:
        length_num = int(m["length"]) if m["length"] else 0
    except ValueError:
        length_num = 0
    return (length_num, int(m["local_product_id"]))


with open("product_families.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "family_id", "family_name", "member_count", "has_length_option",
        "has_colour_option", "has_size_option", "has_barrel_size_option", "attribute_tags",
        "representative_product_url", "representative_local_product_id",
    ])
    family_id_map = {}
    for i, (key, fam) in enumerate(sorted(families.items(), key=lambda kv: kv[0]), start=1):
        family_id_map[key] = i
        members_sorted = sorted(fam["members"], key=variant_sort_key)
        rep = members_sorted[0]
        w.writerow([
            i,
            fam["display_name"],
            len(fam["members"]),
            bool(fam["lengths"]),
            bool(fam["colours"]),
            bool(fam["sizes"]),
            bool(fam["barrel_sizes"]),
            ";".join(sorted(fam["attributes"])),
            rep["product_url"],
            rep["local_product_id"],
        ])

with open("product_options.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["family_id", "option_name", "option_type"])
    for key, fam in families.items():
        fid = family_id_map[key]
        if fam["lengths"]:
            w.writerow([fid, "Length", "rectangles"])
        if fam["colours"]:
            w.writerow([fid, "Hair Palette", "swatch"])
        if fam["sizes"]:
            w.writerow([fid, "Size", "rectangles"])
        if fam["barrel_sizes"]:
            w.writerow([fid, "Barrel Size", "rectangles"])

with open("product_option_values.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["family_id", "option_name", "value_label", "source_product_url", "source_local_product_id"])
    for key, fam in families.items():
        fid = family_id_map[key]
        seen_lengths, seen_colours, seen_sizes, seen_barrels = set(), set(), set(), set()
        for m in fam["members"]:
            if m["length"] and m["length"] not in seen_lengths:
                seen_lengths.add(m["length"])
                w.writerow([fid, "Length", f'{m["length"]}"', m["product_url"], m["local_product_id"]])
            # BC rejects option values that are duplicates case/whitespace-insensitively
            # (e.g. "Scandinavian Blonde" vs " scandinavian Blonde" from a listing typo)
            colour_key = re.sub(r"\s+", " ", (m["colour"] or "")).strip().lower()
            if m["colour"] and colour_key not in seen_colours:
                seen_colours.add(colour_key)
                w.writerow([fid, "Hair Palette", m["colour"].strip(), m["product_url"], m["local_product_id"]])
            if m["size"] and m["size"] not in seen_sizes:
                seen_sizes.add(m["size"])
                w.writerow([fid, "Size", m["size"], m["product_url"], m["local_product_id"]])
            if m["barrel_mm"] and m["barrel_mm"] not in seen_barrels:
                seen_barrels.add(m["barrel_mm"])
                w.writerow([fid, "Barrel Size", m["barrel_mm"], m["product_url"], m["local_product_id"]])

with open("product_family_members.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "family_id", "local_product_id", "product_url", "raw_name_from_listing",
        "length", "colour", "size", "barrel_mm", "attributes", "list_price", "sale_price",
    ])
    for key, fam in families.items():
        fid = family_id_map[key]
        for m in fam["members"]:
            w.writerow([
                fid, m["local_product_id"], m["product_url"], m["name_from_listing"],
                m["length"] or "", m["colour"] or "", m["size"] or "", m["barrel_mm"] or "",
                ";".join(m["attributes"]),
                m["list_price_from_listing"], m["sale_price_from_listing"],
            ])

with open("dropped_banner_rows.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["local_product_id", "product_url", "thumbnail_url_from_listing"])
    for r in dropped_banners:
        w.writerow([r["local_product_id"], r["product_url"], r["thumbnail_url_from_listing"]])

print("\nWrote: product_families.csv, product_options.csv, product_option_values.csv, "
      "product_family_members.csv, dropped_banner_rows.csv")

# Sample of biggest families for sanity-check
print("\nTop 10 largest families:")
for key, fam in sorted(families.items(), key=lambda kv: -len(kv[1]["members"]))[:10]:
    print(f'  {len(fam["members"]):3d}  {fam["display_name"]}  (lengths={sorted(fam["lengths"])}, colours={len(fam["colours"])})')
