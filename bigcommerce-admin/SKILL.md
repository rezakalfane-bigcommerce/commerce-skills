---
name: bigcommerce-admin
description: >-
  Perform BigCommerce store administration and merchandising tasks via the
  BigCommerce REST Management APIs. Use this skill whenever the user wants to
  create, read, update, or delete anything in a BigCommerce store: products,
  variants, categories, brands, images, metafields, inventory, price lists,
  promotions, coupons, gift certificates, banners, customer segments, orders,
  shipments, refunds, customers, customer groups, webhooks, redirects, scripts,
  pages, blog posts, channels, store settings, or B2B Edition (companies,
  buyer users, quotes/RFQs, sales reps). Also use it when the user mentions a
  store hash, X-Auth-Token, api.bigcommerce.com, "the catalog", "merch" tasks,
  bulk product updates, B2B, quotes, or asks to automate anything in a
  BigCommerce store — even if they don't say "API".
---

# BigCommerce Admin & Merchandising

Work with the BigCommerce REST Management APIs to administer a store: catalog and merchandising, orders and customers, and store configuration.

## Setup and authentication

All Management API requests hit:

```
https://api.bigcommerce.com/stores/{STORE_HASH}/v3/...   (preferred)
https://api.bigcommerce.com/stores/{STORE_HASH}/v2/...   (legacy resources)
```

Authentication is a single header — no OAuth dance for store-level API accounts:

```
X-Auth-Token: {ACCESS_TOKEN}
Content-Type: application/json
Accept: application/json
```

### Where credentials come from

`scripts/bc_api.py` resolves credentials itself, in this priority order:

1. **Environment variables** `BC_STORE_HASH` / `BC_ACCESS_TOKEN`
2. **`.env.local`** in the working directory or any parent — `BC_STORE_HASH=...` / `BC_ACCESS_TOKEN=...` lines, plus optional per-environment variants like `BC_STAGING_STORE_HASH=...`
3. **`~/.bc-cli/config.json`** — named environments:

```json
{
  "default_environment": "prod",
  "environments": {
    "prod":    { "store_hash": "...", "access_token": "..." },
    "staging": { "store_hash": "...", "access_token": "..." }
  }
}
```

Each entry's keys may be `store_hash`/`access_token` or camelCase `storeHash`/`accessToken` — both are accepted.

Select an environment with `--env NAME` (or `BC_ENV=NAME`). Discover what's configured with `python scripts/bc_api.py list-envs` — it prints environment names and truncated store hashes only, never tokens.

Tokens come from the store control panel (**Settings → API → API Accounts**) and don't expire. If a request returns **403**, the token is missing an OAuth scope — tell the user which resource needs which scope (e.g., Products modify for catalog writes) rather than retrying.

### Credential hygiene — non-negotiable

- **Never open, cat, print, or read the contents of `.env.local`, `~/.bc-cli/config.json`, or any credential file.** The client script loads them itself; there is no reason for their contents to ever enter the conversation. To find out what environments exist, use `list-envs` — nothing else.
- **Never echo a token or store hash** back to the user, put one in a URL you display, log one, or include one in error messages. The script redacts both from all of its own output; don't undo that by printing values yourself.
- **Never copy credentials into other files** — no hardcoding into generated scripts, notebooks, docs, README examples, commit messages, or artifacts. Generated code must import `request`/`get_all` from `bc_api.py` (or read the same sources at runtime) rather than embedding values.
- If the user pastes a token directly into chat, use it via an environment variable for the session and suggest they move it into `.env.local` or `~/.bc-cli/config.json` — and that they rotate it, since it's now in the conversation.
- If no credentials are found anywhere, ask the user to add them to one of the three sources — don't ask them to paste the token into chat.

### Multi-environment discipline

When both a production and a non-production environment exist, state which environment each command targets **before** running it, and default to the non-production one for anything experimental. Never run destructive or bulk-write operations against an environment the user hasn't explicitly named in this conversation.

## The bundled client

Use `scripts/bc_api.py` for all requests instead of writing ad-hoc curl/fetch code. It resolves credentials (see above), handles pagination, retries 429s using the store's rate-limit headers, redacts secrets from output, and pretty-prints responses:

```bash
# GET with query params
python scripts/bc_api.py GET /v3/catalog/products --params limit=50 include=variants

# Fetch every page (follows meta.pagination)
python scripts/bc_api.py GET /v3/catalog/products --all

# Target a named environment; list what's configured (names only, no secrets)
python scripts/bc_api.py GET /v2/store --env staging
python scripts/bc_api.py list-envs

# Change the default environment in ~/.bc-cli/config.json (validated, no secrets shown)
python scripts/bc_api.py set-default staging

# POST/PUT with a JSON body (inline or @file)
python scripts/bc_api.py POST /v3/catalog/products --data '{"name": "...", "type": "physical", "price": 9.99, "weight": 1}'
python scripts/bc_api.py PUT /v3/catalog/products --data @batch_update.json

# DELETE (script asks for --yes on destructive calls)
python scripts/bc_api.py DELETE /v3/catalog/products/123 --yes
```

