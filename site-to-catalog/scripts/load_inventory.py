"""Enable per-variant inventory tracking and set stock levels using the real
in-stock/out-of-stock signal extracted from each offer's JSON-LD, with a
randomized quantity for in-stock items (exact quantities aren't exposed
anywhere on the site)."""
import csv
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402

random.seed(42)
IN_STOCK_RANGE = (5, 50)


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


product_ids = {r["family_id"]: r["bc_product_id"] for r in load_csv("bc_product_ids.csv")}
variants = load_csv("enriched_variants.csv")

in_stock_by_sku = {}
for r in variants:
    if r["sku"]:
        in_stock_by_sku[r["sku"]] = r["in_stock"]

updates = []  # {"id": variant_id, "inventory_level": N}
products_to_track = []
no_variant_products = []

for fid, pid in product_ids.items():
    pid = int(pid)
    status, resp = request("GET", f"/v3/catalog/products/{pid}", params={"include": "variants"})
    if status >= 300:
        print(f"  FAILED to fetch product {pid}: {resp}")
        continue
    d = resp["data"]
    prod_variants = d["variants"]

    if len(prod_variants) <= 1:
        # Standalone product with just the base variant - track at product level instead.
        v = prod_variants[0] if prod_variants else None
        sku = v["sku"] if v else d.get("sku", "")
        flag = in_stock_by_sku.get(sku)
        level = random.randint(*IN_STOCK_RANGE) if flag != "False" else 0
        no_variant_products.append((pid, level))
        continue

    products_to_track.append(pid)
    for v in prod_variants:
        flag = in_stock_by_sku.get(v["sku"])
        if flag == "False":
            level = 0
        elif flag == "True":
            level = random.randint(*IN_STOCK_RANGE)
        else:
            level = random.randint(*IN_STOCK_RANGE)  # unknown - default to in-stock-ish
        updates.append({"id": v["id"], "inventory_level": level})

print(f"{len(products_to_track)} products need variant-level tracking, {len(updates)} variants to update")
print(f"{len(no_variant_products)} standalone products to update at product level")

# Enable variant-level tracking on the multi-variant products first.
for i, pid in enumerate(products_to_track, start=1):
    status, resp = request("PUT", f"/v3/catalog/products/{pid}", body={"inventory_tracking": "variant"})
    if status >= 300:
        print(f"  FAILED to enable variant tracking for product {pid}: {resp}")
    time.sleep(0.05)
print("Enabled variant-level tracking.")

# Batch-update variant inventory levels (<=50/call).
ok, fail = 0, 0
for i in range(0, len(updates), 50):
    chunk = updates[i : i + 50]
    status, resp = request("PUT", "/v3/catalog/variants", body=chunk)
    if status >= 300:
        print(f"  FAILED variant batch {i}: {resp}")
        fail += len(chunk)
    else:
        ok += len(chunk)
    time.sleep(0.2)
print(f"Variant inventory updates: {ok} ok, {fail} failed")

# Standalone products: track at product level with a simple inventory_level.
ok2, fail2 = 0, 0
for pid, level in no_variant_products:
    status, resp = request(
        "PUT", f"/v3/catalog/products/{pid}",
        body={"inventory_tracking": "product", "inventory_level": level},
    )
    if status >= 300:
        print(f"  FAILED product-level inventory for {pid}: {resp}")
        fail2 += 1
    else:
        ok2 += 1
    time.sleep(0.1)
print(f"Standalone product inventory updates: {ok2} ok, {fail2} failed")
