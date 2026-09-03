# Merchandising Reference

Promotions, pricing, segmentation, and channel merchandising.
Scopes: **Marketing** (promotions, coupons, banners, gift certs), **Products** (price lists), **Customers** (segments), **Channel listings** (channels).

## Contents
- [Promotions (v3)](#promotions-v3)
- [Coupon codes for promotions](#coupon-codes-for-promotions)
- [Classic coupons (v2)](#classic-coupons-v2)
- [Price lists](#price-lists)
- [Customer segments](#customer-segments)
- [Banners & gift certificates](#banners--gift-certificates)
- [Channels & listings](#channels--listings)
- [Pricing & currencies](#pricing--currencies)
- [Merchandising levers cheat sheet](#merchandising-levers-cheat-sheet)

## Promotions (v3)

The modern engine — use this over v2 coupons for anything new.

| Action | Endpoint |
|---|---|
| List | `GET /v3/promotions` (filters: `status=`, `redemption_type=`, `name:like=`) |
| Create | `POST /v3/promotions` (required: `name`, `redemption_type`, `rules`) |
| Update / Delete | `PUT/DELETE /v3/promotions/{id}` |
| Archive / restore (bulk) | `POST /v3/promotions/archive` / `POST /v3/promotions/unarchive` — body is a **bare array of IDs**, e.g. `[12, 13]` (not `{"ids":[...]}`, not "archives") |
| Global settings | `GET/PUT /v3/promotions/settings` |

`GET /v3/promotions` filters: `id=`, `name=`, `code=`, `currency_code=`, `redemption_type=`, `status=`, `channels=` (comma-separated IDs; storewide promos always match), `is_featured=`, `query=` (free-text over name+code). No documented `:like` filters on this endpoint.

Anatomy of a promotion:

```json
{
  "name": "20% off Sale category",
  "redemption_type": "AUTOMATIC",        // or "COUPON"
  "status": "ENABLED",
  "start_date": "2026-08-15T00:00:00Z",
  "end_date": "2026-08-31T23:59:59Z",    // optional
  "max_uses": 500,                        // optional
  "stop": false,                          // true = don't stack later promos
  "channels": [{ "id": 1 }],              // optional; omit/[] = all channels
  "rules": [{
    "action": {
      "cart_items": {
        "discount": { "percentage_amount": "20" },
        "items": { "categories": [42] }
      }
    },
    "apply_once": false,
    "condition": { "cart": { "minimum_spend": "50" } }   // optional
  }],
  "notifications": []
}
```

Action shapes worth knowing: `cart_items` (item-level discount, target by `categories`/`brands`/`products`/`variants` or `{"and":[...]}` combos), `cart_value` (order subtotal discount), `shipping` (free/discounted shipping, `zone_ids` or `"*"`), `gift_item` (free gift `product_id`/`variant_id`), `fixed_price_set` (bundle pricing). Conditions can nest `and`/`or`/`not` over cart contents, spend, and item quantities.

**`notifications` — this is what the control panel UI calls "Banners" under a promotion's edit page (Marketing → Promotions → [promotion] → Banners → "Add banner"), confirmed live — do NOT confuse with the general storefront `/v2/banners` content-block API below, which is a completely different feature.** These are short on-brand text messages shown to shoppers in specific spots as a promotion is/isn't yet satisfied, not images. Each entry: `{"content": "...", "type": "...", "locations": [...]}`, all three required. The control panel UI shows 4 template choices, all 4 confirmed live (**the OpenAPI spec's `NotificationType` enum only lists 3 of them — another spec gap, same pattern as the `/ip/` path prefix issue elsewhere in this skill; don't trust that enum as exhaustive**): "Availability" → **`type: "promotion"`** (found by deliberately sending a bogus type and reading the full valid-values list back from the 422 — the error message enumerates `"promotion"`, `"upsell"`, `"eligible"`, `"applied"` plus uppercase variants; response echoes it back as `"PROMOTION"`), "Upsell" → `UPSELL`, "Eligibility" → `ELIGIBLE`, "Congratulations" → `APPLIED`. `locations` valid values (same deliberate-error-probe technique): `HOME_PAGE`, `PRODUCT_PAGE`, `CART_PAGE`, `CHECKOUT_PAGE` (accepts either case). `PUT /v3/promotions/{id}` with just `{"notifications": [...]}` is a **partial update** — confirmed live, it doesn't clobber `rules`/other fields, so you don't need to resend the whole promotion body just to add banners to an existing one. Note `PUT` replaces the entire `notifications` array each time (not a per-item merge) — resend all banners you want kept, not just the new one.

**"Buy N, get 1 free" (same product) — confirmed live, full recipe:** condition requires `minimum_quantity: N+1` of the product in cart; action discounts **that same product**, capped to `quantity: 1`, at 100%:

```json
{
  "name": "UWELL: Buy 1 Viscore Pro+ Kit, Get 1 Free",
  "redemption_type": "AUTOMATIC",
  "status": "ENABLED",
  "rules": [{
    "condition": {"cart": {"items": {"products": [1424]}, "minimum_quantity": 2}},
    "action": {"cart_items": {"discount": {"percentage_amount": "100"}, "items": {"products": [1424]}, "quantity": 1}},
    "apply_once": true
  }]
}
```

Key `cart_items` action fields beyond `discount`/`items` (per the official spec, `admin-management-promotions.json`): `quantity` (caps how many matching units get discounted — this is what turns a blanket "100% off everything matching" into "100% off exactly 1 unit"; omit for unlimited), `strategy` (`LEAST_EXPENSIVE`/`LEAST_EXPENSIVE_ONLY`/`MOST_EXPENSIVE`/`MOST_EXPENSIVE_ONLY` — which unit(s) get picked when several qualify), `as_total` (bool — spread a fixed discount across matching items instead of applying it per-item), `include_items_considered_by_condition` (bool, **defaults `false`** — by default the units that satisfied the *condition*'s `minimum_quantity` are excluded from the *action*'s discount pool, which is exactly what makes the buy-N-get-1 math work: with `minimum_quantity: 2` and `quantity: 1`, one unit satisfies the condition and the other is the one that gets discounted; you'd only flip this to `true` for something like "buy 1, that same 1 unit is 20% off"), `exclude_items_on_sale` (bool), `add_free_item` (bool — tries to add a free unit to the cart rather than discounting an existing one, falling back to the 100%-off-existing-unit behavior if it can't). The response echoes back `add_free_item: true` and `strategy: "LEAST_EXPENSIVE"` even when omitted from the request — those are server-side defaults, not something that silently failed to save.

**"Buy X, get a DIFFERENT free item Y" — `gift_item` action, confirmed live:** use this instead of `cart_items` when the free item isn't the same product being bought (e.g. "buy a kit, get a free e-liquid"). Body: `{"gift_item": {"variant_id": N, "quantity": M}}` (schema also allows `product_id`, but see gotcha below), condition is a normal `cart` condition with `items` + `minimum_quantity` on the *purchased* product/brand/category:

```json
{
  "name": "VOOPOO: Buy 75 Nexay Kits, Get 75 Nexay Pods Free",
  "redemption_type": "AUTOMATIC",
  "status": "ENABLED",
  "rules": [{
    "condition": {"cart": {"items": {"products": [1564]}, "minimum_quantity": 75}},
    "action": {"gift_item": {"variant_id": 9513, "quantity": 75}},
    "apply_once": true
  }]
}
```

**Gotcha, confirmed live: `gift_item.product_id` fails on any product that has modifier/option variants** — `422 "Products with modifier options cannot be added to the cart automatically. Choose another gift item."` — even though the OpenAPI spec lists `product_id` as valid alongside `variant_id` and marks neither as individually required. The engine can't auto-resolve which variant to gift when there's a choice to make, so use `variant_id` (a specific SKU, e.g. one flavor/strength) instead — that always works regardless of how many variants the parent product has. Condition-side `items.products`/`items.brands` matchers have no such restriction (they match at the product/brand level fine); it's specifically the *gifted* item that needs to be unambiguous.

The `condition.cart.items` matcher for gift-item promos can use `products` (specific SKUs, e.g. "buy any of these named kits") or `brands` (e.g. "buy 5+ of any product from this brand") — same `ItemMatcher` shape as `cart_items` actions.

`cart_value` worked example — "N% off the whole order once spend crosses a threshold" (a common ask):

```json
{
  "name": "5% Off Orders Over $500",
  "redemption_type": "AUTOMATIC",
  "status": "ENABLED",
  "stop": true,
  "rules": [{
    "action": { "cart_value": { "discount": { "percentage_amount": "5" } } },
    "apply_once": true,
    "condition": { "cart": { "minimum_spend": "500" } }
  }]
}
```

Currency note: monetary values are strings in the store's default (or promotion's specified) currency.

**Channel scoping.** `channels` is a real field on the promotion body: an array of objects keyed by `id` (channel ID) — `[{"id": 1}]`, **not** a bare ID array (`[1]` → 422 "must contain a collection of objects") and **not** `channel_id` (→ 422 "Please provide a id"). Omit the field or send `[]` to apply storewide across every channel (this is also what the control panel calls "all channels"); include one or more `{"id": N}` entries to restrict to specific channels ("selected channels" in the UI, under **Marketing → Promotions → This promotion applies to**). Look up channel IDs with `GET /v3/channels` first — ask the user which named channel(s) they mean, since IDs aren't self-explanatory. `channels` is also usable as a `GET /v3/promotions?channels=` query filter, separately from this create/update field.

## Coupon codes for promotions

For `redemption_type: "COUPON"` promotions:

- `GET /v3/promotions/{id}/codes` — list
- `POST /v3/promotions/{id}/codes` — `{"code": "SUMMER20", "max_uses": 100, "max_uses_per_customer": 1}`
- `POST /v3/promotions/{id}/codes/bulk` — generate many random codes: `{"quantity": 500, "code_prefix": "VIP-", "max_uses": 1}` (single-use code drops)
- `DELETE /v3/promotions/{id}/codes/{code_id}` or bulk delete via `?id:in=`

## Classic coupons (v2)

Legacy but still common; needed when the user says "coupon" and the store predates v3 promotions.

- `GET/POST /v2/coupons`, `PUT/DELETE /v2/coupons/{id}`, `DELETE /v2/coupons` (**deletes ALL — confirm loudly**)
- Create body: `{"name": "...", "type": "per_item_discount"|"per_total_discount"|"percentage_discount"|"shipping_discount"|"free_shipping", "code": "SAVE10", "amount": "10", "applies_to": {"entity": "products"|"categories", "ids": [...]}, "enabled": true}`
- Optional: `min_purchase`, `expires` (RFC 2822 date), `max_uses`, `max_uses_per_customer`

## Price lists

Per-customer-group / per-channel price overrides — the tool for wholesale/VIP pricing.

| Action | Endpoint |
|---|---|
| Lists | `GET/POST /v3/pricelists`, `PUT/DELETE /v3/pricelists/{id}` |
| **Delete ALL price lists** | `DELETE /v3/pricelists` (no `{id}` — nukes every price list + its records, confirm loudly) |
| Records (per variant+currency) | `GET /v3/pricelists/{id}/records` (10 concurrent GETs max) |
| Create records (≤100/req) | `POST /v3/pricelists/{id}/records` — 10 concurrent max; rejects invalid items individually, but if a valid item **collides** with an existing record (same price_list_id+variant+currency) the **whole batch rolls back** (`meta.saved_records: 0`) |
| **Bulk upsert records (≤1000/req)** | `PUT /v3/pricelists/{id}/records` — only 2 concurrent requests allowed (vs. 10 for POST); prefer POST for pure creates |
| Upsert/delete one record by currency | `PUT/DELETE /v3/pricelists/{id}/records/{variant_id}/{currency_code}` |
| Cross-price-list batch records | `POST/PUT /v3/pricelists/records` — same item shape, but each item carries its own `price_list_id` so one call can touch multiple price lists (POST concurrency 10; PUT concurrency only 1) |
| Assignments (batch, ≤25/req) | `GET/POST/DELETE /v3/pricelists/assignments` |
| Assignments (single upsert) | `PUT /v3/pricelists/{id}/assignments` (25 concurrent max) |

Record shape: `{"variant_id": 123, "currency": "usd", "price": 8.5, "sale_price": 7.99, "retail_price": 12, "map_price": 8, "bulk_pricing_tiers": [...]}` — can also key by `sku`; `currency` + (`variant_id` or `sku`) are required. Don't send a record for a parent product's own SKU when the product has variants.

Assignments bind a price list to a `customer_group_id` and/or `channel_id` (both optional, but `price_list_id` is required): `POST /v3/pricelists/assignments` with a **bare array** `[{"price_list_id": 1, "customer_group_id": 5}]`. `DELETE /v3/pricelists/assignments` takes only query params (`id`, `price_list_id`, `customer_group_id`, `channel_id`, and `:in` variants) — no body — and requires at least one.

## Customer segments

Segments drive targeted promotions (Enterprise feature).

- `GET/POST /v3/segments` (create body is a **bare array**, e.g. `[{"name": "VIP"}]`; max 1000 segments/store, 10 concurrent requests)
- `PUT/DELETE /v3/segments` — these operate on the **collection**, not `/v3/segments/{id}` (that path doesn't exist). `PUT` body is a bare array of `{"id", "name", "description"}`; `DELETE` takes segment IDs via `?id:in=`.
- **Segment IDs are UUIDs** (strings), not integers — don't assume incrementing integer IDs.
- Shopper profiles: `GET/POST /v3/shopper-profiles` (a profile wraps a `customer_id`; profile IDs are also UUIDs)
- Membership: `GET/POST/DELETE /v3/segments/{seg_id}/shopper-profiles` — `POST` body is a **bare array of shopper-profile UUID strings** (`["uuid1", "uuid2"]`, not objects), max 50/request, 10 concurrent; `DELETE` takes UUIDs via `?id:in=` (no body).
- Reverse lookup: `GET /v3/shopper-profiles/{id}/segments`

Flow: ensure a shopper profile exists per customer → add the profile's UUID to the segment → reference the segment's UUID in a promotion rule condition (`"customer": {"segments": {"id": [...]}}`).

## Banners & gift certificates

- **Banners (v2)**: `GET/POST /v2/banners`, `PUT/DELETE /v2/banners/{id}`. Body: `{"name", "content" (HTML), "page": "home_page"|"category_page"|"brand_page"|"search_page", "location": "top"|"bottom", "date_type": "always"|"custom", "visible": "1"}`. `item_id` required for category/brand pages.
- **Gift certificates (v2)**: `GET/POST /v2/gift_certificates`, `PUT/DELETE /v2/gift_certificates/{id}`. Create: `{"code": "XXX-YYY", "amount": "50.00", "balance": "50.00", "to_email", "to_name", "from_email", "from_name", "status": "active"}`. `DELETE /v2/gift_certificates` nukes all — confirm.

## Channels & listings

Multi-storefront / marketplace merchandising.

- `GET/POST /v3/channels`, `PUT /v3/channels/{id}`. Create requires `name`, `type` (`storefront`|`marketplace`|`pos`|`marketing`), `platform` — `type`/`platform`/`status` must be a valid combo (see BC's channel status matrix) and neither `type` nor `platform` can be changed after creation. Channel `1` is always the default storefront and always exists.
- Product↔channel assignment (puts a product on a **storefront**, incl. the default one): `GET/PUT/DELETE /v3/catalog/products/channel-assignments` — `[{"product_id": 1, "channel_id": 2}]`. This is the fix for "product created via the API isn't listed on any storefront" — product creates do **not** auto-assign to a channel, so always follow a `POST /v3/catalog/products` with this call for whichever channel(s) the product should appear on.
- `GET/POST/PUT /v3/channels/{id}/listings` (+ `DELETE .../listings/{listing_id}`) — BC's own docs say to prefer this for **non-storefront** channels (marketplaces, POS, marketing), not for the default/storefront channel. `state` is one of `active`|`disabled`|`pending`|`pending_disable`|`pending_delete`|`partially_rejected`|`queued`|`rejected`|`submitted`|`error`|`deleted`. `product_id` is immutable after creation; if `listing_id` doesn't exist the API returns 200 with empty data rather than a 404.
- Multi-currency per channel: `GET/PUT /v3/channels/currency-assignments` (all channels, batch) or `GET/PUT /v3/channels/{id}/currency-assignments` (one channel). Currencies must already exist store-wide (`POST /v2/currencies` or control panel) before they can be assigned to a channel.
- Category assignment per channel happens via category **trees** (see catalog.md)

## Pricing & currencies

- **Calculated price lookup**: `POST /v3/pricing/products` — given `channel_id`, `currency_code`, `items: [{"product_id", "variant_id", "options": [...]}]` (and optionally `customer_group_id`, `customer_id`, `country_code`), returns the final resolved price after price lists, promotions, and tax rules are applied. Use this to verify "what would the customer actually see" instead of manually combining catalog price + price list + promotion. `channel_id`, `currency_code`, and `items` are required; limit 50 concurrent requests.
- **Store currencies (v2 only — no v3 equivalent)**: `GET/POST /v2/currencies`, `GET/PUT/DELETE /v2/currencies/{id}`. Create requires `name`, `currency_code`, `currency_exchange_rate`, `token_location`, `token`, `decimal_token`, `thousands_token`, `decimal_places`. `is_default` can only be set to `true`, never unset directly (set a different currency's `is_default: true` instead); a currency with `is_default: true` can't be deleted; `currency_code` is read-only on update.
- To make a non-default currency usable on a specific channel/storefront, create it via `/v2/currencies` first, then assign it with `/v3/channels/currency-assignments` (above).

## Merchandising levers cheat sheet

| Goal | Mechanism |
|---|---|
| Reorder products in a category | `PUT /v3/catalog/categories/{id}/products/sort-order` |
| Feature a product on homepage | `PUT /v3/catalog/products/{id}` with `"is_featured": true` |
| Related products | `PUT /v3/catalog/products/{id}` `"related_products": [-1]` (auto) or explicit ID array |
| Sitewide sale | v3 promotion, `redemption_type: AUTOMATIC`, `cart_items` with `items: {"and": []}` or category targeting |
| VIP pricing | Price list + assignment to customer group |
| Flash sale on schedule | Promotion `start_date`/`end_date` (times are UTC) |
| Single-use influencer codes | `POST /v3/promotions/{id}/codes/bulk` |
