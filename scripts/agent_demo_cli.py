#!/usr/bin/env python3
"""Minimal agent CLI simulator for the agent_demo pipeline.

Reads the artifact produced by the previous stage, writes a short analysis
report, and exits successfully. This keeps the demo runnable in environments
where a full Agent CLI is not installed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent CLI simulator for agent_demo")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    data = json.loads(artifact_path.read_text(encoding="utf-8"))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    topic = data.get("topic", "unknown topic")
    rows = data.get("data", [])

    report = (
        f"# Agent Demo Analysis\n\n"
        f"## Task\n{args.task}\n\n"
        f"## Topic\n{topic}\n\n"
        f"## Observations\n"
        f"The generated dataset contains {len(rows)} signal row(s).\n\n"
        f"## Summary\n"
        f"<!-- summary: Analysis complete for '{topic}' with {len(rows)} signal row(s). -->\n"
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
