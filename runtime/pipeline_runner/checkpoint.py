from __future__ import annotations


from runtime.state_store.database import StateStore

from .context import RunContext


class CheckpointWriter:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    async def write(self, stage_name: str, context: RunContext) -> None:
        await self._store.write_checkpoint(
            pipeline_run_id=context.pipeline_run_id,
            stage_name=stage_name,
            snapshot_json=context.to_json(),
        )
