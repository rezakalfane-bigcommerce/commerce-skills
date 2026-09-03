# site-to-catalog

A [Claude Code](https://claude.com/claude-code) skill that replicates a live storefront's catalog into a BigCommerce sandbox: crawl the site, parse its navigation into a category tree, group scraped product offers into product families with parsed option values, then load and enrich everything — categories, products, variants, swatches, inventory, SEO — via the BigCommerce Management API.

Built from a real end-to-end replication (140 categories across 2 channel trees, 134 product families with full variant/price matrices, real swatch images, inventory, and SEO fields).

## What's in here

- **`SKILL.md`** — the staged pipeline Claude Code follows: crawl → nav parse → families → categories → products → enrichment → swatches → inventory → SEO, plus the hard-won rules (single-channel category trees, parents-before-children, consistent option-name parsing across scripts, iterative enrichment with failure CSVs).
- **`scripts/`** — the 15 pipeline scripts, one per stage (see the table in `SKILL.md`). Constants that must change per site/store are marked `# EDIT PER SITE`.

## Prerequisites

- The [`commerce-admin`](../commerce-admin) skill — all load stages use its `bc_api.py` client (credential resolution, pagination, retries, secret redaction).
- Python 3 with `beautifulsoup4`.

## Install

This skill is part of the [`commerce-skills`](https://github.com/rezakalfane-bigcommerce/commerce-skills) monorepo. Quick single-skill install via [`degit`](https://github.com/Rich-Harris/degit):

```bash
npx degit rezakalfane-bigcommerce/commerce-skills/site-to-catalog ~/.claude/skills/site-to-catalog
npx degit rezakalfane-bigcommerce/commerce-skills/commerce-admin ~/.claude/skills/commerce-admin  # prerequisite
```

Claude Code picks up any skill under `~/.claude/skills/` automatically — no further registration needed.

## Usage

Ask Claude Code things like:

- "Replicate the catalog from https://example-shop.com into my BC sandbox"
- "Scrape this site's nav and load the category tree into BigCommerce"
- "Group these scraped products into families and load them with variants"

Stages that write to BigCommerce always show counts/samples and ask for confirmation first.

## Safety

- Write stages only run against an explicitly confirmed sandbox/demo store.
- Crawling is throttled; replicate content only into private sandboxes you have a legitimate reason to model.
- No credentials are ever hardcoded — everything goes through `bc_api.py`'s credential resolution.

## License

MIT
