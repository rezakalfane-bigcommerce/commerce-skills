# Orders & Customers Reference

Scopes: **Orders** (orders, shipments), **Order transactions / payments** (capture, void, refunds), **Customers** (customers, groups, attributes).

## Contents
- [Orders (v2)](#orders-v2)
- [Order sub-resources](#order-sub-resources)
- [Shipments](#shipments)
- [Refunds & payment actions (v3)](#refunds--payment-actions-v3)
- [Customers (v3)](#customers-v3)
- [Customer groups (v2) & subscribers](#customer-groups-v2--subscribers)
- [Recipes](#recipes)

## Orders (v2)

Orders remain v2: bare JSON, 204 on empty lists, dates in RFC 2822.

| Action | Endpoint |
|---|---|
| List | `GET /v2/orders` — filters: `status_id=`, `min_date_created=`, `max_date_created=`, `customer_id=`, `email=`, `min_total=`, `sort=date_created:desc` |
| Get / Update | `GET/PUT /v2/orders/{id}` |
| Create (manual/draft order) | `POST /v2/orders` |
| Count | `GET /v2/orders/count` |
| Archive | `DELETE /v2/orders/{id}` (archives, not hard delete) |
| **Delete all** | `DELETE /v2/orders` — archives everything; **confirm loudly** |
| Statuses | `GET /v2/order_statuses` — map `status_id` ↔ label first, don't hardcode |

Common status IDs (verify per store — labels are customizable): 0 Incomplete, 1 Pending, 2 Shipped, 3 Partially Shipped, 4 Refunded, 5 Cancelled, 7 Awaiting Payment, 9 Awaiting Shipment, 10 Completed, 11 Awaiting Fulfillment, 12 Manual Verification Required.

Update an order's status: `PUT /v2/orders/{id}` with `{"status_id": 2}`. Add staff notes via `"staff_notes"`, customer-visible message via `"customer_message"`.

Create requires: `billing_address` object and `products` array (`product_id`+`quantity`, or `name`+`quantity`+`price_inc_tax`/`price_ex_tax` for custom items). Set `"status_id": 0` while assembling if needed.

## Order sub-resources

All `GET /v2/orders/{id}/...`: `products` (line items — note each has its own `id` distinct from `product_id`), `shipping_addresses`, `coupons`, `taxes`, `messages`, `fees`, `consignments`, `shipping_quotes` (under a shipping address). Order metafields are v3: `GET/POST /v3/orders/{id}/metafields`, `GET/PUT/DELETE /v3/orders/{id}/metafields/{metafield_id}`; there's also a store-wide `GET /v3/orders/metafields` to query across all orders (filter by `key`, `key:in`, `namespace`, `date_created`, etc.) instead of looping per-order.

## Shipments

Creating a shipment is how you mark items shipped and attach tracking:

- `GET/POST /v2/orders/{id}/shipments`; `PUT/DELETE .../shipments/{sid}`; `GET .../shipments/count`
- Create body:

```json
{
  "order_address_id": 1,
  "tracking_number": "1Z...",
  "shipping_provider": "ups",        // ups|usps|fedex|upsready|upsonline|endicia|shipperhq|royalmail|auspost|canadapost|"" (custom, or "carrier_{id}" for a 3rd-party provider)
  "tracking_carrier": "",
  "items": [{"order_product_id": 15, "quantity": 2}]
}
```

`order_address_id` comes from `GET .../shipping_addresses`; `order_product_id` is the line item `id` from `GET .../products`. Omitting `items` isn't allowed — list every line being shipped. BigCommerce flips status to Shipped/Partially Shipped automatically.

## Refunds & payment actions (v3)

Always quote before refunding:

1. `POST /v3/orders/{id}/payment_actions/refund_quotes` — body is `{"items": [...]}` (or `{"tax_adjustment_amount": {...}}`). Each item's shape depends on `item_type`:
   - Quantity-bound — `item_type: PRODUCT|GIFT_WRAPPING`, `item_id` (order product ID), `quantity` (+ optional `adjustments` array for per-item deductions).
   - Amount-bound — `item_type: ORDER|SHIPPING|HANDLING|TAX|FEE`, `item_id`, `amount`. (`ORDER` skips tax recalculation — use it for a flat custom-amount refund.)
   Response gives totals + valid `payment_methods`.
2. `POST /v3/orders/{id}/payment_actions/refunds` — same `items` **plus required** `payments: [{"provider_id": ..., "amount": ..., "offline": false}]` from the quote's `payment_methods`. Both `items` and `payments` are required.
3. Inspect: `GET /v3/orders/{id}/payment_actions/refunds` (this order); store-wide `GET /v3/orders/payment_actions/refunds` (list) or `GET /v3/orders/payment_actions/refunds/{refund_id}` (single, across any order).

Capture/void authorized payments: `POST /v3/orders/{id}/payment_actions/capture` and `.../void` — **no request body**, they act on the full authorized amount for the order. Transactions: `GET /v3/orders/{id}/transactions`. **All money movement requires explicit user confirmation with amounts shown.**

## Customers (v3)

Array-based: every write takes an array, even for one record.

| Action | Endpoint |
|---|---|
| List | `GET /v3/customers` — filters: `email:in=`, `name:like=`, `customer_group_id:in=`, `date_created:min=`, `include=addresses,storecredit,attributes,formfields` |
| Create | `POST /v3/customers` — `[{"first_name","last_name","email", ...}]` |
| Update | `PUT /v3/customers` — `[{"id": 1, ...}]` |
| Delete | `DELETE /v3/customers?id:in=1,2` (**confirm**) |
| Addresses | `GET/POST/PUT/DELETE /v3/customers/addresses` (array style, filter `customer_id:in=`) |
| Attributes | `/v3/customers/attributes` (define) + `/v3/customers/attribute-values` (upsert per customer, `PUT`) |
| Form field values | `GET/PUT /v3/customers/form-field-values` |
| Metafields | `GET/POST/PUT/DELETE /v3/customers/{id}/metafields[/{metafield_id}]`, plus store-wide `GET/POST/PUT/DELETE /v3/customers/metafields` |
| Store credit | set via update: `"store_credit_amounts": [{"amount": 25.5}]` |

Address create requires `first_name`, `last_name`, `address1`, `city`, `country_code`, and (per schema) `state_or_province` + `postal_code`, plus `customer_id` when posting to the standalone `/v3/customers/addresses` endpoint (not needed when nesting `addresses` inside a customer create).

Passwords: set `"authentication": {"force_password_reset": true}` or `{"new_password": "..."}` on create/update — confirmed against the `customerAuthentication_PostPut` schema (`new_password` is write-only, never returned); never echo passwords back. To check a login without authenticating as the customer, use `POST /v3/customers/validate-credentials` (email/password in body) — it has extra rate limiting to prevent brute-force. To move customers between groups: `PUT /v3/customers` with `customer_group_id`. Multi-storefront access: omit `channel_ids` (or send `null`) for **global** login access — but that only works on channels with `allow_global_logins` enabled, which is on by default **only for the default storefront** (see `/v3/customers/settings/channels/{channel_id}`). On a store with multiple channels, a customer created without `channel_ids` may not be able to log in on the non-default storefronts unless global logins are enabled there too; to scope a customer to specific channels instead, pass a non-empty `channel_ids` array. `origin_channel_id` just records which channel's registration form created them.

## Customer groups (v2) & subscribers

- **Groups**: `GET/POST /v2/customer_groups`, `PUT/DELETE /v2/customer_groups/{id}`. Body: `{"name": "Wholesale", "is_default": false, "discount_rules": [{"type": "all"|"category"|"product", "method": "percent"|"fixed"|"price", "amount": 10, "category_id": ...}]}`. Groups are the hook for price lists and group-level discounts. Gotcha: a category discount rule created via the API always applies to "this category and its subcategories" — there's no field to restrict it to the category only (that toggle only exists in the control panel UI).
- **Subscribers** (newsletter list): `GET/POST/DELETE /v3/customers/subscribers` (bulk delete takes filters like `email`, `source`, `date_created`), `GET/PUT/DELETE .../subscribers/{id}`. Distinct from customers — a subscriber is just an email opt-in. **Unlike every other `/v3/customers/*` write, `POST /v3/customers/subscribers` takes a single object, not an array.** Body fields: `email`, `first_name`, `last_name`, `source` (`storefront`|`order`|`custom`), `order_id`, `channel_id`, `consents` (array of consent types like `marketing_newsletter`, `abandoned_cart` — an empty array means unsubscribed).
- **Wishlists**: `GET/POST /v3/wishlists` (create requires `customer_id`; optional `name`, `is_public`, `items: [{"product_id", "variant_id"}]`), `GET/PUT/DELETE /v3/wishlists/{id}`, `POST /v3/wishlists/{id}/items`, `DELETE /v3/wishlists/{id}/items/{item_id}`. List filters: `customer_id=`.

## Recipes

**Daily "ship these" list** — `GET /v2/orders?status_id=11&sort=date_created:asc` (Awaiting Fulfillment; confirm the store's ID via order_statuses), then per order pull `products` + `shipping_addresses`.

**Bulk status transition** — list orders with the source filter, show the user count + order IDs, then loop `PUT /v2/orders/{id}` `{"status_id": N}`. No batch endpoint exists for orders; respect rate limits on big sets.

**Find a customer's lifetime value** — `GET /v2/orders?customer_id=42` (paginate), sum `total_inc_tax`, exclude status 4/5 (Refunded/Cancelled) unless told otherwise.

**Import customers from CSV** — map columns to v3 customer objects, chunk into arrays of ≤10 per `POST /v3/customers` call, collect per-item errors from the response (it reports which array entries failed and why — usually duplicate email).
