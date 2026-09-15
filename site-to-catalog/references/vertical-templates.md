# Vertical templates — compact, reusable demo catalogs

A **vertical template** is a distilled, source-scrubbed mini-catalog (≈5 top-level
categories, ≤20 total, ≤150 products) stored as two CSVs, loadable into any
BigCommerce channel in ~15–20 min. Built once from a source (live site crawl,
BC store export, or existing CSV dumps), reused across many demo environments.

Existing templates (load results in `load_out_*/` next to each template):

| Vertical | Source | Products | Variants |
|---|---|---|---|
| `it-components` | targetcomponents BC store (scraped CSVs) | 150 simple | – |
| `hvac-distribution` | greenmill BC store (scraped CSVs) | 150 simple | – |
| `outdoor-gear` | bergfreunde.eu (live OXID crawl) | 145 | 2,556 (Colour×Size) |
| `hardware-repair-parts` | primelineparts.com (live custom Next.js/BC-backed crawl) | 124 simple | – |
| `vape-distribution` | flawless BC store (Shopify export) | 146 | 1,366 (Flavour/Colour/Resistance/Nicotine Strength) |

## Template anatomy

`categories.csv` (ids are template-local, parents before children):

```
category_id, category_name, category_slug, parent_category_id, category_url, sort_order
```

`products.csv` (15 base columns + 2 variant columns):

```
product_id, product_name, category_ids, product_slug, product_url, sku,
manufacturer, brand, ean, part_code, weight_kg, key_specifications,
description_html, images, price, options, variants
```

- `key_specifications` — `Name=Value | Name=Value | …` → becomes BC custom fields
- `images` — comma-separated absolute URLs (first = thumbnail); must all respond 200
- `options` — pipe-separated option names, e.g. `Colour|Size` (empty = simple product)
- `variants` — JSON array `[{"sku","price","options":{"Colour":"Red","Size":"M"}}]`
  (empty = simple product; variant SKUs must be globally unique across the template)
- `weight_kg` — always kilograms; the loader converts if the target store is LBS
- `product_url` — informational source PDP link (empty when it would leak the source)

## Loading

```bash
python3 scripts/scan_image_urls.py /path/to/template/products.csv   # ALWAYS pre-scan
python3 scripts/load_template.py --env <env> --channel-id <id> --tree-id <id> \
    --workdir /path/to/template [--limit 1]
```

The loader is idempotent/resumable (`load_out_<env>_<channel>/` mapping files),
reconciles existing brands/categories by name, creates variant matrices inline
on product create, and channel-assigns everything at the end. Test with
`--limit 1` and inspect the product before the full run.

## Selection & scrubbing checklist (when building a new template)

- **Quotas**: ≤5 top / ≤20 cats / ≤150 products; 10–14 products per leaf.
- **Pick for demo richness**: brand round-robin (diversity), prefer multi-image,
  variant-rich, spec-rich products; mix price points; dedupe across leaves.
- **Every product must have**: ≥1 live image URL, specs, description, price>0, SKU.
- **Scrub source traces** (all fields, then re-scan with a case-insensitive regex):
  own-brand names → a neutral own-brand (e.g. ProTrade, VaporWorks), SKU prefixes,
  category names, descriptions (**site chrome leaks in**: contact blocks, "ask our
  experts", off-domain `<a href>`s), and **slugs — regenerate them from scrubbed
  names** (source slugs keep the old brand).
- **Keep image URLs on the source host** — BigCommerce fetches them at load time
  and re-hosts on its own CDN; no trace remains in the demo store.
- **When HTML extraction returns placeholders or repeated images**, capture the
  rendered page with Playwright:

  ```bash
  python3 scripts/capture_rendered_images.py products.csv \
    --column product_url --host assets.example.com \
    --output captured_images.jsonl
  ```

  Use the captured `page_url` to map images back to products, keep the source
  URL/alt/dimensions as provenance, and inspect a few assignments visually.
  Then replace images with `replace_product_images.py`; it requires a dry run
  and `--replace-existing` because BigCommerce image updates may append records.
  Run `scan_image_urls.py` on the updated CSV before loading or refreshing.
- Validate: unique slugs/SKUs (incl. variant SKUs), tree parent refs, then
  `scan_image_urls.py` — one 404 blocks a product create.

## Verification after loading

- Products on channel == template count (`?channel_id:in=` filter).
- Tree: `GET /v3/catalog/trees/{id}/categories` — **the response nests `children`;
  don't verify by matching `parent_id` across the top-level array** (looks like
  leaves are missing/mis-parented when they aren't).
- Variant/image totals vs template; spot-check one product with
  `include=variants,images,custom_fields,options`.
