import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv
CHANNEL_IDS = [1, 1894444]  # EDIT PER SITE / STORE
TREE_TO_CHANNEL = {1: 1, 2: 1894444}  # EDIT PER SITE / STORE


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_price(s):
    if not s:
        return None
    s = s.replace("£", "").replace(",", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def slug_from_url(url):
    path = urlparse(url).path.strip("/")
    if path.endswith(".html"):
        path = path[:-5]
    return path.split("/")[-1] or "product"


families = load_csv("product_families.csv")
options_rows = load_csv("product_options.csv")
option_values_rows = load_csv("product_option_values.csv")
family_members = load_csv("product_family_members.csv")
category_products = load_csv("category_products.csv")
bc_tree1 = {r["local_id"]: r["bc_category_id"] for r in load_csv("bc_category_ids_tree1.csv")}
bc_tree2 = {r["local_id"]: r["bc_category_id"] for r in load_csv("bc_category_ids_tree2.csv")}

# local_product_id (per-URL) -> set of local category ids
prod_to_cats = {}
for r in category_products:
    prod_to_cats.setdefault(r["local_product_id"], set()).add(r["category_id"])

# family_id -> list of local_product_ids
family_members_map = {}
for r in family_members:
    family_members_map.setdefault(r["family_id"], []).append(r["local_product_id"])

# family_id -> options list, option_name -> [values]
family_options = {}
for r in options_rows:
    family_options.setdefault(r["family_id"], []).append(r["option_name"])

family_option_values = {}
for r in option_values_rows:
    family_option_values.setdefault((r["family_id"], r["option_name"]), []).append(r["value_label"])

OPTION_TYPE_MAP = {
    "Length": "rectangles",
    "Size": "rectangles",
    "Barrel Size": "rectangles",
    # "swatch" requires real colour hex/image data per value (BC 422s without
    # it) - we don't have that yet (enrichment phase). Use dropdown for now;
    # can be upgraded to swatch once real swatch images/colours are fetched.
    "Hair Palette": "dropdown",
}

used_slugs = set()
created = []  # (family_id, bc_product_id)
failures = []

print(f"Loading {len(families)} families into BigCommerce...")

for fam in families:
    fid = fam["family_id"]
    name = fam["family_name"].strip()[:250]

    rep_url = fam["representative_product_url"]
    rep_local_id = fam["representative_local_product_id"]

    # price: find the representative member's list/sale price from family_family_members
    rep_row = next(
        (m for m in family_members if m["family_id"] == fid and m["local_product_id"] == rep_local_id),
        None,
    )
    list_price = parse_price(rep_row["list_price"]) if rep_row else None
    sale_price = parse_price(rep_row["sale_price"]) if rep_row else None
    price = list_price or sale_price or 0.01
    if list_price is None:
        sale_price = None  # don't set a sale_price with no base list price

    # categories: union of local category ids across every member URL, mapped to BOTH trees
    local_ids = family_members_map.get(fid, [])
    local_cat_ids = set()
    for lid in local_ids:
        local_cat_ids |= prod_to_cats.get(lid, set())
    bc_cat_ids = []
    for lcid in local_cat_ids:
        if lcid in bc_tree1:
            bc_cat_ids.append(int(bc_tree1[lcid]))
        if lcid in bc_tree2:
            bc_cat_ids.append(int(bc_tree2[lcid]))

    slug = slug_from_url(rep_url)
    base_slug = slug
    i = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{i}"
        i += 1
    used_slugs.add(slug)

    body = {
        "name": name,
        "type": "physical",
        "price": price,
        "weight": 0.5,
        "categories": bc_cat_ids,
        "custom_url": {"url": f"/products/{slug}/", "is_customized": True},
        "is_visible": True,
    }
    if sale_price and sale_price < price:
        body["sale_price"] = sale_price

    if DRY_RUN:
        opt_summary = family_options.get(fid, [])
        print(f"[{fid}] {name} | price={price} sale={sale_price} | cats={bc_cat_ids} | opts={opt_summary} | slug={slug}")
        created.append((fid, f"DRY-{fid}"))
        continue

    status, resp = request("POST", "/v3/catalog/products", body=body)
    if status >= 300:
        failures.append((fid, name, "create", resp))
        print(f"  FAILED create family {fid} ({name}): {resp}")
        continue

    pid = resp["data"]["id"]
    created.append((fid, pid))

    # create options for this family
    for opt_name in family_options.get(fid, []):
        values = family_option_values.get((fid, opt_name), [])
        if not values:
            continue
        opt_body = {
            "display_name": opt_name,
            "type": OPTION_TYPE_MAP.get(opt_name, "dropdown"),
            "option_values": [
                {"label": v, "sort_order": idx} for idx, v in enumerate(values)
            ],
        }
        ostatus, oresp = request("POST", f"/v3/catalog/products/{pid}/options", body=opt_body)
        if ostatus >= 300:
            failures.append((fid, name, f"option:{opt_name}", oresp))
            print(f"  FAILED option '{opt_name}' for family {fid} ({name}): {oresp}")

    if len(created) % 20 == 0:
        print(f"  ...{len(created)}/{len(families)} products created")

print(f"\nCreated {len(created)} products, {len(failures)} failures")

with open("bc_product_ids.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["family_id", "bc_product_id"])
    for fid, pid in created:
        w.writerow([fid, pid])

with open("load_products_failures.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["family_id", "name", "stage", "error"])
    for fid, name, stage, err in failures:
        w.writerow([fid, name, stage, str(err)[:500]])

if DRY_RUN:
    print("\nDry run complete - no API writes performed.")
    sys.exit(0)

# Channel assignment: put every created product on both storefronts
print("\nAssigning products to channels...")
assignments = [
    {"product_id": pid, "channel_id": ch}
    for _, pid in created
    for ch in CHANNEL_IDS
]
for i in range(0, len(assignments), 50):
    chunk = assignments[i : i + 50]
    status, resp = request("PUT", "/v3/catalog/products/channel-assignments", body=chunk)
    if status >= 300:
        print(f"  FAILED channel-assignment chunk {i}: {resp}")
    time.sleep(0.2)

print("Done.")
