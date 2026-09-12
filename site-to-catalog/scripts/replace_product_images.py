#!/usr/bin/env python3
"""Replace BigCommerce product images from a template CSV.

The loader mapping must contain ``sku,bc_product_id``. This intentionally
deletes existing image records before adding replacements because a product PUT
may append images instead of replacing them.

Always dry-run first. Writes require --replace-existing.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/commerce-admin/scripts"))
from bc_api import request  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("products_csv")
    ap.add_argument("mapping_csv")
    ap.add_argument("--env", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-existing", action="store_true")
    args = ap.parse_args()
    with open(args.products_csv, encoding="utf-8", newline="") as f:
        products = {r["sku"]: r for r in csv.DictReader(f)}
    with open(args.mapping_csv, encoding="utf-8", newline="") as f:
        mapping = list(csv.DictReader(f))
    jobs = []
    for row in mapping:
        p = products.get(row.get("sku", ""))
        if not p:
            continue
        urls = [u.strip() for u in (p.get("images") or "").split(",") if u.strip()]
        if urls:
            jobs.append((int(row["bc_product_id"]), row["sku"], urls, p["product_name"][:250]))
    print(f"target: env={args.env}; products: {len(jobs)}; image refs: {sum(len(x[2]) for x in jobs)}")
    for pid, sku, urls, _ in jobs[:5]:
        print(f"  {sku} ({pid}) -> {len(urls)} images")
    if args.dry_run:
        return
    if not args.replace_existing:
        raise SystemExit("refusing to write: pass --replace-existing after reviewing the dry run")

    deleted = added = 0
    for pid, sku, urls, name in jobs:
        st, body = request("GET", f"/v3/catalog/products/{pid}/images", env=args.env)
        if st != 200:
            raise RuntimeError(f"GET images {sku}/{pid}: {st} {body}")
        for image in body.get("data", []):
            st, resp = request("DELETE", f"/v3/catalog/products/{pid}/images/{image['id']}", env=args.env)
            if st not in (200, 204):
                raise RuntimeError(f"DELETE image {sku}/{pid}/{image['id']}: {st} {resp}")
            deleted += 1
        for order, url in enumerate(urls[:12]):
            st, resp = request("POST", f"/v3/catalog/products/{pid}/images", env=args.env,
                               body={"image_url": url, "is_thumbnail": order == 0,
                                     "sort_order": order, "description": name})
            if st not in (200, 201):
                raise RuntimeError(f"POST image {sku}/{pid}: {st} {resp}")
            added += 1
        time.sleep(0.1)
    print(f"complete: deleted {deleted}, added {added}")


if __name__ == "__main__":
    main()
