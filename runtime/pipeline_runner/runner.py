from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import structlog
import yaml
from pydantic import ValidationError

from runtime.agent_gateway.agent_driver import AgentDriver
from runtime.config_loader import RuntimeConfig
from runtime.event_bus.memory_bus import MemoryEventBus
from runtime.notifier.composite import CompositeNotifier
from runtime.state_store.database import StateStore
from runtime.state_store.models import ArtifactRef as ArtifactRefModel, MarketType, RunStatus, SignalSide
from tools.base.tool_registry import ToolNotFoundError, ToolRegistry
from tools.base.tool_result import ArtifactRef as ArtifactRefData

from .checkpoint import CheckpointWriter
from .context import RunContext

logger = structlog.get_logger()

DEFAULT_RETRIES = 2


class PipelineRunnerError(Exception):
    pass


class PipelineRunner:
    """Prefect-backed pipeline engine. Each stage is compiled to a dynamically
    created Prefect task (named after the stage) and chained sequentially into
    a flow. Runs in Prefect's ephemeral mode; no server required."""
    def __init__(
        self,
        config: RuntimeConfig,
        store: StateStore,
        bus: MemoryEventBus,
        registry: ToolRegistry,
        agent_driver: AgentDriver | None = None,
        notifier: CompositeNotifier | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._bus = bus
        self._registry = registry
        self._agent_driver = agent_driver
        self._notifier = notifier
        self._pipelines_dir = config.paths.pipelines
        self._schema = self._load_schema()
        self._checkpoint = CheckpointWriter(store)

    def _load_schema(self) -> dict[str, Any]:
        schema_path = Path("schemas") / "pipeline_manifest.schema.json"
        if schema_path.exists():
            return json.loads(schema_path.read_text())
        return {}

    async def run_pipeline(
        self,
        pipeline_name: str,
        inputs: dict[str, Any] | None = None,
        run_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        inputs = inputs or {}
        try:
            manifest = self._load_manifest(pipeline_name)
        except Exception as exc:
            run = await self._store.create_pipeline_run(pipeline_name=pipeline_name, run_id=run_id)
            await self._store.update_pipeline_run_status(run.id, RunStatus.failed)
            await self._bus.publish(
                "pipeline.run.failed",
                {"pipeline_name": pipeline_name, "error": str(exc)},
                correlation_id=run.id,
            )
            return run.id

        run = await self._store.create_pipeline_run(pipeline_name=manifest["name"], run_id=run_id)
        run_id = run.id
        context = RunContext(pipeline_run_id=run_id, inputs=inputs)

        await self._bus.publish(
            "pipeline.run.started",
            {"pipeline_name": manifest["name"], "run_id": str(run_id)},
            correlation_id=run_id,
        )

        pipeline_flow = self._build_flow(manifest, run_id, context)
        try:
            await pipeline_flow()
        except Exception as exc:
            logger.warning("pipeline.run.failed", run_id=str(run_id), pipeline_name=manifest["name"])
            await self._fail_run(run_id, manifest["name"], str(exc))
            return run_id

        await self._store.update_pipeline_run_status(run_id, RunStatus.completed)
        await self._bus.publish(
            "pipeline.run.completed",
            {"pipeline_name": manifest["name"], "run_id": str(run_id)},
            correlation_id=run_id,
        )
        return run_id

    def _build_flow(self, manifest: dict[str, Any], run_id: uuid.UUID, context: RunContext):
        from prefect import flow

        stage_tasks = [
            (sequence, stage, self._build_stage_task(stage))
            for sequence, stage in enumerate(manifest["stages"])
        ]

        @flow(name=f"pipeline:{manifest['name']}")
        async def _pipeline_flow() -> None:
            for sequence, stage, stage_task in stage_tasks:
                await stage_task(run_id, sequence, stage, context)

        return _pipeline_flow

    def _build_stage_task(self, stage: dict[str, Any]):
        from prefect import task

        async def _stage_task(
            run_id: uuid.UUID,
            sequence: int,
            stage: dict[str, Any],
            context: RunContext,
            _runner: PipelineRunner = self,
        ) -> None:
            await _runner._execute_stage(run_id, sequence, stage, context)

        options: dict[str, Any] = {"name": stage["name"]}
        if stage.get("on_failure") == "retry":
            options["retries"] = stage.get("retries", DEFAULT_RETRIES)
            options["retry_delay_seconds"] = stage.get("retry_delay_sec", 0)
        if stage.get("timeout_sec") is not None:
            options["timeout_seconds"] = stage["timeout_sec"]
        return task(**options)(_stage_task)

    def _load_manifest(self, pipeline_name: str) -> dict[str, Any]:
        path = self._pipelines_dir / f"{pipeline_name}.yaml"
        if not path.exists():
            raise PipelineRunnerError(f"Pipeline manifest not found: {path}")
        manifest = yaml.safe_load(path.read_text())
        if self._schema:
            jsonschema.validate(instance=manifest, schema=self._schema)
        return manifest

    async def _fail_run(self, run_id: uuid.UUID, manifest_name: str, error: str) -> None:
        await self._store.update_pipeline_run_status(run_id, RunStatus.failed)
        await self._bus.publish(
            "pipeline.run.failed",
            {"pipeline_name": manifest_name, "error": error},
            correlation_id=run_id,
        )

    async def _execute_stage(
        self,
        run_id: uuid.UUID,
        sequence: int,
        stage: dict[str, Any],
        context: RunContext,
    ) -> None:
        stage_name = stage["name"]
        tool_name = stage["tool"]
        raw_inputs = stage.get("inputs", {})
        resolved_inputs = self._resolve_inputs(raw_inputs, context)
        context.stage_inputs[stage_name] = resolved_inputs

        stage_run = await self._store.create_stage_run(
            pipeline_run_id=run_id,
            stage_name=stage_name,
            sequence=sequence,
            inputs_snapshot=resolved_inputs,
        )
        await self._bus.publish(
            "stage.run.started",
            {"stage_name": stage_name, "sequence": sequence},
            correlation_id=run_id,
        )
        await self._bus.publish(
            "tool.call.started",
            {"tool": tool_name, "stage_name": stage_name},
            correlation_id=run_id,
        )

        try:
            tool = self._registry.get(tool_name)
            if "pipeline_run_id" in tool.input_model.model_fields:
                resolved_inputs["pipeline_run_id"] = str(run_id)
            tool.input_model(**resolved_inputs)
            result = await tool.execute(resolved_inputs)
            if not result.success:
                error = result.error or "Tool returned failure"
            else:
                tool.output_model(**result.data)
        except ToolNotFoundError as exc:
            result = None
            error = str(exc)
        except ValidationError as exc:
            result = None
            error = f"Validation failed: {exc}"
        except Exception as exc:
            result = None
            error = f"Tool execution failed: {exc}"

        if result is None or not result.success:
            failure_error = error if result is None else (result.error or "Unknown tool error")
            await self._store.update_stage_run_status(
                stage_run.id,
                RunStatus.failed,
                error_message=failure_error,
            )
            await self._bus.publish(
                "tool.call.failed",
                {"tool": tool_name, "stage_name": stage_name, "error": failure_error},
                correlation_id=run_id,
            )
            await self._bus.publish(
                "stage.run.failed",
                {"stage_name": stage_name, "error": failure_error},
                correlation_id=run_id,
            )
            raise PipelineRunnerError(failure_error)

        # Persist artifacts
        artifact_models = []
        for artifact in result.artifacts:
            model = await self._persist_artifact(run_id, stage_run.id, stage_name, artifact)
            artifact_models.append(model)
            context.artifacts.append(artifact)

        if "signals" in result.data and isinstance(result.data["signals"], list):
            await self._persist_signals(run_id, stage_run.id, result.data["signals"])

        context.outputs[stage_name] = result.data
        context.metadata[stage_name] = {
            "cost_usd": result.cost_usd,
            "duration_seconds": result.duration_seconds,
        }

        outputs_snapshot = {
            "data": result.data,
            "artifacts": [a.model_dump() for a in result.artifacts],
        }
        await self._store.update_stage_run_status(
            stage_run.id,
            RunStatus.completed,
            outputs_snapshot=outputs_snapshot,
        )
        await self._bus.publish(
            "tool.call.completed",
            {"tool": tool_name, "stage_name": stage_name, "cost_usd": result.cost_usd},
            correlation_id=run_id,
        )
        await self._bus.publish(
            "stage.run.completed",
            {"stage_name": stage_name, "sequence": sequence},
            correlation_id=run_id,
        )
        await self._checkpoint.write(stage_name, context)

    def _resolve_inputs(self, raw_inputs: dict[str, Any], context: RunContext) -> dict[str, Any]:
        def walk(source: Any, path: list[str]) -> Any:
            current = source
            for part in path:
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return current

        def resolve_ref(ref: str) -> Any:
            parts = ref.split(".")
            if parts[0] == "inputs":
                return walk(context.inputs, parts[1:])
            if len(parts) < 3 or parts[1] not in ("in", "out"):
                return None
            stage_name, kind, path = parts[0], parts[1], parts[2:]
            source = context.stage_inputs if kind == "in" else context.outputs
            return walk(source.get(stage_name), path)

        def resolve(value: Any) -> Any:
            if isinstance(value, str) and value.startswith("$"):
                return resolve_ref(value[1:])
            if isinstance(value, dict):
                return {k: resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            return value

        return {key: resolve(value) for key, value in raw_inputs.items()}

    async def _persist_artifact(
        self,
        run_id: uuid.UUID,
        stage_run_id: uuid.UUID,
        stage_name: str,
        artifact: ArtifactRefData,
    ) -> ArtifactRefModel:
        artifact_dir = self._config.paths.artifacts / str(run_id) / stage_name
        await asyncio.to_thread(artifact_dir.mkdir, parents=True, exist_ok=True)
        dest = artifact_dir / artifact.name
        if artifact.content is not None:
            await asyncio.to_thread(dest.write_text, artifact.content, encoding="utf-8")
        elif not await asyncio.to_thread(dest.exists):
            await asyncio.to_thread(dest.write_text, f"# artifact {artifact.name}\n", encoding="utf-8")
        content_bytes = await asyncio.to_thread(dest.read_bytes)
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        relative_path = str(dest.relative_to(self._config.paths.artifacts))
        return await self._store.create_artifact_ref(
            pipeline_run_id=run_id,
            stage_run_id=stage_run_id,
            name=artifact.name,
            mime_type=artifact.mime_type,
            relative_path=relative_path,
            sha256=sha256,
        )

    async def _persist_signals(
        self,
        run_id: uuid.UUID,
        stage_run_id: uuid.UUID,
        signals: list[dict[str, Any]],
    ) -> None:
        for raw in signals:
            try:
                market = MarketType(raw.get("market", "crypto"))
                side = SignalSide(raw.get("side", "long"))
                triggered_at = self._parse_signal_timestamp(raw.get("generated_at"))
                valid_until = self._parse_signal_timestamp(raw.get("valid_until")) if raw.get("valid_until") else None
                await self._store.create_signal(
                    source=raw.get("source", "internal"),
                    strategy_id=raw.get("strategy_id", ""),
                    symbol=raw.get("symbol", ""),
                    market=market,
                    side=side,
                    strength=float(raw.get("strength", 0.0)),
                    triggered_at=triggered_at,
                    valid_until=valid_until,
                    payload=raw.get("metadata", {}),
                )
            except Exception as exc:
                logger.warning(
                    "signal.persist.failed",
                    run_id=str(run_id),
                    stage_run_id=str(stage_run_id),
                    error=str(exc),
                )

    def _parse_signal_timestamp(self, value: str | int | float | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
