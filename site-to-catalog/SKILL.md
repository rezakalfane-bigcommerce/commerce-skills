---
name: site-to-catalog
description: "Replicate a live storefront's catalog into a BigCommerce sandbox: crawl the site, parse its navigation into a category tree, group scraped product offers into product families with parsed option values, then load and enrich everything (categories, products, variants, swatches, inventory, SEO) via the BigCommerce Management API. Trigger: /site-to-catalog, or requests like \"replicate this site's catalog\", \"import categories/products from <url>\", \"build a demo catalog from <site>\", \"scrape the nav and load it into BC\"."
---

# site-to-catalog

Turn a live e-commerce site into a fully populated BigCommerce sandbox catalog, stage by stage. Built from (and battle-tested on) a full replication of beautyworksonline.com into a BC sandbox: 140 categories across 2 channel trees, 134 product families, full variant/price matrices, real swatch images, inventory, and SEO fields.

## Prerequisites

- The **`commerce-admin`** skill installed at `~/.claude/skills/commerce-admin/` — every `load_*` script imports its `scripts/bc_api.py` for credential resolution, pagination, retry, and secret redaction. Configure store credentials per that skill's README before any load stage.
- Python 3 with `beautifulsoup4` (`pip install beautifulsoup4`) for the crawl/parse stages.
- A scratch working directory for the pipeline's CSVs/logs (set `CATALOG_WORKDIR`, or run scripts from inside it). Never write pipeline artifacts into a source repo.

## The pipeline

Run stages in order. Each stage's outputs (CSVs) are the next stage's inputs. **Always dry-run and show the user counts/samples before any stage that writes to BigCommerce, and get explicit confirmation before bulk writes.**

| Stage | Script | Input → Output |
|---|---|---|
| 1. Crawl | `scripts/crawl.py` | `categories.csv` → `raw/categories/*.html`, `products_seen.csv`, `category_products.csv`, `crawl_log.csv` |
| 1b. Visuals (optional) | `scripts/extract_site_visuals.py` | site pages → logos/banners/background images for later use |
| 2. Nav → categories | `scripts/parse_nav.py` | saved nav HTML → `categories.csv` + `excluded.csv` |
| 2b. Load categories | `scripts/load_categories.py` | `categories.csv` → BC categories (per tree), `bc_category_ids_tree*.csv` |
| 3. Group families | `scripts/group_families.py` | `products_seen.csv` → `product_families.csv`, `product_family_members.csv`, `product_options.csv`, `product_option_values.csv` |
| 4. Load products | `scripts/load_products.py` (+ `create_missing_products.py` for stragglers) | families → BC base products, `load_products_failures.csv` |
| 5. Enrich | `scripts/enrich_products.py` then `scripts/load_enrichment.py` | scraped detail pages → descriptions, images, ratings, per-variant SKU/price matrix |
| 5b. Repair | `scripts/fix_stale_option_labels.py`, `scripts/debug_variant_failures.py` | fix option-label drift / diagnose variant-matching failures between reruns |
| 6. Swatches | `scripts/load_swatches.py` | per-colour images → upgrade the colour option's display style from `dropdown` to `swatch` |
| 7. Inventory | `scripts/load_inventory.py` | in-stock signals (JSON-LD) → per-variant inventory tracking + seeded stock levels |
| 8. SEO/slugs | `scripts/fill_seo_fields.py`, `scripts/fix_product_slugs.py` | meta title/description + clean product URLs |

## Adapting to a new site

Constants marked `# EDIT PER SITE` in the scripts must be updated first:

- `parse_nav.py` — `SITE_HOST`, plus the **product-vs-category heuristics**: what makes a nav link a product page rather than a category (weight specs like `(48g)`, mm sizes, `(NEW!)` tags, brand-prefixed SKU names), with an allowlist for real collections that look product-like. These are inherently site-specific; rewrite them per site rather than trying to force the old rules.
- `group_families.py` + `load_enrichment.py` + `load_swatches.py` — the **option name-parsing rules** (e.g. stripping a leading `24" -` length, trailing colour after a dash, `(Worth £x)` tags). **These three scripts must use byte-identical parsing rules**: families are keyed on the parsed name, and enrichment/swatch loading later matches offers back to option *values* by re-parsing the same names. Any drift means silent variant-matching failures (that's what `debug_variant_failures.py` and `fix_stale_option_labels.py` exist to repair).
- `load_products.py` / `create_missing_products.py` — `CHANNEL_IDS` and `TREE_TO_CHANNEL` for the target store.
- `crawl.py` — set `CATALOG_WORKDIR` (or run from the working directory).

## Hard-won rules (why the scripts are shaped this way)

- **A BC category tree can only be assigned to one channel.** "Same categories on two channels" means creating an *identical structure twice*, once per tree — and keeping a separate local-id→BC-id map per tree (`bc_category_ids_tree1.csv`, `..._tree2.csv`).
- **Create categories level-by-level, parents first.** A child's `parent_id` must be a BC id that already exists; batch creates at ≤10 categories per request.
- **Nav trees contain lies.** The same landing-page URL appears under multiple parents (BC categories have exactly one parent — give duplicates unique per-parent slugs, never duplicate products); some "category" links are actually product pages or off-domain/info links (exclude them, but write them to `excluded.csv` so the user can review); legacy platform URLs (e.g. Magento `/catalog/category/view/s/<slug>/id/<id>/`) need slug extraction, not naive path-splitting.
- **Enrichment is iterative, not one-shot.** Keep a failures CSV per run and a numbered log per rerun (`load_enrichment_run1.log`, `run2`, ...); parsing edge cases surface only when real data hits them. Rerun until the failure list is empty or explained.
- **Inventory quantities usually aren't public.** Use the real in-stock/out-of-stock signal (JSON-LD availability) and seed plausible quantities with a fixed random seed for reproducibility.
- **Respect the source site.** Throttle the crawl, identify with a normal UA, and only replicate content into a private sandbox/demo — this is for demo-building against a store you have a legitimate reason to model.
- **Never write credentials into pipeline scripts or CSVs.** All API access goes through `bc_api.py`'s credential resolution (env vars, `.env.local`, or `~/.bc-cli/config.json`) — see the `commerce-admin` skill.

## Safety

Stages 2b, 4, 5, 6, 7, 8 **write to a live BigCommerce store**. Before each:
1. Confirm the target store hash with the user (`python ~/.claude/skills/commerce-admin/scripts/bc_api.py list-envs`).
2. Show what will be created/modified (counts + a few sample rows) and get explicit confirmation.
3. Never run a write stage against a store that wasn't explicitly designated as the sandbox/demo target.
