"""Prefix every product's custom_url with /products/ to avoid collisions
with category URLs sharing the same slug (found 12 real collisions)."""
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


bc_ids = [r["bc_product_id"] for r in load_csv("bc_product_ids.csv")]
fixed, skipped, failed = 0, 0, 0

for pid in bc_ids:
    status, resp = request("GET", f"/v3/catalog/products/{pid}", params={"include_fields": "custom_url"})
    if status >= 300:
        print(f"  FAILED to fetch product {pid}: {resp}")
        failed += 1
        continue
    url = resp["data"]["custom_url"]["url"]
    if url.startswith("/products/"):
        skipped += 1
        continue
    new_url = "/products" + url
    ustatus, uresp = request(
        "PUT", f"/v3/catalog/products/{pid}",
        body={"custom_url": {"url": new_url, "is_customized": True}},
    )
    if ustatus >= 300:
        print(f"  FAILED to update product {pid} url to {new_url}: {uresp}")
        failed += 1
    else:
        fixed += 1
    time.sleep(0.1)

print(f"\nFixed {fixed}, already-prefixed {skipped}, failed {failed} (of {len(bc_ids)})")
