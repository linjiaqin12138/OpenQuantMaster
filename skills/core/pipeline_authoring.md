# Pipeline Authoring

## Manifest format

```yaml
name: hello_pipeline
version: "1.0"
description: Optional description
stages:
  - name: stage_name
    tool: echo_tool
    inputs:
      message: "Hello"
      repeat: 1
    on_failure: stop
```

## Rules

- Stage `name` must be unique within the pipeline.
- `tool` must match a tool discovered by `ToolRegistry`.
- `inputs` are validated against the tool's `input_schema`.
- Pipelines run on a Prefect-backed engine (ephemeral mode, no server needed);
  each stage becomes a Prefect task.
- `on_failure: stop` (the default) fails the whole run on stage failure.
  `on_failure: retry` maps to Prefect task retries using optional stage keys
  `retries` (default 2) and `retry_delay_sec` (default 0). A stage-level
  `timeout_sec` maps to the Prefect task timeout. `skip`/`escalate` are not
  implemented.
