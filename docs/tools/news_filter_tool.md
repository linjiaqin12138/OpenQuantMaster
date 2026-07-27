# news_filter_tool

`news_filter_tool` fetches recent RSS news from the OpenAlice CLI gateway, scores each article with an LLM for relevance to short-term crypto trading and black-swan / tail-risk potential, and bins the results into `high`, `medium_pending`, or `degraded`. Seen article IDs are persisted to `data/watch_state.json` so the same article is not re-scored across polling windows.

## Dependencies

- `httpx` — async HTTP client for the OpenAlice gateway.
- `litellm` — unified async LLM completion (`litellm.acompletion`).
- `tenacity` — retries around the LLM call.
- `structlog`, `pydantic` — already part of the runtime.

## Configuration

Add the following sections to `config.yaml` (defaults are provided):

```yaml
openalice:
  workspace_id: auto-quant-clear-willow-field
  cli_gateway_url: http://127.0.0.1:47332
  export: data

llm:
  provider: openai
  model: gpt-4o-mini
  api_key: ""          # or set env var QUANT_AGENT_LLM__API_KEY
  api_base: ""         # optional custom endpoint
  timeout: 30
```

The `llm.api_key` can also be supplied via the environment variable `QUANT_AGENT_LLM__API_KEY` thanks to `pydantic-settings` nested env overrides.

Supported model strings include:

- `gpt-4o-mini`
- `anthropic/claude-3-5-sonnet-20241022`
- Any other provider supported by `litellm`.

## Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `window_minutes` | integer | no | `60` | Look-back window from now. |
| `limit` | integer | no | `100` | Max articles to fetch from OpenAlice. |
| `min_score` | float | no | `0.6` | Articles with `score >= min_score` are classified as `high`. |
| `medium_score` | float | no | `0.3` | Articles with `medium_score <= score < min_score` are classified as `medium_pending`. Must be `<= min_score`. |
| `pipeline_run_id` | string | no | `null` | Pipeline run ID used to organize the output artifact. |

## Output structure

On success, `ToolResult.data` contains:

```json
{
  "total": 3,
  "new": 3,
  "scored": 2,
  "high": [
    {
      "id": "770",
      "time": "2026-07-26T00:00:14.000Z",
      "title": "...",
      "source": "scmp-business",
      "link": "...",
      "score": 0.85,
      "reason": "Regulatory approval is bullish for crypto markets."
    }
  ],
  "medium_pending": [...],
  "degraded": [
    {
      "id": "772",
      "time": "2026-07-26T01:00:00.000Z",
      "title": "...",
      "source": "...",
      "link": "...",
      "score": null,
      "reason": null,
      "error": "LLM parse error: ..."
    }
  ],
  "artifact": "<run_id>/news_filter_tool/news_filter_result.json"
}
```

- `total` — total raw articles returned by OpenAlice.
- `new` — articles not already present in `data/watch_state.json`.
- `scored` — articles successfully parsed into a numeric score (excludes `degraded`).
- `high` — urgent / black-swan-like articles.
- `medium_pending` — relevant but not immediately actionable articles.
- `degraded` — articles whose LLM response could not be parsed.
- `artifact` — relative path to the persisted JSON artifact.

## State file

`data/watch_state.json` is merged, not overwritten:

```json
{
  "news_filter": {
    "seen_ids": ["770", "771"],
    "last_run_at": "2026-07-27T13:00:00Z"
  }
}
```

Other top-level keys in the file are preserved so the same file can be shared with `event_trigger_tool` later.

## Error handling

- **OpenAlice gateway failure** — returns `ToolResult(success=False, error=...)`.
- **LLM failure after retries** — best-effort PushPlus notification, then returns `ToolResult(success=False, error=...)`.
- **Individual article parse failure** — article is placed in `degraded` and processing continues.
- **No keyword fallback** — the tool never falls back to simple keyword matching.

## CLI usage examples

### 1. Poll the last 12 hours

```bash
python -m runtime.cli tool news_filter_tool --inputs '{"window_minutes": 720}'
```

### 2. Adjust thresholds and limit

```bash
python -m runtime.cli tool news_filter_tool \
  --inputs '{"window_minutes": 120, "limit": 50, "min_score": 0.7, "medium_score": 0.4}'
```

### 3. Run with a specific pipeline run ID

```bash
python -m runtime.cli tool news_filter_tool \
  --inputs '{"window_minutes": 60, "pipeline_run_id": "run-20260727-001"}'
```

## Pipeline YAML example

```yaml
name: crypto_news_filter

trigger:
  type: cron
  cron: "0 * * * *"

stages:
  - filter_news:
      tool: news_filter_tool
      inputs:
        window_minutes: 60
        limit: 100
        min_score: 0.6
        medium_score: 0.3
```

## Notes

- The LLM is called once per new article. Each call is retried up to 3 times with exponential backoff.
- `response_format: {"type": "json_object"}` is used when the provider supports it.
- Scores are clamped to the `[0.0, 1.0]` range before binning.
