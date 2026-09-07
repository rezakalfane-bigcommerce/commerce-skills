# Currency and Locale Reference

Confirmed against the Catalyst commerce-b2b storefront integration (2026-09-07). Currency and
locale are separate concerns: the locale controls translated content, paths, labels, and number
formatting; the currency controls transactional prices and the cart's currency.

## Locale context

Use the locale configured for the storefront channel, represented in GraphQL as:

- Channel: `bc/store/channel/{numeric_channel_id}`
- Locale: `bc/store/locale/{locale_code}`

Storefront GraphQL requests that need localized catalog content or route resolution must send the
locale in `Accept-Language` (for example, `fr`, `es`, or `it`). The Admin Translations API uses the
same locale URN in its `localeId` filter and mutation input. URL-path translations are stored as
`PRODUCT_URL_PATHS` and `CATEGORY_URL_PATHS`; normalize trailing slashes when matching paths.

## Currency context

The storefront exposes available currencies through `site.currencies`; filter to currencies that
are transactional before offering them as checkout choices. The selected currency must be passed
to price queries and every rendered monetary value should be formatted with the active locale and
currency together (for example, `Intl.NumberFormat(locale, { style: 'currency', currency })`).

Changing a cart's currency uses the Storefront GraphQL mutation:

```graphql
mutation UpdateCartCurrency($input: UpdateCartCurrencyInput!) {
  cart {
    updateCartCurrency(input: $input) {
      cart { entityId currencyCode }
    }
  }
}
```

`updateCartCurrency` creates a new cart in the requested currency. Persist the returned cart
`entityId`, invalidate cart data, and reload all totals and line-item prices. A currency selector
must not leave the old cart ID in session storage or cookies.

Changing a cart's locale is separate and uses `UpdateCartLocaleInput`; it updates the existing cart
in place. Keep the cart locale synchronized when the storefront language changes, but do not treat
that operation as a currency conversion.

## Validation checklist

- Verify the selected locale and currency independently.
- Re-read cart `currencyCode` after a currency mutation and confirm the cart ID changed.
- Render all monetary values with the same locale/currency formatter, including dashboard totals,
  order/quote/invoice details, project pricing, and cart summaries.
- Never infer currency from a symbol; use the ISO currency code returned by the API.
