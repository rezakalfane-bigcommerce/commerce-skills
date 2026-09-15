# Site adapters — extraction markers that worked

Per-platform selectors/patterns proven in real extractions. Use as starting
points when writing a new `parse_*`/`enrich_*` stage; verify against a saved
page before trusting them (markup drifts).

## OXID eShop (proven on bergfreunde.eu)

**Category/PLP** (server-rendered, ~72 tiles/page, gender via suffix `/for--men/`):
- Tiles: `li.product-item`; link href = PDP URL (root-level descriptive slug
  `{brand}-{name}-{type}/`).
- Tile text is pipe-structured: `… | {discount%} | {brand} | {name} | {type} | {old €} | {price €} | {rating} | ({reviews})`;
  current price in `span.price`.
- JSON-LD `@graph` carries only internal `artId`s + category paths — not useful
  for product data; parse the tiles instead.

**PDP**:
- JSON-LD `Product`: `sku`, `mpn`, one image, ratings. No offers/price.
- **Variant dimensions**: `<li data-mapp-click="pds_select.variant.color|size" data-varsel="VALUE">`
  — the `data-varsel` is on the item itself, not a child. Color SKU bases appear
  as `data-msrc` (`/{sku}-{colorsuffix}/`).
- Current price: `[data-codecept="productPrice"]`; item no. in spec text (`Item No.:`).
- Spec table: the element containing `Item No.:` holds flat `Key: value` pairs —
  regex-extract pairs, stop at `Legal notice` / `Please choose`.
- Description: prefer `.product-longdescription` / `.longdesc` —
  `.product-description-content` **also contains site chrome** ("Ask our experts",
  contact links) that must be stripped. ~20% of products have no long description:
  synthesize `<p>{name}. Recommended use: X. Main material: Y.</p>` from specs.
- Images on `bfgcdn.com` with size tokens (`/1500_1500_90/`): enumerate page URLs,
  keep the largest token per image path; mains vs `*-detail-N` shots.
- robots.txt allows PLP/PDP crawling (only filter params disallowed); OXID variant
  URLs `/*/size--` `/*/colour--` are disallowed and unnecessary anyway.

## Shopify exports / migrations (proven on flawless → BC)

Catalog originally from Shopify (`id` = Shopify gid, images on `cdn.shopify.com` —
publicly fetchable, reusable as import image URLs):
- `vendor` → brand; `product_type` → natural category subdivision
  (e.g. Juices → Nic Salts/Shortfills/10ml via name patterns).
- `skus[]` with `variant_title` + per-variant `price` + **real variant SKUs**
  (no construction needed). `variant_title == "Default Title"` = simple product.
- Option naming per product type: juices/pouches → `Flavour` (titles like
  `Pineapple Ice`) or `Nicotine Strength` (`20mg`); kits/tanks → `Colour`;
  pods/coils → `Resistance` (`0.6ohm XL`). Combo titles `"Fresh Mint / 12mg"`
  split into two options on `\s*/\s*`.
- **Gotcha: the export's first SKU often equals the product's own variant SKU** —
  drop the product-level SKU at create or BigCommerce 409s "Sku not unique".
- Marketing descriptions may contain `<a href>` to the source domain — unwrap all
  links. Watch for the source brand as an English adjective too ("flawless
  finish") — scrub brand-position mentions, keep/replace the adjective
  deliberately.

## Custom Next.js/Makeswift frontend on a BigCommerce backend (proven on primelineparts.com)

Recognizable by product images on `cdn11.bigcommerce.com/s-<store_hash>/...` behind a
fully custom (non-Catalyst) Next.js storefront, often built on Makeswift
(`storage.googleapis.com/s.mkswft.com/...` asset URLs in the page source):
- The top-level category pages (e.g. `/categories/<top-slug>/`) are server-rendered
  and a non-JS fetch gets real product tiles (name/url/image/price) straight from
  the HTML.
- **Trap:** in-page subcategory facets rendered as `?category=<Name>` query params
  are client-side-only (React state hydrated after load) — a plain fetch of that
  URL silently returns the *same* unfiltered top-level tile set, not the filtered
  one. There is no error, so this is easy to miss and load a template with
  duplicate/wrong-category data.
- **Fix:** look for actual nested subcategory routes instead —
  `/categories/<top-slug>/<sub-slug>/` (guess the sub-slug from the facet label,
  e.g. "Window Hardware" → `window-hardware`). These 200 and are server-rendered
  with the real per-subcategory product set. Verify with a quick `curl -o /dev/null
  -w '%{http_code}'` sweep before trusting a batch of WebFetch calls to them.
- No `__NEXT_DATA__` or other embedded JSON blob is present in the HTML (grepping
  for it returns nothing) — don't waste a round-trip looking for one; go straight
  to the nested-route guess.

## BigCommerce → BigCommerce (template from another BC store)

- Extract in-process (`from bc_api import request, get_all`) — **the CLI output
  redacts the store hash from CDN URLs, which silently breaks image extraction**;
  in-process calls return unredacted JSON.
- `/v3/catalog/products?categories:in=<id>` + `include=variants,images,custom_fields,options`
  gets everything; `include=id,images` is invalid (`id` is not an include).
- Beware category sprawl from imports (products in 5–8 categories: type + brand +
  "new" buckets) — pick ONE primary leaf per product for the template.
