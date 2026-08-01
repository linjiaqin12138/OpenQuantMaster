# news_filter_tool

`news_filter_tool` fetches recent RSS news from the OpenAlice CLI gateway, scores each article with an LLM for relevance and black-swan / tail-risk potential, and bins the results into `high`, `medium_pending`, or `degraded`. Seen article IDs are persisted to `data/watch_state.json` so the same article is not re-scored across polling windows.

The scoring prompt is a configurable template: the built-in default targets short-term crypto trading, but you can override it per-tool in `config.yaml` or per-call via the `prompt_template` input (see below).

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

# Optional: per-tool LLM override. Fields not listed inherit from `llm` above.
tools:
  news_filter_tool:
    llm:
      model: gpt-4o-mini
      timeout: 15
```

`news_filter_tool` first looks for `tools.news_filter_tool.llm`. Any field explicitly set there overrides the global `llm` block; unset fields inherit the defaults. The `llm.api_key` can also be supplied via the environment variable `QUANT_AGENT_LLM__API_KEY`, and a tool-level override can be set via `QUANT_AGENT_TOOLS__NEWS_FILTER_TOOL__LLM__MODEL` (etc.).

### Prompt template

Articles are scored in batches: each LLM call receives `batch_size` articles and must return one rating per article. The scoring prompt is a template with two placeholders: `{count}` (number of articles in the batch) and `{articles}` (the rendered article blocks; each block carries the article `id`, title, time, source, link, and an 800-char content preview). Resolution order:

1. `prompt_template` input parameter (per pipeline run)
2. `tools.news_filter_tool.prompt.template` in `config.yaml` (or env `QUANT_AGENT_TOOLS__NEWS_FILTER_TOOL__PROMPT__TEMPLATE`)
3. Built-in default (crypto trading risk analyst)

A template using any other placeholder fails loudly with `success=False` before any LLM call. The template must keep instructing the model to return ONLY JSON of the form `{"ratings": [{"id": string, "score": float 0-1, "reason": string}, ...]}` with exactly one entry per article id — the response parser contract is fixed.

Example — retarget the filter to U.S. equities:

```yaml
tools:
  news_filter_tool:
    batch_size: 5
    prompt:
      template: |
        You are a U.S. equities risk analyst. Rate EACH article's relevance to
        short-term equity trading and its tail-risk potential. Return ONLY JSON:
        {"ratings": [{"id": string, "score": float 0-1, "reason": string}, ...]}
        with exactly one entry per article, keyed by the article id given below.

        Articles ({count}):
        {articles}
```

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
| `read_concurrency` | integer | no | `5` | Max concurrent `readRss` calls when enriching articles with full metadata. |
| `batch_size` | integer | no | `null` | Articles scored per LLM call (1-50). Overrides `tools.news_filter_tool.batch_size` in config (default `1`). |
| `prompt_template` | string | no | `null` | Per-call prompt template override. Placeholders: `{count}`, `{articles}`. Overrides the config template. |
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
      "link": "https://www.scmp.com/...full-untruncated-url...",
      "content": "Full article text...",
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
      "error": "LLM batch parse error: ..."
    }
  ],
  "artifact": "<run_id>/news_filter_tool/news_filter_result.json"
}
```

- `total` — total raw articles returned by OpenAlice.
- `new` — articles not already present in `data/watch_state.json`.
- `scored` — articles successfully parsed into a numeric score (excludes `degraded`).
- `high` — urgent / black-swan-like articles. Each entry includes the full `link` and `content` fetched via `readRss`.
- `medium_pending` — relevant but not immediately actionable articles.
- `degraded` — articles whose batch response could not be parsed, or that were missing from the LLM's `ratings` array.
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
- **Batch parse failure** — if a batch's response cannot be parsed, every article in that batch is placed in `degraded` and processing continues with the next batch. Articles missing from the `ratings` array are also placed in `degraded`.
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

### 3. Score 5 articles per LLM call

```bash
python -m runtime.cli tool news_filter_tool \
  --inputs '{"window_minutes": 120, "batch_size": 5}'
```

### 4. Run with a specific pipeline run ID

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

- The LLM is called once per batch of `batch_size` new articles (ceil(new / batch_size) calls per run). Each call is retried up to 3 times with exponential backoff.
- Before scoring, each new article is enriched via OpenAlice `readRss(id)` to obtain the full, untruncated `metadata` (including `link`) and article `content`. These calls run concurrently, bounded by `read_concurrency`.
- If `readRss` fails for an article, that article is skipped for the current run (it remains in `watch_state.json` and will be retried on the next poll).
- `response_format: {"type": "json_object"}` is used when the provider supports it.
- Scores are clamped to the `[0.0, 1.0]` range before binning.
