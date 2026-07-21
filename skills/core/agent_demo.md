# agent_demo

## Goal
Read the data artifact from the previous stage and write a short analysis report.

## Tools you can use
- `demo_data_tool` (already ran in stage 1; read its artifact)
- `notify_tool(subject, body, channels)` — send the summary to PushPlus

## Inputs
- Pipeline run id: `{pipeline_run_id}`
- Previous stage artifact: `artifacts/{pipeline_run_id}/generate_data/demo_data.json`
- Output directory: `artifacts/{pipeline_run_id}/agent_analyze/`

## Output
Write a report to `artifacts/{pipeline_run_id}/agent_analyze/report.md` with:
1. A brief summary of the demo data.
2. Your interpretation.
3. A one-sentence notification summary.

Then call `notify_tool` with subject "Agent Demo Report", body set to your one-sentence summary, and channels `["pushplus"]`.

## Constraints
- Do not execute trades or call any unregistered tools.
