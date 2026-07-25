from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from runtime.config_loader import RuntimeConfig
from tools.base.tool_result import ArtifactRef

logger = structlog.get_logger()


@dataclass
class VibeResult:
    success: bool
    data: dict[str, Any]
    artifacts: list[ArtifactRef]
    run_dir: str | None
    error: str | None


class VibeCapabilityError(RuntimeError):
    pass


class VibeBridge:
    """Unified bridge to Vibe-Trading.

    Transport is selected by ``config.vibe_trading.mode``:

    - ``cli``: spawn ``vibe-trading`` subcommands.
    - ``mcp``: talk to ``vibe-trading-mcp`` over stdio JSON-RPC.
    - ``http``: reserved for future use.
    """

    _READ_ONLY_BLOCKLIST = {"place_order", "cancel_order", "shell", "write_file"}

    def __init__(self, config: RuntimeConfig) -> None:
        self._cfg = config

    @property
    def mode(self) -> str:
        return self._cfg.vibe_trading.mode

    async def call(self, capability: str, inputs: dict[str, Any]) -> VibeResult:
        cfg = self._cfg.vibe_trading
        if capability not in cfg.allowed_capabilities:
            raise VibeCapabilityError(
                f"Capability '{capability}' is not in allowed_capabilities"
            )
        if cfg.read_only and capability in self._READ_ONLY_BLOCKLIST:
            raise VibeCapabilityError(
                f"Capability '{capability}' is blocked in read_only mode"
            )

        if self.mode == "cli":
            return await self._call_cli(capability, inputs)
        if self.mode == "mcp":
            return await self._call_mcp(capability, inputs)
        if self.mode == "http":
            return VibeResult(
                success=False,
                data={},
                artifacts=[],
                run_dir=None,
                error="HTTP mode is not implemented yet",
            )
        return VibeResult(
            success=False,
            data={},
            artifacts=[],
            run_dir=None,
            error=f"Unknown vibe_trading mode: {self.mode}",
        )

    # ------------------------------------------------------------------ CLI

    async def _call_cli(self, capability: str, inputs: dict[str, Any]) -> VibeResult:
        cfg = self._cfg.vibe_trading
        run_dir = inputs.get("run_dir")

        if run_dir:
            # Deterministic runner mode: no LLM, just replay an existing run dir.
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "backtest.runner", str(run_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return VibeResult(
                    success=False,
                    data={},
                    artifacts=[],
                    run_dir=None,
                    error=f"Vibe-Trading runner failed: {stderr.decode('utf-8')}",
                )
            artifacts = await self._collect_artifacts(Path(run_dir) / "artifacts")
            return VibeResult(
                success=True,
                data={},
                artifacts=artifacts,
                run_dir=str(run_dir),
                error=None,
            )

        args = self._build_cli_args(capability, inputs)
        cmd = [cfg.cli_path, *args]
        logger.info("vibe_bridge.cli_call", capability=capability, cmd=cmd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return VibeResult(
                success=False,
                data={},
                artifacts=[],
                run_dir=None,
                error=f"Vibe-Trading CLI failed: {stderr.decode('utf-8')}",
            )

        try:
            summary = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            return VibeResult(
                success=False,
                data={},
                artifacts=[],
                run_dir=None,
                error=f"Could not parse Vibe-Trading JSON output: {exc}",
            )

        run_dir = summary.get("run_dir")
        artifacts: list[ArtifactRef] = []
        if run_dir:
            artifacts = await self._collect_artifacts(Path(run_dir) / "artifacts")

        return VibeResult(
            success=True,
            data=summary,
            artifacts=artifacts,
            run_dir=run_dir,
            error=None,
        )

    def _build_cli_args(self, capability: str, inputs: dict[str, Any]) -> list[str]:
        if capability in {"backtest", "research"}:
            description = inputs.get("strategy_description") or inputs.get("prompt")
            if not description:
                raise VibeCapabilityError(
                    f"Capability '{capability}' requires 'strategy_description' or 'prompt'"
                )
            prompt = description
            if capability == "backtest":
                symbols = inputs.get("symbols", [])
                market = inputs.get("market", "")
                if symbols or market:
                    prompt += f" on {','.join(symbols)} ({market})"
            if inputs.get("start"):
                prompt += f" from {inputs['start']}"
            if inputs.get("end"):
                prompt += f" to {inputs['end']}"
            return ["run", "-p", prompt, "--json"]

        if capability == "alpha_bench":
            zoo = inputs.get("zoo")
            universe = inputs.get("universe")
            period = inputs.get("period")
            if not (zoo and universe and period):
                raise VibeCapabilityError(
                    "alpha_bench requires 'zoo', 'universe', and 'period'"
                )
            return [
                "alpha",
                "bench",
                "--zoo",
                str(zoo),
                "--universe",
                str(universe),
                "--period",
                str(period),
                "--json",
            ]

        raise VibeCapabilityError(
            f"Capability '{capability}' is not supported in CLI mode; use mcp mode"
        )

    # ------------------------------------------------------------------ MCP

    async def _call_mcp(self, capability: str, inputs: dict[str, Any]) -> VibeResult:
        from runtime.mcp_bridge import McpBridge

        cfg = self._cfg.vibe_trading
        bridge = await McpBridge.get_instance(cfg)
        tool_name = self._capability_to_mcp_tool(capability)
        result = await bridge.call_tool(tool_name, inputs)

        artifacts: list[ArtifactRef] = []
        run_dir = None
        if isinstance(result, dict):
            run_dir = result.get("run_dir")
            if run_dir:
                artifacts = await self._collect_artifacts(Path(run_dir) / "artifacts")

        return VibeResult(
            success=True,
            data=result if isinstance(result, dict) else {"result": result},
            artifacts=artifacts,
            run_dir=run_dir,
            error=None,
        )

    def _capability_to_mcp_tool(self, capability: str) -> str:
        aliases = {
            "backtest": "run_backtest",
            "research": "run_research_autopilot",
            "alpha_bench": "alpha_bench",
            "swarm": "run_swarm",
            "hypothesis": "create_hypothesis",
            "web_search": "web_search",
        }
        return aliases.get(capability, capability)

    # ------------------------------------------------------------------ helpers

    async def _collect_artifacts(self, artifacts_dir: Path) -> list[ArtifactRef]:
        expected = ("equity.csv", "trades.csv", "metrics.csv", "run_card.json")
        artifacts: list[ArtifactRef] = []
        for filename in expected:
            path = artifacts_dir / filename
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
        return artifacts