For large jobs (hundreds of writes), write a small Python script that imports `request()` and `get_all()` from `bc_api.py` rather than shelling out per item.

## API conventions that matter

**v3 vs v2.** Prefer v3 everywhere it exists. Orders, coupons (classic), gift certificates, banners, customer groups, blog, shipping zones, and store info are still v2-only. v3 responses are wrapped as `{"data": ..., "meta": ...}`; v2 returns bare objects/arrays and returns **204 with no body** when a list is empty — don't treat that as an error.

**Pagination.** v3: `?page=N&limit=250` (250 max on most endpoints), read `meta.pagination.total_pages`. v2: `?page=N&limit=250`, keep going until a 204/empty page.

**Filtering.** v3 supports operators as query-param suffixes: `id:in=1,2,3`, `name:like=shirt`, `date_modified:min=2026-01-01`, `price:max=50`, `sku=ABC`. Use `include=` (e.g. `variants,images,custom_fields`) and `include_fields=`/`exclude_fields=` to keep payloads small — always trim fields on large listings.

**Batch writes.** Use batch endpoints instead of loops wherever they exist: `PUT /v3/catalog/products` (up to 10 products per request), `PUT /v3/catalog/variants`, price list record upserts (up to 1,000 per request), `POST /v3/customers` (arrays — even a single customer must be wrapped in an array). This is dramatically faster and gentler on rate limits.

**Rate limits.** Quotas are per-store per-token in a rolling 30-second window (150 requests on standard plans, higher on Pro/Enterprise). The client script already backs off on 429 using `X-Rate-Limit-Time-Reset-Ms`. When planning bulk work, prefer batch endpoints and mention the expected runtime to the user for very large catalogs.

**Concurrency.** Don't parallelize writes to the same resource; BigCommerce has no optimistic locking on most endpoints and last-write-wins.

## Safety rules

Some endpoints are irreversible and store-wide. Before calling any of these, show the user exactly what will be affected and get explicit confirmation:

- Any `DELETE` with a filter or no ID (`DELETE /v3/catalog/products?id:in=...`, "Delete All Coupons", "Delete All Gift Certificates", "Delete All Orders")
- Order archival, refunds, payment capture/void
- Changing storefront status (taking the store down), robots.txt, or checkout settings
- Deleting webhooks, scripts, or redirects (can silently break integrations/SEO)

For bulk mutations, do a read-first dry run: fetch what matches the filter, show a count and a small sample, then execute. After bulk writes, verify with a spot-check read.

## Workflow

1. **Confirm credentials** (env vars set, or ask).
2. **Identify the domain** and read the matching reference file — they contain the endpoints, required fields, gotchas, and worked examples:
   - `references/catalog.md` — products, variants, options/modifiers, categories & category trees, brands, images, metafields, custom fields, bulk pricing, catalog summary, inventory adjustments & locations
   - `references/merchandising.md` — promotions & coupon codes (v3), classic coupons (v2), price lists & assignments, customer segments/shopper profiles, banners, gift certificates, product sort order, channels & channel listings, featured/related products
   - `references/orders-customers.md` — orders (v2), order statuses, shipments, refunds & payment actions, order metafields, customers (v3), addresses, attributes, customer groups (v2), subscribers, wishlists
   - `references/store-admin.md` — store info & settings endpoints, webhooks, 301 redirects, scripts, pages, blog posts, themes & widgets, shipping zones/methods, tax classes, system logs
   - `references/b2b-edition.md` — B2B Edition companies, buyer users, sales reps, quotes/RFQs. **Separate API host and auth headers from everything else** — read this before making any B2B call.
3. **Plan the calls** — smallest number of requests, batch where possible, read before destructive writes.
4. **Execute with `bc_api.py`**, watching for the failure modes below.
5. **Verify and report** — re-read what changed, summarize IDs created/modified, and surface any partial failures (v3 batch endpoints return per-item errors in a 207-style response body; check every element).

## Common failure modes

- **422 on product create**: missing one of the required fields `name`, `type`, `price`, `weight` — or a duplicate SKU/product name conflict.
- **409 on category/brand create**: name already exists at that level. Look it up with `name:like=` and reuse the ID.
- **v2 order updates**: `PUT /v2/orders/{id}` with `status_id` changes status; product line changes require the order-products sub-resource, not the order body.
- **Metafields**: `permission_set` is required (`read`, `write`, `app_only`, `read_and_sf_access`, `write_and_sf_access`); duplicates of (namespace, key, owner) 409.
- **Image uploads**: use `image_url` (publicly reachable) in JSON, or multipart `image_file`. Local files must go multipart — the client script supports `--file` for this.
- **Variant option confusion**: v3 "variant options" generate purchasable variants with their own SKUs; "modifiers" don't create variants. Building a variant matrix means creating options + option values first, or supplying `variants` inline on product create.
