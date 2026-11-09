# NewsFetcher

Fetch recent financial news through AkShare and return normalized items in `ServiceResult.data`. No API key or additional configuration is required.

## Methods

| Method | UseCase | Request |
|--------|---------|---------|
| `fetch_recent()` | `FetchRecentNewsUseCase` | `FetchRecentNewsInput` |
| `fetch_stock_news()` | `FetchStockNewsUseCase` | `FetchStockNewsInput` |

Both return `NewsOutput`.

## Request

The request and response models belong to the UseCases that own the actions; the service re-exports them as part of its public facade.

`FetchRecentNewsInput`:

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `sources` | no | all | Any of `cls`, `em`, `sina`, `ths`, `futu` |
| `keywords` | no | `[]` | Local case-insensitive substring filters over title, summary, and content |
| `keyword_match` | no | `any` | Match any keyword or require all keywords |
| `limit` | no | `null` | Optional total cap after filtering and deduplication; unset means no extra truncation |
| `deduplicate` | no | `true` | Exact normalized-text deduplication, not semantic event clustering |

`FetchStockNewsInput`:

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `symbol` | yes | — | Stock code or search keyword passed to `stock_news_em` |
| `limit` | no | `null` | Optional total cap |

`recent` is the provider's current latest page, not a fixed duration. At the time of writing, AkShare documents these upstream caps:

| Source | AkShare function | Upstream cap |
|--------|------------------|--------------|
| `cls` | `stock_info_global_cls` | 20 |
| `em` | `stock_info_global_em` | 200 |
| `sina` | `stock_info_global_sina` | 20 |
| `ths` | `stock_info_global_ths` | 20 |
| `futu` | `stock_info_global_futu` | 50 |

The actual time span varies with publication frequency. `fetch_stock_news` returns at most the latest 100 Eastmoney results and does not guarantee 30-day coverage. Neither mode accepts start/end dates or pagination.

## Response (`NewsOutput`)

| Field | Description |
|-------|-------------|
| `rows` | Returned count |
| `items` | Normalized news |
| `coverage` | Actual earliest/latest returned publication timestamps, not guaranteed coverage |
| `source_stats` | Per-source fetched, filtered, duplicate, and returned counts |
| `errors` | Per-source errors when some sources fail |

Each item contains `id`, `source`, optional `symbol`, `title`, `summary`, `content`, `url`, and `published_at`. Naive China-local timestamps are interpreted as Asia/Shanghai and returned in UTC. IDs are stable hashes of the canonical URL when available, otherwise of the normalized item metadata.

If at least one recent source succeeds, the call succeeds and reports other failures in `errors`. If every source fails, the call returns `all_sources_failed`. An empty result after filtering is successful.

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The request does not satisfy the request model (for example a missing `symbol`) |
| `all_sources_failed` | Every requested source failed |
| `news_source_unavailable` | A source timed out, is unreachable, or rate-limited |
| `news_source_failed` | A source failed for any other reason; per-source failures are listed in `errors` |

## Service example

```python
from src.services.news_fetcher import NewsFetcher

service = NewsFetcher()

result = await service.fetch_recent(
    {
        "sources": ["cls", "em"],
        "keywords": ["降息", "央行"],
        "keyword_match": "any",
    }
)

stock_result = await service.fetch_stock_news({"symbol": "603777", "limit": 50})
```

Live calls access external sites through AkShare. Upstream layout or availability changes can make an individual source fail.
