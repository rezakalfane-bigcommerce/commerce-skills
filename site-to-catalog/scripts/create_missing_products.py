"""One-off: create BC products for the 2 families that split out of siblings
after the group_families.py word-order/blacklist fixes (Celebrity Choice
Stick Tip Bond, Beauty Works Jumbo Waver) - mirrors load_products.py logic
for a specific family_id list, then appends to bc_product_ids.csv."""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

TARGET_FAMILY_IDS = {"36", "77"}
CHANNEL_IDS = [1, 1894444]  # EDIT PER SITE / STORE


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


families = {r["family_id"]: r for r in load_csv("product_families.csv")}
options_rows = load_csv("product_options.csv")
option_values_rows = load_csv("product_option_values.csv")
family_members = load_csv("product_family_members.csv")
category_products = load_csv("category_products.csv")
bc_tree1 = {r["local_id"]: r["bc_category_id"] for r in load_csv("bc_category_ids_tree1.csv")}
bc_tree2 = {r["local_id"]: r["bc_category_id"] for r in load_csv("bc_category_ids_tree2.csv")}

prod_to_cats = defaultdict(set)
for r in category_products:
    prod_to_cats[r["local_product_id"]].add(r["category_id"])

family_members_map = defaultdict(list)
for r in family_members:
    family_members_map[r["family_id"]].append(r)

family_options = defaultdict(list)
for r in options_rows:
    family_options[r["family_id"]].append(r["option_name"])

family_option_values = defaultdict(list)
for r in option_values_rows:
    family_option_values[(r["family_id"], r["option_name"])].append(r["value_label"])

OPTION_TYPE_MAP = {"Length": "rectangles", "Size": "rectangles", "Barrel Size": "rectangles", "Hair Palette": "dropdown"}

# Get existing slugs so we don't collide with the 134 already-created products.
existing_slugs = set()
for r in families.values():
    existing_slugs.add(slug_from_url(r["representative_product_url"]))

new_rows = []
for fid in TARGET_FAMILY_IDS:
    fam = families[fid]
    name = fam["family_name"][:250]
    rep_url = fam["representative_product_url"]
    members = family_members_map[fid]
    rep_member = next((m for m in members if m["product_url"] == rep_url), members[0])

    list_price = parse_price(rep_member["list_price"])
    sale_price = parse_price(rep_member["sale_price"])
    price = list_price or sale_price or 0.01
    if list_price is None:
        sale_price = None

    local_cat_ids = set()
    for m in members:
        local_cat_ids |= prod_to_cats.get(m["local_product_id"], set())
    bc_cat_ids = []
    for lcid in local_cat_ids:
        if lcid in bc_tree1:
            bc_cat_ids.append(int(bc_tree1[lcid]))
        if lcid in bc_tree2:
            bc_cat_ids.append(int(bc_tree2[lcid]))

    slug = slug_from_url(rep_url)
    base_slug = slug
    i = 2
    while slug in existing_slugs:
        slug = f"{base_slug}-{i}"
        i += 1
    existing_slugs.add(slug)

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

    status, resp = request("POST", "/v3/catalog/products", body=body)
    if status >= 300:
        print(f"FAILED create family {fid} ({name}): {resp}")
        continue
    pid = resp["data"]["id"]
    print(f"Created family {fid} '{name}' -> product {pid}")
    new_rows.append((fid, pid))

    for opt_name in family_options.get(fid, []):
        values = family_option_values.get((fid, opt_name), [])
        if not values:
            continue
        opt_body = {
            "display_name": opt_name,
            "type": OPTION_TYPE_MAP.get(opt_name, "dropdown"),
            "option_values": [{"label": v, "sort_order": idx} for idx, v in enumerate(values)],
        }
        ostatus, oresp = request("POST", f"/v3/catalog/products/{pid}/options", body=opt_body)
        if ostatus >= 300:
            print(f"  FAILED option '{opt_name}': {oresp}")

    for ch in CHANNEL_IDS:
        request("PUT", "/v3/catalog/products/channel-assignments", body=[{"product_id": pid, "channel_id": ch}])

with open("bc_product_ids.csv", "a", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    for fid, pid in new_rows:
        w.writerow([fid, pid])

print(f"\nAppended {len(new_rows)} rows to bc_product_ids.csv")
