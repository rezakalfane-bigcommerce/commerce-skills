import csv
import re
import sys

LENGTH_RE = re.compile(r'^\s*(\d{2})\s*"\s*[-–]?\s*')
COLOUR_SEP_RE = re.compile(r'\s*[-–]\s+')
WORTH_TAG_RE = re.compile(r'\s*\(Worth\s*£[\d.]+\)\s*$', re.IGNORECASE)
ATTRIBUTE_TAG_RE = re.compile(r'\s*\(\s*(Sulfate Free)\s*\)\s*', re.IGNORECASE)
SIZE_RE = re.compile(r'\s+(\d+(?:\.\d+)?\s?(?:ml|Ltr|Litre|L)s?)\s*$')
QUANTITY_RE = re.compile(r'\s*[-–]?\s*(\d+\s*pieces?)\s*$', re.IGNORECASE)
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


def looks_like_colour(c):
    return c.split()[-1].lower().strip("®™") not in NON_COLOUR_WORDS


def parse_offer_name(raw_name):
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
    seps = list(COLOUR_SEP_RE.finditer(name))
    if seps:
        candidate = name[seps[-1].end():].strip()
        if 1 <= len(candidate.split()) <= 4 and not re.search(r"\d", candidate) and looks_like_colour(candidate):
            colour_val = candidate
    return length_val, colour_val, size_val, barrel_mm_val


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


family_rows = {r["family_id"]: r for r in load_csv("product_families.csv")}
variants = load_csv("enriched_variants.csv")
ground_truth = {}
for r in load_csv("product_family_members.csv"):
    ground_truth[(r["family_id"], r["raw_name_from_listing"])] = (
        r["length"] or None, r["colour"] or None, r["size"] or None, r["barrel_mm"] or None,
    )

no_option_count = 0
examples = []
for offer in variants:
    fid = offer["family_id"]
    sku = offer["sku"]
    if not sku:
        continue
    fam = family_rows.get(fid)
    if not fam:
        continue
    has_length = fam["has_length_option"] == "True"
    has_colour = fam["has_colour_option"] == "True"
    has_size = fam["has_size_option"] == "True"
    has_barrel = fam["has_barrel_size_option"] == "True"

    gt = ground_truth.get((fid, offer["offer_name"].strip()))
    if gt:
        length, colour, size, barrel = gt
    else:
        length, colour, size, barrel = parse_offer_name(offer["offer_name"])
    length = offer["length"] or length
    barrel = offer["barrel_mm"] or barrel

    needed = sum([has_length, has_colour, has_size, has_barrel])
    found = sum([bool(has_length and length), bool(has_colour and colour), bool(has_size and size), bool(has_barrel and barrel)])
    if found < needed:
        no_option_count += 1
        if len(examples) < 20:
            examples.append((fid, fam["family_name"], offer["offer_name"], gt, (length, colour, size, barrel), (has_length, has_colour, has_size, has_barrel)))

print(f"{no_option_count} / {len(variants)} offers have incomplete option resolution")
for e in examples:
    print(e)
