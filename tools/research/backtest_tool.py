from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult


class BacktestInput(BaseModel):
    strategy_description: str | None = Field(default=None, min_length=1)
    run_dir: str | None = Field(default=None, min_length=1)
    market: Literal["crypto", "a_share", "us_equity", "hk_equity"]
    symbols: list[str] = Field(..., min_length=1)
    start: str | None = None
    end: str | None = None
    mode: Literal["cli", "mcp", "http"] | None = None


class BacktestOutput(BaseModel):
    run_id: str
    metrics_artifact: str
    equity_artifact: str
    trades_artifact: str
    run_card_artifact: str
    sharpe: float | None = None
    max_drawdown_pct: float | None = None
    total_return_pct: float | None = None


class BacktestTool(BaseTool):
    name: ClassVar[str] = "backtest_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "research"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = BacktestInput
    output_model: ClassVar[type[BaseModel]] = BacktestOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        from runtime.config_loader import load_config

        cfg = load_config()
        mode = inputs.get("mode") or cfg.vibe_trading.mode
        run_id = str(uuid.uuid4())

        if mode == "cli":
            output_dir = await self._call_cli(cfg, inputs, run_id)
        elif mode == "http":
            output_dir = await self._call_http(cfg, inputs, run_id)
        elif mode == "mcp":
            output_dir = await self._call_mcp(cfg, inputs, run_id)
        else:
            return ToolResult(success=False, error=f"Unsupported vibe_trading mode: {mode}")

        artifacts = await self._collect_artifacts(output_dir)

        metrics = await self._read_run_card(output_dir)
        output = self.output_model(
            run_id=run_id,
            metrics_artifact="metrics.csv",
            equity_artifact="equity.csv",
            trades_artifact="trades.csv",
            run_card_artifact="run_card.json",
            sharpe=metrics.get("sharpe"),
            max_drawdown_pct=metrics.get("max_drawdown_pct"),
            total_return_pct=metrics.get("total_return_pct"),
        )
        return ToolResult(success=True, data=output.model_dump(), artifacts=artifacts)

    async def _call_cli(self, cfg: Any, inputs: dict[str, Any], run_id: str) -> Path:
        run_dir = inputs.get("run_dir")
        if run_dir:
            return Path(run_dir)

        description = inputs.get("strategy_description")
        if not description:
            raise ValueError("strategy_description or run_dir is required")

        tmpdir = Path(tempfile.gettempdir()) / f"vibe_backtest_{run_id}"
        tmpdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            cfg.vibe_trading.cli_path,
            "run",
            "--description", description,
            "--market", inputs["market"],
            "--symbols", ",".join(inputs["symbols"]),
            "--output-dir", str(tmpdir),
        ]
        if inputs.get("start"):
            cmd.extend(["--start", inputs["start"]])
        if inputs.get("end"):
            cmd.extend(["--end", inputs["end"]])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(tmpdir),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Vibe-Trading CLI failed: {stderr.decode('utf-8')}\n"
                f"stdout: {stdout.decode('utf-8')}"
            )
        return tmpdir

    async def _call_http(self, cfg: Any, inputs: dict[str, Any], run_id: str) -> Path:
        raise NotImplementedError("HTTP Vibe-Trading mode is not implemented in Milestone 2")

    async def _call_mcp(self, cfg: Any, inputs: dict[str, Any], run_id: str) -> Path:
        raise NotImplementedError("MCP Vibe-Trading mode is not implemented in Milestone 2")

    async def _collect_artifacts(self, output_dir: Path) -> list[ArtifactRef]:
        expected = ("equity.csv", "trades.csv", "metrics.csv", "run_card.json")
        artifacts = []
        for filename in expected:
            path = output_dir / filename
            if not await asyncio.to_thread(path.exists):
                continue
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            artifacts.append(
                ArtifactRef(
                    name=filename,
                    mime_type="application/json" if filename.endswith(".json") else "text/csv",
                    relative_path=filename,
                    sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    content=content,
                )
            )
        if not artifacts:
            raise RuntimeError(
                f"No artifacts found in backtest output dir: {output_dir} "
                f"(expected any of: {', '.join(expected)})"
            )
        return artifacts

    async def _read_run_card(self, output_dir: Path) -> dict[str, Any]:
        path = output_dir / "run_card.json"
        if not await asyncio.to_thread(path.exists):
            return {}
        try:
            text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in run_card {path}: {exc}") from exc
