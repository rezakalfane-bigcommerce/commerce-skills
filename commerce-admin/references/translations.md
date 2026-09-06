# Translations (Multi-Language Content) Reference

Confirmed live (2026-09-05) against a real store with multi-storefront locales enabled (a
non-default locale, e.g. `fr`, added to a channel). This is a **GraphQL** API, not REST — separate
shape from every other file in this skill, but same host and auth as the core Management API.

## Base URL and auth

```
POST https://api.bigcommerce.com/stores/{STORE_HASH}/graphql
```

```
X-Auth-Token: {ACCESS_TOKEN}
Content-Type: application/json
Accept: application/json
```

Body is the standard GraphQL envelope: `{"query": "..."}` (use `variables` too if you prefer —
not required, string-interpolating the query directly also works and is what was used for the
live test below).

**OAuth scope**: the API account needs **Store Translations** (read-only or modify). No separate
token-exchange step — same store token as everything else in this skill.

`scripts/bc_api.py` is REST-shaped and doesn't send GraphQL bodies; for this API, POST directly
with `urllib`/`requests`/`fetch`, not through that script.

## resourceType enum — the one real gotcha

The docs' own overview page groups "Categories" and "Brands" under a heading called
**"Product Listings"**, which reads like there might be a `PRODUCT_LISTINGS` enum value — **there
isn't, for categories.** Confirmed live: categories use `resourceType: CATEGORIES`, with
`resourceId: "bc/store/category/{id}"`. Don't guess from the grouping heading; the confirmed
values seen so far:

| resourceType | resourceId format | Confirmed live? |
|---|---|---|
| `PRODUCTS` | `bc/store/product/{id}` | ✅ read + write |
| `CATEGORIES` | `bc/store/category/{id}` | ✅ read + write |
| `PRODUCT_MODIFIERS`, `PRODUCT_FILTERS`, `PRODUCT_URLS`, `BRAND_URLS`, `CATEGORY_URLS`, `LOCATIONS`, `SHIPPING_METHODS`, `TAX_RATES`, `ORDER_STATUSES`, `PROMOTIONS`, `PAYMENT_METHODS`, `ADDRESS_FORM_FIELDS`, `CUSTOMER_FORM_FIELDS`, `CHECKOUT_SETTINGS` | not tested | Documented, not yet verified live |

`channelId` and `localeId` are also URN-shaped: `"bc/store/channel/{numeric_channel_id}"` and
`"bc/store/locale/{locale_code}"` (e.g. `"bc/store/locale/fr"`). Get the channel id from
`GET /v3/channels` (REST, via `bc_api.py`) — it's the numeric storefront channel id, same one
used elsewhere in this skill for channel-scoped calls.

## Read existing translations (confirmed live)

```graphql
query {
  store {
    translations(filters: {
      resourceType: PRODUCTS,
      channelId: "bc/store/channel/1891823",
      localeId: "bc/store/locale/fr",
      resourceIds: ["bc/store/product/338"]
    }) {
      edges {
        node {
          resourceId
          fields { fieldName original translation }
        }
      }
    }
  }
}
```

Confirmed field set actually returned for a `PRODUCTS` resource (all snake_case — **not**
camelCase, despite what some secondary docs/summaries claim for `metaDescription`):
`availability_description`, `description`, `meta_description`, `name`, `page_title`,
`preorder_message`, `search_keywords`, `warranty`. `translation` is `null` until you've set one;
`original` always reflects the resource's default-locale value.

For `CATEGORIES`, the documented field set is `name`, `description`, `page_title`,
`meta_keywords`, `meta_description`, `search_keywords` (not independently re-verified beyond
`name`/`description`, which are confirmed live).

## Write translations (confirmed live)

```graphql
mutation {
  translation {
    updateTranslations(input: {
      resourceType: CATEGORIES,
      channelId: "bc/store/channel/1891823",
      localeId: "bc/store/locale/fr",
      entities: [
        { resourceId: "bc/store/category/1713", fields: [
          { fieldName: "name", value: "VMC double flux — récupération de chaleur" }
        ] },
        { resourceId: "bc/store/category/1714", fields: [
          { fieldName: "name", value: "Extracteurs d'air" }
        ] }
      ]
    }) {
      __typename
      errors { __typename ... on Error { message } }
    }
  }
}
```

Confirmed live: **`entities` batches multiple resources of the same `resourceType` in one
mutation call** — one call for all categories, a separate call for all products (can't mix
resourceTypes in a single `updateTranslations` call). Empty `errors: []` on success. Values with
embedded double quotes need escaping (`\"`) if you're string-interpolating the query rather than
using GraphQL `variables`.

## Practical notes from a real translation pass

