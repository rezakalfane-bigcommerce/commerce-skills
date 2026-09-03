# Store Administration Reference

Scopes vary: **Information & settings**, **Content**, **Sites & routes**, **Store logs**, **Themes**, **Create payments** — check 403s against the scope of the resource family.

## Contents
- [Store info & settings](#store-info--settings)
- [Webhooks](#webhooks)
- [301 redirects](#301-redirects)
- [Scripts](#scripts)
- [Pages & blog](#pages--blog)
- [Themes & widgets](#themes--widgets)
- [Shipping](#shipping)
- [Tax](#tax)
- [Diagnostics](#diagnostics)

## Store info & settings

- `GET /v2/store` — store profile, plan, timezone, currency, features. Cheap sanity check that credentials work; use it as the first call in a new session.
- `GET /v2/time` — server timestamp.
- Settings live under `/v3/settings/...`, each a small `GET`/`PUT` pair. Highlights:
  - `/v3/settings/store/profile`, `/v3/settings/store/locale`, `/v3/settings/store/units-of-measurement`
  - `/v3/settings/storefront/status` — **can take the storefront down** (`"down_for_maintenance_message"` etc.); treat writes as high-risk
  - `/v3/settings/storefront/seo`, `/v3/settings/storefront/robotstxt`, `/v3/settings/storefront/search`, `/v3/settings/storefront/category`, `/v3/settings/storefront/product`, `/v3/settings/storefront/security`
  - `/v3/settings/inventory` + `/v3/settings/inventory/notifications` (low-stock emails)
  - `/v3/settings/catalog` (SKU/option display behavior), `/v3/settings/email-statuses` (transactional email toggles)
  - `/v3/settings/logo`, `POST /v3/settings/logo/image`, `POST /v3/settings/favicon/image`
  - Faceted search: `/v3/settings/search/filters` (+ `/available`, `/contexts`)
  - Analytics providers (GA, Meta pixel, etc.): `GET /v3/settings/analytics`, `GET/PUT /v3/settings/analytics/{id}` — each entry has `channel_id`, `enabled`, `code`.
  - Many accept `?channel_id=` for per-storefront overrides; `null` values mean "inherits global".
- Store-level metafields (distinct from product/customer metafields): `GET/POST /v3/store/metafields`, `GET/PUT/DELETE /v3/store/metafields/{id}`.
- Currencies: `GET/POST /v2/currencies`, `PUT/DELETE /v2/currencies/{id}`.

## Webhooks

`GET/POST /v3/hooks`, `PUT/DELETE /v3/hooks/{id}`

```json
{
  "scope": "store/order/created",
  "destination": "https://example.com/webhooks/bc",
  "is_active": true,
  "headers": { "x-custom-auth": "..." }
}
```

Destination must be HTTPS, served on port 443 (no custom ports), and respond 200 quickly. Common scopes: `store/order/*`, `store/order/created`, `store/order/statusUpdated`, `store/product/*`, `store/product/inventory/updated`, `store/customer/*`, `store/cart/abandoned`, `store/shipment/*`, `store/sku/inventory/*`. A webhook auto-deactivates after 90 days of inactivity (no matching events) or repeated delivery failures — check `is_active` when debugging "webhooks stopped firing". Email notifications for failures: `PUT /v3/hooks/admin` / `GET /v3/hooks/admin?is_active=true`.

## 301 redirects

v3 (preferred, multi-site aware): 
- `GET /v3/storefront/redirects` (filter `site_id=`, `keyword=`)
- `PUT /v3/storefront/redirects` — upsert array: `[{"from_path": "/old-url/", "site_id": 1000, "to": {"type": "product"|"brand"|"category"|"page"|"url", "entity_id": 123}}]` (dynamic targets survive URL changes; `"type": "url"` + `"url"` for static)
- `DELETE /v3/storefront/redirects?id:in=...` (**confirm**) — or `?site_id=...` alone to delete **every** redirect for that site (no `id:in` needed); double-check which one you're sending, this is a common footgun.
- Bulk CSV: export/import jobs under `/v3/storefront/redirects/imex/...`

Site IDs come from `GET /v3/sites`. `/v3/sites` is also a full CRUD resource (create/update/delete storefront sites, each tied 1:1 to a channel, plus per-site SSL certs at `/v3/sites/{site_id}/certificate` and custom URL routing templates at `/v3/sites/{site_id}/routes`) — not otherwise covered in this skill; ask before provisioning a new site on a multi-storefront store.

## Scripts

Inject JS/HTML into storefront pages (analytics tags, chat widgets):

`GET/POST /v3/content/scripts`, `PUT/DELETE /v3/content/scripts/{uuid}`

```json
{
  "name": "GA4",
  "description": "Analytics",
  "html": "<script>...</script>",       // required + kind "script_tag" for inline HTML
  "src": "https://cdn.../tag.js",         // required + kind "src" instead, for a src-based <script> tag
  "kind": "script_tag",                   // "script_tag" (inline html) | "src" (external src)
  "location": "head",                     // head | footer
  "visibility": "all_pages",              // storefront | all_pages | checkout | order_confirmation — all_pages/checkout need Checkout content scope
  "consent_category": "essential",        // essential | functional | analytics | targeting; defaults to "unknown" (hidden when cookie-consent banner is enabled) if omitted
  "auto_uninstall": true
}
```

`html` and `src` are mutually exclusive with their matching `kind`. Scripts also take `channel_id` for per-storefront scoping (omit for all channels). Deleting a script can break tracking/chat — confirm and note which script by name.

## Pages & blog

- **Pages (v3)**: `GET/POST/PUT/DELETE /v3/content/pages` (arrays for batch; single via `/{id}`). Types: `page` (HTML `body`), `link`, `contact_form`, `raw`. Fields: `name`, `url`, `is_visible`, `parent_id`, `sort_order`, `is_homepage`, `channel_id` (defaults to 1 — set explicitly for non-default-channel pages on multi-storefront stores), SEO fields.
- **Blog (v2)**: `GET/POST /v2/blog/posts`, `PUT/DELETE /v2/blog/posts/{id}`. Body: `{"title", "body" (HTML), "url", "tags": [...], "is_published": true, "published_date", "meta_description"}`. `title` and `body` are the only required fields. **`is_published` isn't sticky** — every PUT must re-send `is_published: true` explicitly or the post gets unpublished, even if it was already published.

## Themes & widgets

- Themes: `GET /v3/themes`, `POST /v3/themes` (upload), `GET /v3/themes/{uuid}/configurations`. Activation is **not** per-theme-uuid: `POST /v3/themes/actions/activate` with body `{"variation_id": "..."}` (optional `?channel_id=` to target a specific storefront) — **visual change to live store — confirm**.
- Widgets (Page Builder content): templates at `/v3/content/widget-templates`, instances at `/v3/content/widgets`, placements at `/v3/content/placements` (bind a `widget_uuid` into a named `region` on a given `template_file`, e.g. `pages/home`, `pages/category`, `pages/product`; `entity_id` targets a specific product/category page, omit for home/global). Regions: `GET /v3/content/regions?template_file=pages/home`.
- Whole-page widget snapshots (not a per-page-uuid endpoint): `GET /v3/content/page-widgets?channel_id=&template_file=&entity_id=` to read all widget regions for a template/entity; `POST /v3/content/page-widgets` with a `regions` array to publish/overwrite them.

## Shipping

v2, zone-based:
- `GET/POST /v2/shipping/zones`, `PUT/DELETE /v2/shipping/zones/{id}` — zone types: `country`, `state`, `zip`, `global`
- Methods within a zone: `GET/POST /v2/shipping/zones/{zid}/methods`, `PUT/DELETE .../methods/{mid}` — types: `perorder` (flat per order), `peritem`, `weight`, `total` (table rates), `freeshipping` (with optional minimum), plus carrier types (`endicia`, `usps`, `fedex`, ...)
- Table-rate example: `{"name": "By weight", "type": "weight", "settings": {"default_cost": 10, "range_type": "weight", "ranges": [{"lower_limit": 0, "upper_limit": 5, "shipping_cost": 5}]}, "enabled": true}`
- Carrier connections (account credentials) are **v2, not v3**: `POST/PUT/DELETE /v2/shipping/carrier/connection` — there is no `GET`; credentials are write-only once set.
- Global shipping settings (v3): `GET/PUT /v3/shipping/settings`; per-channel override: `GET/PUT /v3/shipping/settings/channels/{channel_id}` — check this on multi-storefront stores before assuming a shipping-settings change applies everywhere.
- Products' customs info for international: `GET/PUT /v3/shipping/products/customs-information`

## Tax

- Classes: `GET /v2/tax_classes` (v2 read), create/update/delete via `POST/PUT/DELETE /v3/tax/classes`
- Manual zones & rates: `/v3/tax/zones`, `/v3/tax/rates` (rates belong to zones)
- Settings: `GET/PUT /v3/tax/settings`
- Product tax properties (codes for providers like Avalara): `/v3/tax/properties` + `/v3/tax/products/properties`
- Debugging "wrong tax rate applied": `POST /v3/tax/zonecheck` — checks which tax zone applies for a given address + customer group, without placing an order.
- Customer-level tax data (e.g. exemption info): `GET/PUT/DELETE /v3/tax/customers`.

## Diagnostics

- `GET /v3/store/systemlogs` — recent platform events (failed emails, app issues); filter `type=`/`type:not=`, `module=`/`module:not=`, `severity=` (`1`=Success, `2`=Notice, `3`=Warning, `4`=Error; also `severity:min=`/`severity:max=`).
- 403 → missing scope. 429 → rate limit (client script handles). 404 on a valid-looking v2 list → often means empty result on some resources (204 elsewhere) or a wrong store hash.
- Multi-storefront confusion: if a change "doesn't show", check `?channel_id=` variants of the settings endpoint and channel listing overrides.
