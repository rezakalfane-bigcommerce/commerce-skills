"""Fill SEO fields (Page Title, Meta Description, Search Keywords) for every
product, using data we already extracted (family name, short description,
option values)."""
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402


def load_csv(name):
    with open(name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


product_ids = {r["family_id"]: r["bc_product_id"] for r in load_csv("bc_product_ids.csv")}
families = {r["family_id"]: r for r in load_csv("product_families.csv")}
enriched_family = {r["family_id"]: r for r in load_csv("enriched_family.csv")}

option_values_by_family = {}
for r in load_csv("product_option_values.csv"):
    option_values_by_family.setdefault((r["family_id"], r["option_name"]), []).append(r["value_label"])

updated, skipped, failed = 0, 0, 0

for fid, pid in product_ids.items():
    fam = families.get(fid)
    enr = enriched_family.get(fid)
    if not fam:
        skipped += 1
        continue

    name = fam["family_name"].strip()
    page_title = f"{name} | Beauty Works"[:255]

    short_desc = clean_html(enr["short_description"]) if enr else ""
    meta_description = short_desc[:320] if short_desc else f"Shop {name} from Beauty Works."[:320]

    colours = option_values_by_family.get((fid, "Hair Palette"), [])
    keywords = [name, "Beauty Works"]
    keywords += colours[:6]
    if fam["has_length_option"] == "True":
        keywords.append("hair extensions")
    search_keywords = ", ".join(dict.fromkeys(k for k in keywords if k))[:255]

    body = {
        "page_title": page_title,
        "meta_description": meta_description,
        "search_keywords": search_keywords,
    }
    status, resp = request("PUT", f"/v3/catalog/products/{pid}", body=body)
    if status >= 300:
        print(f"  FAILED product {pid} (family {fid}): {resp}")
        failed += 1
    else:
        updated += 1
    time.sleep(0.1)

print(f"\nUpdated {updated}, skipped {skipped}, failed {failed} (of {len(product_ids)})")
