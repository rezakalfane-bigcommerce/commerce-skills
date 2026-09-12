#!/usr/bin/env python3
"""Load a vertical template (categories.csv + products.csv) into a BigCommerce channel.

Source-agnostic: works with any template following references/vertical-templates.md
(it-components, hvac-distribution, outdoor-gear, vape-distribution...).
Stages: brands -> tree categories (parents first, name+parent reconcile) ->
products (inline images + custom_fields + inline variant matrices) -> channel assignment.

Resumable: SKUs already recorded in the out dir mapping are skipped on rerun.

Usage:
  python3 load_template.py --env rezakalfane --channel-id 1881733 --tree-id 16 \
      [--workdir /path/to/template] [--limit N]

Notes / hard-won fixes baked in:
  - trees/categories POST returns items keyed `category_id` (GET tree view uses `id`);
    category `url` must be an object {"path": ...}, not a plain string.
  - No product-level `sku` is sent when the product has variants: if it equals one
    of the variant SKUs (common in exports) BigCommerce 409s "Sku not unique".
  - Weights are converted kg -> lbs when the target store's units are LBS
    (templates store weight_kg).
  - Pre-run scan_image_urls.py: BigCommerce validates every image_url at create
    time and rejects the whole product if one 404s.
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

for cand in (Path.home() / ".claude/skills/commerce-admin/scripts",
             Path.home() / ".agents/skills/commerce-admin/scripts"):
    if cand.exists():
        sys.path.insert(0, str(cand))
        break
from bc_api import request, get_all  # noqa: E402

KG_TO_LBS = 2.20462


def parse_specs(s):
    out = []
    for kv in s.split("|"):
        if "=" in kv:
            k, v = (x.strip() for x in kv.split("=", 1))
            if k and v:
                out.append({"name": k[:250], "value": v[:250]})
    return out


def fail(msg):
    sys.exit(f"FATAL: {msg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--channel-id", type=int, required=True)
    ap.add_argument("--tree-id", type=int, required=True)
    ap.add_argument("--workdir", default=os.environ.get("CATALOG_WORKDIR", "."))
    ap.add_argument("--limit", type=int, default=0, help="load at most N products (testing)")
    args = ap.parse_args()
    env, channel_id, tree_id = args.env, args.channel_id, args.tree_id
    workdir = Path(args.workdir)

    outdir = workdir / f"load_out_{env}_{channel_id}"
    outdir.mkdir(exist_ok=True)
    cat_map_file = outdir / "bc_category_ids.csv"
    prod_map_file = outdir / "bc_product_ids.csv"
    fail_file = outdir / "failures.csv"

    cats = list(csv.DictReader(open(workdir / "categories.csv")))
    prods = list(csv.DictReader(open(workdir / "products.csv")))

    # store weight units (templates carry weight_kg)
    st, store = request("GET", "/v2/store", env=env)
    to_lbs = st == 200 and store.get("weight_units", "").upper() in ("LBS", "POUNDS")
    print(f"target: env={env} channel={channel_id} tree={tree_id} "
          f"store_units={store.get('weight_units') if st == 200 else '?'}")
    print(f"template: {len(cats)} categories, {len(prods)} products (workdir={workdir})\n")

    # ---------------- brands ----------------
    needed = sorted({p["brand"].strip() for p in prods if p["brand"].strip()})
    brand_map = {b["name"].casefold(): b["id"] for b in get_all("/v3/catalog/brands", env=env)}
    created = 0
    for name in needed:
        if name.casefold() in brand_map:
            continue
        st, body = request("POST", "/v3/catalog/brands", body={"name": name}, env=env)
        if st in (200, 201):
            brand_map[name.casefold()] = body["data"]["id"]
            created += 1
        elif st == 409:
            brand_map = {b["name"].casefold(): b["id"] for b in get_all("/v3/catalog/brands", env=env)}
        else:
            fail(f"brand {name!r}: {st} {body}")
    print(f"[brands] {len(needed)} needed, {created} created")

    # ---------------- categories ----------------
    cat_map = {}
    if cat_map_file.exists():
        cat_map = {r["template_id"]: int(r["bc_id"]) for r in csv.DictReader(open(cat_map_file))}
    if len(cat_map) < len(cats):
        existing = list(get_all(f"/v3/catalog/trees/{tree_id}/categories", env=env))
        by_name_parent = {(e["name"], e["parent_id"]): e.get("category_id", e.get("id")) for e in existing}
        tops = [c for c in cats if not c["parent_category_id"]]
        leaves = [c for c in cats if c["parent_category_id"]]

        def chunk(xs, n=10):
            for i in range(0, len(xs), n):
                yield xs[i:i + n]

        created_map = dict(cat_map)
        for group, is_top in ((tops, True), (leaves, False)):
            to_create = []
            for c in group:
                parent_bc = 0 if is_top else created_map.get(c["parent_category_id"])
                if not is_top and not parent_bc:
                    fail(f"no BC parent id for {c['category_name']!r}")
                hit = by_name_parent.get((c["category_name"], parent_bc))
                if hit:
                    created_map[c["category_id"]] = hit
                else:
                    to_create.append((c, parent_bc))
            for batch in chunk(to_create):
                payload = [{"name": c["category_name"], "tree_id": tree_id,
                            "parent_id": parent_bc,
                            "url": {"path": c["category_slug"], "is_customized": True},
                            "is_visible": True,
                            "sort_order": int(c["sort_order"] or 0)} for c, parent_bc in batch]
                st, body = request("POST", "/v3/catalog/trees/categories", body=payload, env=env)
                data = (body or {}).get("data") or []
                meta = (body or {}).get("meta") or {}
                if st not in (200, 201, 207) or len(data) != len(payload) or meta.get("failed", 0):
                    fail(f"category batch: {st} {body}")
                for (c, _), d in zip(batch, data):
                    created_map[c["category_id"]] = d["category_id"]
        with open(cat_map_file, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["template_id", "bc_id", "name"])
            for c in cats:
                w.writerow([c["category_id"], created_map[c["category_id"]], c["category_name"]])
        cat_map = dict(created_map)
    print(f"[categories] {len(cat_map)} mapped (tree {tree_id})")

    # ---------------- products ----------------
    done = {}
    if prod_map_file.exists():
        done = {r["sku"]: int(r["bc_product_id"]) for r in csv.DictReader(open(prod_map_file))}
    failures = []
    todo = [p for p in prods if p["sku"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[products] {len(done)} already loaded, {len(todo)} to create")

    pmf = open(prod_map_file, "a", newline="")
    pmw = csv.writer(pmf)
    if not done:
        pmw.writerow(["template_product_id", "sku", "bc_product_id"])
    for i, p in enumerate(todo, 1):
        imgs = [u.strip() for u in p["images"].split(",") if u.strip()]
        weight = float(p["weight_kg"] or 0)
        body = {
            "name": p["product_name"][:250],
            "type": "physical",
            "sku": p["sku"],
            "price": float(p["price"]),
            "weight": round(weight * KG_TO_LBS, 3) if to_lbs else weight,
            "description": p["description_html"],
            "brand_id": brand_map.get(p["brand"].strip().casefold()),
            "categories": [cat_map[p["category_ids"]]],
            "custom_url": {"url": p["product_slug"], "is_customized": True},
            "inventory_tracking": "none",
            "is_visible": True,
            "availability": "available",
            "images": [{"image_url": u, "is_thumbnail": j == 0, "sort_order": j,
                        "description": p["product_name"][:250]} for j, u in enumerate(imgs)],
            "custom_fields": parse_specs(p["key_specifications"]),
        }
        if p["ean"].strip():
            body["upc"] = p["ean"].strip()
        if p["part_code"].strip():
            body["mpn"] = p["part_code"].strip()
        if (p.get("variants") or "").strip():
            vs = json.loads(p["variants"])
            body["variants"] = [
                {"sku": v["sku"], "price": v["price"],
                 "option_values": [{"option_display_name": k, "label": str(val)}
                                   for k, val in v["options"].items()]}
                for v in vs]
            body.pop("sku", None)  # variant products: no product-level sku
        if body["brand_id"] is None:
            body.pop("brand_id")
        st, resp = request("POST", "/v3/catalog/products", body=body, env=env)
        if st in (200, 201):
            bc_id = resp["data"]["id"]
            pmw.writerow([p["product_id"], p["sku"], bc_id])
            pmf.flush()
            done[p["sku"]] = bc_id
            print(f"  [{i}/{len(todo)}] {p['sku']} -> {bc_id}")
        else:
            failures.append({"sku": p["sku"], "status": st, "error": str(resp)[:500]})
            print(f"  [{i}/{len(todo)}] {p['sku']} FAILED {st}: {str(resp)[:200]}")
        time.sleep(0.2)
    pmf.close()
    if failures:
        with open(fail_file, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["sku", "status", "error"])
            w.writeheader()
            w.writerows(failures)
        print(f"[products] {len(failures)} failures -> {fail_file}")

    # ---------------- channel assignment ----------------
    if not args.limit:
        ids = list(done.values())
        for i in range(0, len(ids), 50):
            batch = [{"product_id": pid, "channel_id": channel_id} for pid in ids[i:i + 50]]
            st, body = request("PUT", "/v3/catalog/products/channel-assignments", body=batch, env=env)
            if st not in (200, 201, 204):
                fail(f"channel assign {i}: {st} {body}")
        print(f"[channel] assigned {len(ids)} products to channel {channel_id}")

    print("\nDONE.")


if __name__ == "__main__":
    main()
