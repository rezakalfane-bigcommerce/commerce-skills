# bigcommerce-admin

A [Claude Code](https://claude.com/claude-code) skill for administering a BigCommerce store through the BigCommerce REST Management APIs — catalog and merchandising, orders and customers, store configuration, and B2B Edition.

## What's in here

- **`SKILL.md`** — the skill definition Claude Code loads: setup/auth, safety rules, workflow, and common failure modes.
- **`scripts/bc_api.py`** — a stdlib-only Python client for the core Management API: resolves credentials, paginates, retries on 429, redacts secrets from all output.
- **`scripts/b2b_api.py`** — the same client pattern pointed at the separate B2B Edition API host/auth headers (`api-b2b.bigcommerce.com`, `X-Auth-Token` + `X-Store-Hash`); reuses `bc_api.py`'s credential resolution.
- **`references/`** — endpoint references Claude reads on demand:
  - `catalog.md` — products, variants, options/modifiers, categories, brands, images, metafields, inventory
  - `merchandising.md` — promotions, coupons, price lists, customer segments, banners, gift certificates, channels
  - `orders-customers.md` — orders, shipments, refunds, customers, customer groups, wishlists
  - `store-admin.md` — store settings, webhooks, redirects, scripts, pages, blog, shipping, tax, logs
  - `b2b-edition.md` — B2B companies (incl. sub-company hierarchies), buyer users/roles, super admins, quotes/RFQs, orders, invoices, payments, shopping lists

## Install

Clone (or copy) this repo into your Claude Code skills directory:

```bash
git clone https://github.com/rezakalfane-bigcommerce/bigcommerce-admin-skill.git ~/.claude/skills/bigcommerce-admin
```

Claude Code picks up any skill under `~/.claude/skills/` automatically — no further registration needed.

## Configure credentials

`scripts/bc_api.py` needs a store hash and an API access token (**Settings → API → API Accounts** in the BigCommerce control panel, "V3 API Token" type). It resolves them from any of the following, in order:

1. **Environment variables** — `BC_STORE_HASH` / `BC_ACCESS_TOKEN`
2. **`.env.local`** in the working directory or a parent — either naming convention works:
   ```
   BC_STORE_HASH=abc123
   BC_ACCESS_TOKEN=xxxx
   ```
   or the Catalyst/Next.js storefront convention:
   ```
   BIGCOMMERCE_STORE_HASH=abc123
   BIGCOMMERCE_ACCESS_TOKEN=xxxx
   ```
   Multiple named environments are also supported: `BC_STAGING_STORE_HASH=...` / `BC_STAGING_ACCESS_TOKEN=...`, selected with `--env staging`.
3. **`~/.bc-cli/config.json`** — for credentials that aren't tied to any one project:
   ```json
   {
     "default_environment": "prod",
     "environments": {
       "prod":    { "store_hash": "...", "access_token": "..." },
       "staging": { "store_hash": "...", "access_token": "..." }
     }
   }
   ```

Run `python scripts/bc_api.py list-envs` to see what's configured (names and truncated store hashes only — never tokens).

`scripts/b2b_api.py` reuses the same token/credential sources — no separate setup — but the API account needs the **B2B Edition** scope enabled (Settings → API → API Accounts → Scopes) or B2B calls fail with a confusing 401/403, even though core calls work fine.

## Usage

Normally you'd just ask Claude Code to do something ("add a 20% off coupon", "bulk update these SKUs' prices", "create a B2B company with an admin user") and it invokes the skill itself. The clients can also be run directly:

```bash
python scripts/bc_api.py GET /v3/catalog/products --params limit=50 include=variants
python scripts/bc_api.py GET /v3/catalog/products --all
python scripts/bc_api.py POST /v3/catalog/products --data '{"name": "...", "type": "physical", "price": 9.99, "weight": 1}'
python scripts/bc_api.py DELETE /v3/catalog/products/123 --yes

python scripts/b2b_api.py GET /api/v3/io/companies
python scripts/b2b_api.py POST /api/v3/io/rfq --data @quote.json
```

See `SKILL.md` for the full command reference, API conventions (v2 vs v3, pagination, batch writes, rate limits), and safety rules around destructive operations.

## Security

Neither script ever prints access tokens — all output is passed through a redactor. Never hardcode credentials into generated scripts or docs; always read them via `bc_api.py`'s credential resolution (which `b2b_api.py` reuses).
