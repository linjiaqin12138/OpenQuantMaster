from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import jsonschema
import structlog
import yaml
from pydantic import ValidationError

from runtime.config_loader import RuntimeConfig
from runtime.event_bus.memory_bus import MemoryEventBus
from runtime.state_store.database import StateStore
from runtime.state_store.models import ArtifactRef as ArtifactRefModel, RunStatus
from tools.base.tool_registry import ToolNotFoundError, ToolRegistry
from tools.base.tool_result import ArtifactRef as ArtifactRefData

from .checkpoint import CheckpointWriter
from .context import RunContext

logger = structlog.get_logger()


class PipelineRunnerError(Exception):
    pass


class PipelineRunner:
    def __init__(
        self,
        config: RuntimeConfig,
        store: StateStore,
        bus: MemoryEventBus,
        registry: ToolRegistry,
    ) -> None:
        self._config = config
        self._store = store
        self._bus = bus
        self._registry = registry
        self._pipelines_dir = Path("pipelines")
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

        try:
            for sequence, stage in enumerate(manifest["stages"]):
                await self._run_stage(run_id, sequence, stage, context, manifest_name=manifest["name"])
        except PipelineRunnerError:
            logger.warning("pipeline.run.failed", run_id=str(run_id), pipeline_name=manifest["name"])
            return run_id
        except Exception as exc:
            logger.exception("pipeline.run.failed", run_id=str(run_id))
            await self._store.update_pipeline_run_status(run_id, RunStatus.failed)
            await self._bus.publish(
                "pipeline.run.failed",
                {"pipeline_name": manifest["name"], "error": str(exc)},
                correlation_id=run_id,
            )
            return run_id

        await self._store.update_pipeline_run_status(run_id, RunStatus.completed)
        await self._bus.publish(
            "pipeline.run.completed",
            {"pipeline_name": manifest["name"], "run_id": str(run_id)},
            correlation_id=run_id,
        )
        return run_id

    def _load_manifest(self, pipeline_name: str) -> dict[str, Any]:
        path = self._pipelines_dir / f"{pipeline_name}.yaml"
        if not path.exists():
            raise PipelineRunnerError(f"Pipeline manifest not found: {path}")
        manifest = yaml.safe_load(path.read_text())
        if self._schema:
            jsonschema.validate(instance=manifest, schema=self._schema)
        return manifest

    async def _run_stage(
        self,
        run_id: uuid.UUID,
        sequence: int,
        stage: dict[str, Any],
        context: RunContext,
        manifest_name: str,
    ) -> None:
        stage_name = stage["name"]
        tool_name = stage["tool"]
        raw_inputs = stage.get("inputs", {})
        resolved_inputs = self._resolve_inputs(raw_inputs, context)

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
            await self._store.update_pipeline_run_status(run_id, RunStatus.failed)
            await self._bus.publish(
                "pipeline.run.failed",
                {"pipeline_name": manifest_name, "error": failure_error},
                correlation_id=run_id,
            )
            raise PipelineRunnerError(failure_error)

        # Persist artifacts
        artifact_models = []
        for artifact in result.artifacts:
            model = await self._persist_artifact(run_id, stage_run.id, stage_name, artifact)
            artifact_models.append(model)
            context.artifacts.append(artifact)

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
        resolved: dict[str, Any] = {}
        for key, value in raw_inputs.items():
            if isinstance(value, str) and value.startswith("$"):
                ref = value[1:]
                if "." in ref:
                    stage_name, field = ref.split(".", 1)
                    resolved[key] = context.outputs.get(stage_name, {}).get(field)
                else:
                    resolved[key] = context.inputs.get(ref)
            else:
                resolved[key] = value
        return resolved

    async def _persist_artifact(
        self,
        run_id: uuid.UUID,
        stage_run_id: uuid.UUID,
        stage_name: str,
        artifact: ArtifactRefData,
    ) -> ArtifactRefModel:
        artifact_dir = self._config.paths.artifacts / str(run_id) / stage_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        dest = artifact_dir / artifact.name
        if artifact.content is not None:
            dest.write_text(artifact.content, encoding="utf-8")
        elif not dest.exists():
            dest.write_text(f"# artifact {artifact.name}\n", encoding="utf-8")
        sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()
        relative_path = str(dest.relative_to(self._config.paths.artifacts))
        return await self._store.create_artifact_ref(
            pipeline_run_id=run_id,
            stage_run_id=stage_run_id,
            name=artifact.name,
            mime_type=artifact.mime_type,
            relative_path=relative_path,
            sha256=sha256,
        )
