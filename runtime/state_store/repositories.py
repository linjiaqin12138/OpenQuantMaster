from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import ArtifactRef, CheckpointRecord, PipelineRun, RunStatus, StageRun, TriggerType


class PipelineRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, pipeline_name: str, trigger_type: TriggerType = TriggerType.manual) -> PipelineRun:
        run = PipelineRun(pipeline_name=pipeline_name, trigger_type=trigger_type)
        self._session.add(run)
        await self._session.flush()
        return run

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: RunStatus,
        finished_at: datetime | None = None,
    ) -> None:
        run = await self._session.get(PipelineRun, run_id)
        if run is None:
            raise ValueError(f"PipelineRun {run_id} not found")
        run.status = status
        if finished_at is not None:
            run.finished_at = finished_at
        else:
            run.finished_at = datetime.now(timezone.utc)

    async def get(self, run_id: uuid.UUID) -> PipelineRun | None:
        return await self._session.get(PipelineRun, run_id)


class StageRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        pipeline_run_id: uuid.UUID,
        stage_name: str,
        sequence: int,
        inputs_snapshot: dict[str, Any],
    ) -> StageRun:
        stage = StageRun(
            pipeline_run_id=pipeline_run_id,
            stage_name=stage_name,
            sequence=sequence,
            inputs_snapshot=inputs_snapshot,
        )
        self._session.add(stage)
        await self._session.flush()
        return stage

    async def update_status(
        self,
        stage_run_id: uuid.UUID,
        status: RunStatus,
        error_message: str | None = None,
        outputs_snapshot: dict[str, Any] | None = None,
    ) -> None:
        stage = await self._session.get(StageRun, stage_run_id)
        if stage is None:
            raise ValueError(f"StageRun {stage_run_id} not found")
        stage.status = status
        stage.finished_at = datetime.now(timezone.utc)
        if error_message is not None:
            stage.error_message = error_message
        if outputs_snapshot is not None:
            stage.outputs_snapshot = outputs_snapshot


class ArtifactRefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        pipeline_run_id: uuid.UUID,
        stage_run_id: uuid.UUID | None,
        name: str,
        mime_type: str,
        relative_path: str,
        sha256: str,
    ) -> ArtifactRef:
        ref = ArtifactRef(
            pipeline_run_id=pipeline_run_id,
            stage_run_id=stage_run_id,
            name=name,
            mime_type=mime_type,
            relative_path=relative_path,
            sha256=sha256,
        )
        self._session.add(ref)
        await self._session.flush()
        return ref


class CheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(self, pipeline_run_id: uuid.UUID, stage_name: str, snapshot_json: str) -> CheckpointRecord:
        record = CheckpointRecord(
            pipeline_run_id=pipeline_run_id,
            stage_name=stage_name,
            snapshot_json=snapshot_json,
        )
        self._session.add(record)
        await self._session.flush()
        return record
