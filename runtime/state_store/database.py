from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .models import Base, RunStatus, TriggerType
from .repositories import (
    ArtifactRefRepository,
    CheckpointRepository,
    PipelineRunRepository,
    StageRunRepository,
)


class StateStore:
    def __init__(self, database_url: str, artifacts_path: Path | str) -> None:
        self.database_url = database_url
        self.artifacts_path = Path(artifacts_path)
        self._engine = create_async_engine(database_url, future=True, echo=False)
        self._session_factory: sessionmaker = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init(self) -> None:
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()

    async def create_pipeline_run(
        self, pipeline_name: str, trigger_type: TriggerType = TriggerType.manual
    ) -> "PipelineRun":
        async with self._session_factory() as session:
            async with session.begin():
                repo = PipelineRunRepository(session)
                return await repo.create(pipeline_name=pipeline_name, trigger_type=trigger_type)

    async def update_pipeline_run_status(
        self,
        run_id: uuid.UUID,
        status: RunStatus,
        finished_at: Any | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = PipelineRunRepository(session)
                await repo.update_status(run_id=run_id, status=status, finished_at=finished_at)

    async def get_pipeline_run(self, run_id: uuid.UUID) -> "PipelineRun | None":
        async with self._session_factory() as session:
            repo = PipelineRunRepository(session)
            return await repo.get(run_id)

    async def create_stage_run(
        self,
        pipeline_run_id: uuid.UUID,
        stage_name: str,
        sequence: int,
        inputs_snapshot: dict[str, Any],
    ) -> "StageRun":
        async with self._session_factory() as session:
            async with session.begin():
                repo = StageRunRepository(session)
                return await repo.create(
                    pipeline_run_id=pipeline_run_id,
                    stage_name=stage_name,
                    sequence=sequence,
                    inputs_snapshot=inputs_snapshot,
                )

    async def update_stage_run_status(
        self,
        stage_run_id: uuid.UUID,
        status: RunStatus,
        error_message: str | None = None,
        outputs_snapshot: dict[str, Any] | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = StageRunRepository(session)
                await repo.update_status(
                    stage_run_id=stage_run_id,
                    status=status,
                    error_message=error_message,
                    outputs_snapshot=outputs_snapshot,
                )

    async def create_artifact_ref(
        self,
        pipeline_run_id: uuid.UUID,
        stage_run_id: uuid.UUID | None,
        name: str,
        mime_type: str,
        relative_path: str,
        sha256: str,
    ) -> "ArtifactRef":
        async with self._session_factory() as session:
            async with session.begin():
                repo = ArtifactRefRepository(session)
                return await repo.create(
                    pipeline_run_id=pipeline_run_id,
                    stage_run_id=stage_run_id,
                    name=name,
                    mime_type=mime_type,
                    relative_path=relative_path,
                    sha256=sha256,
                )

    async def write_checkpoint(self, pipeline_run_id: uuid.UUID, stage_name: str, snapshot_json: str) -> "CheckpointRecord":
        async with self._session_factory() as session:
            async with session.begin():
                repo = CheckpointRepository(session)
                return await repo.write(
                    pipeline_run_id=pipeline_run_id,
                    stage_name=stage_name,
                    snapshot_json=snapshot_json,
                )
