from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult


class SignalScanInput(BaseModel):
    watch_dir: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    market: Literal["crypto", "a_share", "us_equity", "hk_equity"]


class SignalScanOutput(BaseModel):
    signals: list[dict[str, Any]]
    artifact: str


class SignalScanTool(BaseTool):
    name: ClassVar[str] = "signal_scan_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "research"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = SignalScanInput
    output_model: ClassVar[type[BaseModel]] = SignalScanOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        watch_dir = Path(inputs["watch_dir"])
        strategy_id = inputs["strategy_id"]
        default_market = inputs["market"]

        latest_run_dir = self._find_latest_run_dir(watch_dir, strategy_id)
        if latest_run_dir is None:
            output = self.output_model(signals=[], artifact="signals.json")
            return ToolResult(
                success=True,
                data=output.model_dump(),
                artifacts=[
                    ArtifactRef(
                        name="signals.json",
                        mime_type="application/json",
                        relative_path="signals.json",
                        sha256="",
                        content="[]",
                    )
                ],
            )

        signals = self._load_signals(latest_run_dir, strategy_id, default_market)
        content = json.dumps(signals, indent=2, default=str)
        output = self.output_model(signals=signals, artifact="signals.json")
        return ToolResult(
            success=True,
            data=output.model_dump(),
            artifacts=[
                ArtifactRef(
                    name="signals.json",
                    mime_type="application/json",
                    relative_path="signals.json",
                    sha256="",
                    content=content,
                )
            ],
        )

    def _find_latest_run_dir(self, watch_dir: Path, strategy_id: str) -> Path | None:
        candidates: list[tuple[Path, float]] = []
        if not watch_dir.exists():
            return None
        for entry in watch_dir.iterdir():
            if not entry.is_dir():
                continue
            run_card = entry / "run_card.json"
            if not run_card.exists():
                continue
            try:
                data = json.loads(run_card.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("strategy_id") != strategy_id:
                continue
            candidates.append((entry, entry.stat().st_mtime))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _load_signals(
        self, run_dir: Path, strategy_id: str, default_market: str
    ) -> list[dict[str, Any]]:
        signals_file = run_dir / "signals.json"
        if not signals_file.exists():
            return []
        try:
            raw = json.loads(signals_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        normalized = []
        for item in raw:
            signal = {
                "source": "vibe-trading",
                "strategy_id": item.get("strategy_id") or strategy_id,
                "symbol": item.get("symbol", ""),
                "market": item.get("market") or default_market,
                "interval": item.get("interval"),
                "side": item.get("side", "long"),
                "strength": float(item.get("strength", 0.0)),
                "generated_at": self._normalize_timestamp(
                    item.get("generated_at", datetime.now(timezone.utc).isoformat())
                ),
                "valid_until": item.get("valid_until"),
                "metadata": item.get("metadata", {}),
            }
            normalized.append(signal)
        return normalized

    def _normalize_timestamp(self, value: str | None) -> str:
        if not value:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        return value
