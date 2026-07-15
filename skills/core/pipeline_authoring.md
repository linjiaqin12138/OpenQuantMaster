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
- M1 supports only `on_failure: stop`.
