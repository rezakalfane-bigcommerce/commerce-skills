# Catalog & Inventory Reference

All paths relative to `https://api.bigcommerce.com/stores/{STORE_HASH}`.
OAuth scope: **Products** (read-only or modify) for catalog; **Products / Inventory** for inventory endpoints.

## Contents
- [Products](#products)
- [Variants, options, modifiers](#variants-options-modifiers)
- [Categories & category trees](#categories--category-trees)
- [Brands](#brands)
- [Images & videos](#images--videos)
- [Custom fields, metafields, bulk pricing](#custom-fields-metafields-bulk-pricing)
- [Inventory (locations API)](#inventory-locations-api)
- [Recipes](#recipes)

## Products

| Action | Endpoint |
|---|---|
| List/search | `GET /v3/catalog/products` |
| Create | `POST /v3/catalog/products` |
| Get one | `GET /v3/catalog/products/{id}` |
| Update one | `PUT /v3/catalog/products/{id}` |
| **Batch update (≤10)** | `PUT /v3/catalog/products` — array of objects each containing `id` (products must already exist; use `POST` for new ones) |
| Delete one / by filter | `DELETE /v3/catalog/products/{id}` or `?id:in=1,2,3` (**max 250 per call; confirm first**) |
| Bulk category assign | `PUT /v3/catalog/products/category-assignments` — array of `{"product_id": 1, "category_id": 2}`; `DELETE` needs a filter |
| Bulk channel assign | `PUT /v3/catalog/products/channel-assignments` — array of `{"product_id": 1, "channel_id": 2}`; `DELETE` needs a filter |
| Catalog summary | `GET /v3/catalog/summary` — counts, inventory value, cheapest/priciest |

Required on create: `name`, `type` (`physical`|`digital`), `price`, `weight` (required by the schema regardless of type — include it even for digital). Everything else optional. High-value optional fields: `sku`, `categories` (array of IDs), `brand_id`, `inventory_level` + `inventory_tracking` (`none`|`product`|`variant`), `is_visible` (defaults true — set `false` when staging), `sort_order`, `sale_price`, `retail_price`, `custom_url: {"url": "/my-product/", "is_customized": true}`, SEO fields (`page_title`, `meta_description`), `availability` (`available`|`disabled`|`preorder`).

**Gotcha — channel listing:** creating a product via the API does not put it on any storefront channel's listing by default (it only shows on the default channel's category pages once assigned). Use `PUT /v3/catalog/products/channel-assignments` to explicitly list it on other channels; avoid parallel channel-assignment requests, and never send parallel requests for the same product IDs.

Useful list filters: `sku=`, `sku:in=`, `categories:in=`, `id:in=`/`id:not_in=`, `channel_id:in=`, `brand_id=`, `is_visible=`, `inventory_level:less=`, `date_modified:min=`, `keyword=` (searches name/sku/description/brand name), `availability=`. **Note:** unlike brands/categories, the products endpoint's `name` filter is exact-match only — there is no `name:like` on products; use `keyword=` for partial name search. Sub-resources via `include=variants,images,custom_fields,bulk_pricing_rules,primary_image,modifiers,options,videos`. Trim with `include_fields=name,sku,price,inventory_level`.

Products can be created with a full variant matrix in one call by passing an inline `variants` array (each with `sku`, `price`, and `option_values: [{"option_display_name": "Color", "label": "Red"}]`). This is the fastest way to build an optioned product — BigCommerce creates the options automatically.

## Variants, options, modifiers

**Variants** = purchasable SKUs generated from **variant options** (Color, Size). **Modifiers** (engraving text, gift wrap checkbox) never create SKUs. Pick the right one before building.

| Action | Endpoint |
|---|---|
| List variants of product | `GET /v3/catalog/products/{pid}/variants` |
| **Create variant** | `POST /v3/catalog/products/{pid}/variants` — collection endpoint, **not** `/variants/{vid}` |
| Update/delete variant | `PUT/DELETE /v3/catalog/products/{pid}/variants/{vid}` |
| **All variants store-wide** | `GET /v3/catalog/variants` — `sku=` is **exact-match only** (no `sku:in`); paginate for bulk lookups, or use `GET /v3/inventory/items?sku:in=...` instead (see Inventory section) |
| **Batch variant update** | `PUT /v3/catalog/variants` — up to **50** items/call; array with `id` to update, or omit `id` and send `product_id`+`sku`+`option_values` (each with `id`/`option_id`) to create variants in the same call |
| Options | `.../products/{pid}/options` and `.../options/{oid}/values` |
| Modifiers | `.../products/{pid}/modifiers` and `.../modifiers/{mid}/values` |

Create-variant requires `sku` + `option_values` (get the option/value IDs from the Options endpoints first). Limits: 600 SKUs/product, 255-char SKU. Only one variant is created per call — for a full matrix in one shot, use inline `variants` on product create instead (see Products above).

Variant-level overrides: `price`, `sale_price`, `inventory_level` (only honored when product `inventory_tracking=variant`), `purchasing_disabled`, `image_url`, dimensions/weight.

**Options**: create requires `display_name`, `type`, `option_values` (255-char name limit; only one option per `POST`, but its `option_values` array can hold many). **Option values**: create requires `label` + `sort_order`; 250 values/option limit; `is_default` is read-only on values — set the default via `PUT` on the parent option instead.

**Modifiers**: creating a checkbox modifier with option values takes two calls — create the modifier, then a second call to add/update its values. Date-type modifiers must be sent in ISO-8601 (ATOM) format; omitting the date on an update throws a server error. Modifier-value images are set via a separate multipart `POST` to `.../values/{vid}/image`, not inline — `adjusters.image_url` in the modifier/value body is read-only.

## Categories & category trees

BigCommerce's own docs recommend the **trees** endpoints over the classic ones wherever possible (multi-storefront-aware):

- `PUT /v3/catalog/trees` — **upsert** trees: object with an `id` = update, without `id` = create. `name` required to create, not required to update. `channels` (one channel per tree) is required to create a tree but **must be absent** on update — it's not supported there.
- `GET /v3/catalog/trees/{tree_id}/categories` — the tree's categories. **Rate-limited to 1 concurrent request.**
- `GET/POST/PUT/DELETE /v3/catalog/trees/categories` — batch list/create/update/delete across trees. Create requires `name` + (`tree_id` or `parent_id`); `url` is optional but if set must be unique per channel+category, else the category is created without the URL and the response comes back multi-status.

Store-wide limits (apply to both trees and classic endpoints): 16,000 categories/store, 1,000 categories/product, 50-char name, 8 levels of child-category depth, 65,535-char description.

Classic single-tree endpoints still work: `GET/POST /v3/catalog/categories`, `PUT/DELETE /v3/catalog/categories/{id}`. Required on create: `name`, `parent_id` (0 = top level). **Deleting a category that still has products returns 422** — move the products first (product-side `categories` array, `PUT /v3/catalog/products/{id}`, or `DELETE /v3/catalog/products/category-assignments` with a filter). A category's products are otherwise assigned from the **product** side, not the category side: the `categories` array on the product, `PUT /v3/catalog/products/{id}`, or the bulk `PUT /v3/catalog/products/category-assignments` endpoint (see Products above).

Category image: `POST /v3/catalog/categories/{id}/image` (multipart `image_file`, one at a time, JPEG/GIF/PNG/ICO, 8MB max) or set `image_url` directly on the category via `PUT`.

Product order within a category (merchandising!): `GET/PUT /v3/catalog/categories/{id}/products/sort-order` with `[{"product_id": 123, "sort_order": 0}, ...]`.

## Brands

`GET/POST /v3/catalog/brands`, `PUT/DELETE /v3/catalog/brands/{id}`. Create requires only `name` (must be unique — 409 on duplicate; search with `name:like=` and reuse). 30,000 brands/store limit. Brand image: `POST /v3/catalog/brands/{id}/image` (multipart `image_file`, one at a time) or set `image_url` on the brand via `PUT` — there's no way to update the image through the image endpoint itself.

## Images & videos

- `GET/POST /v3/catalog/products/{pid}/images`; `PUT/DELETE .../images/{iid}`
- JSON body with `image_url` (must be publicly fetchable, ≤255 chars) **or** multipart with `image_file` (use `bc_api.py --file`) — only one image per call
- `is_thumbnail: true` sets the primary image; `sort_order` controls gallery order; `description` is the alt text
- Limits: 1,000 images/product, 8MB per image file/URL; supported types BMP/GIF/JPEG/PNG/WBMP/XBM/WEBP
- Variant images: `POST /v3/catalog/products/{pid}/variants/{vid}/image`
- Videos: `.../products/{pid}/videos` — YouTube IDs only (`video_id` required)

## Custom fields, metafields, bulk pricing

- **Custom fields** (visible on storefront): `.../products/{pid}/custom-fields`, body `{"name": "Material", "value": "Cotton"}`. Each name+value pair must be unique within the product. Limits: 200 custom fields/product, 250 chars per field.
- **Metafields** (structured, permissioned): `.../products/{pid}/metafields` — required: `namespace`, `key`, `value`, `permission_set`. Limit 250 metafields per resource (order/product/category/variant/brand) per client ID. Batch endpoints exist at `/v3/catalog/products/metafields` (and equivalents for variants, categories, brands, inventory locations, carts, orders, channels, store). Duplicate (namespace,key) → 409; update instead.
- **Bulk pricing rules**: `.../products/{pid}/bulk-pricing-rules`, body `{"quantity_min": 10, "quantity_max": 0, "type": "percent"|"fixed"|"price", "amount": 15}`.

## Inventory (locations API)

For multi-location stores; simple stores can just set `inventory_level` on products/variants.

**Locations**: `GET /v3/inventory/locations`, `POST/PUT/DELETE /v3/inventory/locations`.
- Limits: 100 active locations/store; up to 50 concurrent create requests.
- `location_id` 1 is always the store's default shipping origin — it cannot be deleted and its shipping-origin status cannot be changed.
- You cannot delete a location that is a shipping origin or has open order transactions; locations assigned to pickup methods *can* be deleted.
- **Deleting a location deletes its inventory stock too** — treat as destructive, confirm first.
- Locations support their own metafields: `.../locations/{loc}/metafields` and batch `.../locations/metafields`.

**Items**: `GET /v3/inventory/locations/{loc}/items` (1,000 items/call) and `GET /v3/inventory/items?sku:in=...` (also accepts `variant_id:in=`, `product_id:in=`, `location_id:in=`, `location_code:in=`; 1,000 items/call) — the best way to resolve SKUs to `variant_id`/`product_id` in bulk, since `/v3/catalog/variants` only supports exact-match `sku=`. `PUT /v3/inventory/locations/{loc}/items` updates per-location inventory *settings* (not levels) for items.

**Adjustments** (2,000 items/call on both; each item identified by `sku`, `variant_id`, **or** `product_id` — not just `sku`):
- **Absolute set** (the recommended default): `PUT /v3/inventory/adjustments/absolute` — `{"items": [{"location_id": 1, "sku": "ABC", "quantity": 40}]}`. Batches more efficiently than the Catalog API and has lower complexity than relative.
- **Relative (+/-)**: `POST /v3/inventory/adjustments/relative` — same shape, `quantity` may be negative. Per BigCommerce's own guidance, use this **only** when the absolute quantity isn't known — e.g., syncing inventory changes driven by orders through a third party — otherwise prefer absolute.

## Recipes

**Bulk price update from a list of SKUs** — `/v3/catalog/variants` only supports exact-match `sku=`, not `sku:in`; resolve SKUs to variant IDs via `GET /v3/inventory/items?sku:in=...` instead (1,000/call), then send chunks of ≤50 to `PUT /v3/catalog/variants`. Check the response's per-item results for partial failures.

**Clone a product** — `GET` it with `include=variants,images,custom_fields,options,modifiers`, strip `id` fields, adjust `name`/`sku` (must be unique), `POST` it back. Images copy by re-sending each `url_zoom` as `image_url`.

**Hide out-of-stock products** — `GET /v3/catalog/products?inventory_level:less=1&inventory_tracking=product&include_fields=name`, confirm the list with the user, then batch `PUT` with `{"id": ..., "is_visible": false}` in chunks of 10.