- **Only translate generic descriptive words, not brand/model names** — e.g. "Extract fans" →
  "Extracteurs d'air" (translate), but "Cyclone dMEV Boost" or "SLIMLINE 300" stay as-is (proper
  nouns/model numbers, standard practice across locales in real ecommerce catalogs). Check each
  product's `description` length first (`GET /v3/catalog/products` with
  `include_fields=id,name,sku,description`, via `bc_api.py`) — most demo/seed catalogs have empty
  descriptions, so the bulk of the work is just the `name` field.
- **Setting a translation does not update the default-locale/original content** — it's purely an
  overlay read by storefront requests for that specific `localeId`. The default locale keeps
  showing the untouched `name`/`description` from `GET /v3/catalog/products` etc.
- **Storefront propagation isn't instant** — after a successful mutation (verified via the read
  query immediately reflecting the new `translation` value), the actual rendered storefront nav/
  PDP can lag behind for a bit, most likely app-level or edge caching rather than a translation
  API problem. Don't assume the write failed just because a page you load right after still shows
  the old text — re-check the `translations` query directly first (it reflects the true current
  state) before troubleshooting further.
- **Open issue, confirmed live (2026-09-05), not yet resolved**: hours after a successful mutation
  (admin `translations` read-back correctly shows the new `translation` value the whole time), the
  **Storefront GraphQL API itself** — queried directly with `curl`/raw `fetch`, bypassing the app's
  Next.js layer entirely — still returns the untranslated default-locale `name`/`description` for
  `site.product(entityId: ...)`, regardless of the `Accept-Language` header value (`fr`, `fr-FR`,
  `fr-FR,fr;q=0.9`, `FR` all tried, all identical to no header at all). This was tested against a
  store with all locales confirmed enabled at `site.settings.locales` on the storefront schema
  itself (so it isn't a channel/locale-config gap), and against the same `channelId` used for both
  the write mutation and the storefront GraphQL endpoint (so it isn't a channel mismatch either).
  `Product` has no `locale` argument on `name`/`description` in the storefront schema — the only
  locale-shaped field found via introspection is `Product.locales` (`LocaleAlternateConnection`),
  which only returns alternate hreflang `path`/`url` pairs, not translated content. **If you hit
  this**: don't assume it's your app's caching (verify by querying the storefront GraphQL endpoint
  directly, as above) — this looks like it may require BigCommerce platform-side investigation
  (support ticket) rather than a client-side fix. Re-test after several hours in case it's a longer
  edge-cache TTL than the admin API's read-back suggests, but don't keep guessing at request-shape
  workarounds beyond what's documented here without new evidence.

## Additional confirmed catalog resources (2026-09-07)

The following resource types were verified live through the same Admin GraphQL endpoint and support
read/write through `store.translations` and `translation.updateTranslations`:

| resourceType | resourceId format | Confirmed live? |
|---|---|---|
| `PRODUCT_FILTERS` | `bc/store/productFilter/{id}` | ✅ read + write |
| `PRODUCT_OPTIONS` | `bc/store/productOption/{id}` | ✅ read + write |
| `PRODUCT_OPTION_VALUES` | `bc/store/productOptionValue/{id}` | ✅ read + write |
| `PRODUCT_CUSTOM_FIELDS` | `bc/store/productCustomField/{id}` | ✅ read + write |
| `PRODUCT_URL_PATHS` | `bc/store/productUrlPath/{product_id}` | ✅ read + write |
| `CATEGORY_URL_PATHS` | `bc/store/categoryUrlPath/{category_id}` | ✅ read + write |

For these resources, the returned field names are snake_case. URL records use `url_path`; filter,
option, and custom-field records expose the relevant `name` and/or `value` fields. The URL-path
resource names are pluralized with `_URL_PATHS`; they are distinct from the similarly named
`PRODUCT_URLS`/`CATEGORY_URLS` values listed in older documentation.

A complete inventory should paginate `store.translations` with `after` until `pageInfo.hasNextPage`
is false. `updateTranslations` accepts multiple entities only when they share the same
`resourceType`; batch large inventories (50 entities per request is a practical limit) and issue
separate calls for each resource type and locale.

## Localized catalog URL routing in Catalyst

BigCommerce Admin translation read-back confirms URL-path translations immediately, but Catalyst's
locale switcher and proxy must pass the locale context explicitly:

- Locale switching resolves the current path against `PRODUCT_URL_PATHS` and `CATEGORY_URL_PATHS`,
  matches the resource ID, and selects the target locale's `url_path` translation.
- Normalize trailing slashes before comparing paths because catalog records commonly store values
  such as `/products/dmev/`, while `next-intl` pathname values omit the trailing slash.
- The route proxy's Storefront GraphQL `site.route(path: ...)` request must include
  `Accept-Language: {locale}`. Without that header, translated URL paths can fail to resolve and
  fall back to the untranslated slug.
