# eBay Sourcing Tools

Internal automated pipeline for custom marketplace analytics, stock level tracking, and
internal procurement sourcing. Integrates directly with the eBay REST Buy APIs.

> **Status: scaffold in progress.** The repository is public, so the API contract below is
> verified and committed, but the pipeline stages are still being built. See
> [Current state](#current-state) for what exists today.

## Why this exists

Three jobs run against the same eBay catalogue data:

| Job | What it does |
| --- | --- |
| **Marketplace analytics** | Price distribution, seller concentration and condition mix for a product category over time. |
| **Stock level tracking** | Poll watched listings and derive live supply levels, new listings and delistings between snapshots. |
| **Internal procurement sourcing** | Rank purchase candidates by landed cost, seller reliability and condition against a target price. |

## Verified API reference

The eBay Buy API details below were read from eBay's published Browse API v1.1.0 OpenAPI
specification and the official `eBay/ebay-oauth-nodejs-client` repository, not from memory.
They are recorded here because they are easy to get wrong and expensive to guess.

### Authentication

The client-credentials grant is the flow eBay documents for application (non-user) access
to the Browse and Item APIs.

| Property | Value |
| --- | --- |
| Token endpoint (production) | `POST https://api.ebay.com/identity/v1/oauth2/token` |
| Token endpoint (sandbox) | `POST https://api.sandbox.ebay.com/identity/v1/oauth2/token` |
| Authorization | `Basic base64(client_id:client_secret)` |
| Content type | `application/x-www-form-urlencoded` |
| Body | `grant_type=client_credentials&scope=<url-encoded space-separated scopes>` |
| Default scope | `https://api.ebay.com/oauth/api_scope` |
| Order API scope | `https://api.ebay.com/oauth/api_scope/buy.order` |

### Endpoints

The Browse and Item APIs **share** the same base path. The Get Item method is *not* under
`/buy/item/v1` — eBay's own spec gives its production URL as
`https://api.ebay.com/buy/browse/v1/item/`.

| Method | Path | Notes |
| --- | --- | --- |
| Search | `GET /buy/browse/v1/item_summary/search` | `q`, `limit`, `offset`, `sort`, `filter`, `fieldgroups`, `category_ids` |
| Get item | `GET /buy/browse/v1/item/{itemId}` | `fieldgroups=COMPACT` returns only the five fields needed to detect a change |
| Search by image | `POST /buy/browse/v1/item_summary/search_by_image` | Available in v1.1.0 |

Required request header on every call: `X-EBAY-C-MARKETPLACE-ID` (e.g. `EBAY_US`).

### Query parameter reference

**`limit`** — default `50`, maximum `200` per page. A result set caps at `10,000` items.

**`offset`** — `0` to `10,000` inclusive, default `0`.

**`sort`** — `price`, `-price`, `distance`, `newlyListed`. Default is Best Match.
Prefix with `-` for descending.

**`filter`** — comma separated. Ranges use `price:[10..50]`, multi-value uses
`conditions:{NEW|USED}`, and alternatives use `sellers:{sellerA|sellerB}`.
Supported filters: `buyingOptions`, `charityOnly`, `conditionIds`, `conditions`,
`deliveryCountry`, `deliveryOptions`, `deliveryPostalCode`, `excludeCategoryIds`,
`excludeSellers`, `guaranteedDeliveryInDays`, `itemEndDate`, `itemLocationCountry`,
`itemStartDate`, `paymentMethods`, `pickupCountry`, `pickupPostalCode`, `pickupRadius`,
`pickupRadiusUnit`, `price`, `priceCurrency`, `qualifiedPrograms`, `maxDeliveryCost`
(free shipping), `returnsAccepted`, `sellerAccountTypes`, `sellers`.

**`fieldgroups`** — `MATCHING_ITEMS` (default), `ASPECT_REFINEMENTS`,
`BUYING_OPTION_REFINEMENTS`, `CATEGORY_REFINEMENTS`, `CONDITION_REFINEMENTS`, `EXTENDED`.
For Get Item: `COMPACT` or `PRODUCT` (not both).

### Response shapes

`SearchPagedCollection` carries `itemSummaries`, `total`, `limit`, `offset`, `next`, `prev`,
`href`, `warnings`, `autoCorrections` and `refinement`.

`ItemSummary` includes `itemId`, `title`, `price`, `itemWebUrl`, `itemHref`, `condition`,
`conditionId`, `seller`, `image`, `itemLocation`, `shippingOptions`, `marketingPrice`,
`categories`, `buyingOptions`, `thumbnailImages` and `additionalImages`.

`Item` (full record) adds `description`, `itemCreationDate`, `itemEndDate`,
`estimatedAvailabilities`, `quantityLimitPerBuyer`, `lotSize`, `categoryId`, `categoryPath`,
`brand`, `mpn`, `gtin`, `taxes` and `returnTerms`.

Monetary values arrive as **decimal strings** under `ConvertedAmount`
(`value`, `currency`, `convertedFromValue`, `convertedFromCurrency`) and must be parsed as
decimals, never floats.

## Current state

| Module | Status |
| --- | --- |
| `src/ebay_sourcing/errors.py` | **Done** — exception hierarchy plus eBay error-body parsing. |
| `src/ebay_sourcing/config.py` | **Done** — environment settings, watch definitions, TOML watchlist loader, eBay filter builder. |
| `src/ebay_sourcing/models.py` | Next — typed, defensive parsers for every documented response shape. |
| `src/ebay_sourcing/client.py` | Planned — OAuth token handling, retry and rate-limit policy, Browse and Item calls. |
| `src/ebay_sourcing/analytics.py` | Planned — price, seller and condition statistics. |
| `src/ebay_sourcing/inventory.py` | Planned — stock level derivation. |
| `src/ebay_sourcing/procurement.py` | Planned — candidate ranking. |
| `src/ebay_sourcing/storage.py` | Planned — SQLite persistence. |
| `src/ebay_sourcing/cli.py` | Planned — command line entry point. |

## Setup

The eBay Buy APIs require an approved **eBay Partner** account. Create an app in the
[eBay Developer Program](https://developer.ebay.com/my/keys) and grant it the
`https://api.ebay.com/oauth/api_scope` scope.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Credentials are read from the environment only. Copy `.env.example` to `.env` as a
starting point and export the values before running anything:

```bash
export EBAY_CLIENT_ID="your-app-id"
export EBAY_CLIENT_SECRET="your-cert-id"
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `EBAY_CLIENT_ID` | — | Required. eBay app client ID. |
| `EBAY_CLIENT_SECRET` | — | Required. eBay app cert ID. |
| `EBAY_MARKETPLACE_ID` | `EBAY_US` | Marketplace used for every call. |
| `EBAY_ENVIRONMENT` | `production` | `production` or `sandbox`. |
| `EBAY_SOURCING_DB` | `data/ebay_sourcing.db` | SQLite database location. |
| `EBAY_SCOPES` | `https://api.ebay.com/oauth/api_scope` | Space-separated OAuth scopes. |
| `EBAY_RATE_LIMIT_PER_MINUTE` | `60` | Client-side request ceiling. |
| `EBAY_REQUEST_TIMEOUT` | `30` | Per-request timeout in seconds. |
| `EBAY_MAX_RETRIES` | `4` | Retry attempts for transient failures. |

### Security

**This repository is public.** Never commit credentials, `.env` files, OAuth tokens or
database files. `.env` and `data/` are gitignored. In CI, credentials belong in GitHub
Actions secrets and are passed to the job as environment variables.

## Licence

MIT — see [LICENSE](LICENSE).
