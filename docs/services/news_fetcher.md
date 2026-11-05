# NewsFetcher

Fetch recent financial news through AkShare and return normalized items in `ServiceResult.data`. No API key or additional configuration is required.

## Input (`NewsInput`)

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `mode` | no | `recent` | `recent` for multi-source flashes, or `stock_recent` for Eastmoney stock news |
| `sources` | recent: no; stock: forbidden | all | Any of `cls`, `em`, `sina`, `ths`, `futu` |
| `symbol` | stock only | `null` | Stock code or search keyword passed to `stock_news_em` |
| `keywords` | no | `[]` | Local case-insensitive substring filters over title, summary, and content |
| `keyword_match` | no | `any` | Match any keyword or require all keywords |
| `limit` | no | `null` | Optional total cap after filtering and deduplication; unset means no extra truncation |
| `deduplicate` | no | `true` | Exact normalized-text deduplication, not semantic event clustering |

`recent` is the provider's current latest page, not a fixed duration. At the time of writing, AkShare documents these upstream caps:

| Source | AkShare function | Upstream cap |
|--------|------------------|--------------|
| `cls` | `stock_info_global_cls` | 20 |
| `em` | `stock_info_global_em` | 200 |
| `sina` | `stock_info_global_sina` | 20 |
| `ths` | `stock_info_global_ths` | 20 |
| `futu` | `stock_info_global_futu` | 50 |

The actual time span varies with publication frequency. `stock_recent` returns at most the latest 100 Eastmoney results and does not guarantee 30-day coverage. Neither mode accepts start/end dates or pagination.

## Output (`NewsOutput`)

| Field | Description |
|-------|-------------|
| `mode` / `rows` / `items` | Query mode, returned count, and normalized news |
| `coverage` | Actual earliest/latest returned publication timestamps, not guaranteed coverage |
| `source_stats` | Per-source fetched, filtered, duplicate, and returned counts |
| `errors` | Per-source errors when some sources fail |

Each item contains `id`, `source`, optional `symbol`, `title`, `summary`, `content`, `url`, and `published_at`. Naive China-local timestamps are interpreted as Asia/Shanghai and returned in UTC. IDs are stable hashes of the canonical URL when available, otherwise of the normalized item metadata.

If at least one recent source succeeds, the call succeeds and reports other failures in `errors`. If every source fails, the call returns `all_sources_failed`. An empty result after filtering is successful.

## Service example

```python
from src.services.news_fetcher import NewsFetcher

result = await NewsFetcher().run(
    {
        "mode": "recent",
        "sources": ["cls", "em"],
        "keywords": ["降息", "央行"],
        "keyword_match": "any",
    }
)

stock_result = await NewsFetcher().run(
    {"mode": "stock_recent", "symbol": "603777", "limit": 50}
)
```

Live calls access external sites through AkShare. Upstream layout or availability changes can make an individual source fail.
