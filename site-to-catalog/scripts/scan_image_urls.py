#!/usr/bin/env python3
"""Pre-load liveness scan for image URLs in a products CSV.

BigCommerce validates every image_url at product-create time and rejects the
WHOLE product when one URL 404s — so scan before loading, not after.

Usage:
  python3 scan_image_urls.py [products.csv] [--column images] [--workers 24]

Exit code 0 when all URLs respond 200, 1 otherwise (bad URLs listed with SKUs).
"""
import argparse
import concurrent.futures
import csv
import sys
import urllib.request


def check(u):
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return u, r.status
    except Exception as e:
        return u, getattr(e, "code", str(e)[:60])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="products.csv")
    ap.add_argument("--column", default="images")
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    prods = list(csv.DictReader(open(args.csv)))
    key = "sku" if prods and "sku" in prods[0] else "product_id"
    urls = {}
    for p in prods:
        for u in (p.get(args.column) or "").split(","):
            u = u.strip()
            if u:
                urls.setdefault(u, []).append(p[key])

    bad = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for u, st in ex.map(check, urls):
            if st != 200:
                bad.append((u, st, urls[u]))
    print(f"checked {len(urls)} unique urls across {len(prods)} products; bad: {len(bad)}")
    for u, st, skus in bad:
        print(f"  {st} {u}  (products: {','.join(skus[:5])})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
