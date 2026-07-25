from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from runtime.config_loader import load_config
from runtime.vibe_bridge import VibeBridge, VibeCapabilityError
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult


class VibeToolInput(BaseModel):
    capability: str = Field(
        ...,
        description=(
            "Vibe-Trading capability to invoke. In CLI mode use built-in aliases "
            "(backtest, research, alpha_bench); in MCP mode this can also be the "
            "raw MCP tool name (e.g. run_backtest, web_search)."
        ),
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Capability-specific arguments passed to Vibe-Trading.",
    )
    mode: Literal["cli", "mcp", "http"] | None = Field(
        default=None,
        description="Override vibe_trading.mode from config.yaml.",
    )
    timeout_sec: int | None = Field(default=None, ge=1)


class VibeToolOutput(BaseModel):
    success: bool
    capability: str
    mode: str
    run_dir: str | None
    data: dict[str, Any]


class VibeTool(BaseTool):
    name: ClassVar[str] = "vibe_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "vibe"
    input_model: ClassVar[type[BaseModel]] = VibeToolInput
    output_model: ClassVar[type[BaseModel]] = VibeToolOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        cfg = load_config()
        capability = inputs["capability"]
        tool_inputs = inputs.get("inputs", {})
        mode = inputs.get("mode") or cfg.vibe_trading.mode

        # Temporarily override mode for this call
        original_mode = cfg.vibe_trading.mode
        if mode != original_mode:
            cfg.vibe_trading.mode = mode

        bridge = VibeBridge(cfg)
        timeout = inputs.get("timeout_sec") or 300

        try:
            result = await asyncio.wait_for(
                bridge.call(capability, tool_inputs),
                timeout=timeout,
            )
        except VibeCapabilityError as exc:
            return ToolResult(success=False, data={}, error=str(exc))
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                data={},
                error=f"Vibe-Trading capability '{capability}' timed out after {timeout}s",
            )
        finally:
            cfg.vibe_trading.mode = original_mode

        if not result.success:
            return ToolResult(
                success=False,
                data={},
                error=result.error or "Vibe-Trading call failed",
            )

        output = self.output_model(
            success=True,
            capability=capability,
            mode=mode,
            run_dir=result.run_dir,
            data=result.data,
        )
        return ToolResult(
            success=True,
            data=output.model_dump(),
            artifacts=result.artifacts,
        )
