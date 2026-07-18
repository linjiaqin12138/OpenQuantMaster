from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, JSON, String, Text
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TriggerType(str, Enum):
    manual = "manual"
    cron = "cron"
    event = "event"


class RunStatus(str, Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"


class Base(DeclarativeBase):
    pass


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trigger_type: Mapped[TriggerType] = mapped_column(SQLEnum(TriggerType), default=TriggerType.manual)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus), default=RunStatus.running)
    artifacts_index: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    stage_runs: Mapped[list["StageRun"]] = relationship(
        back_populates="pipeline_run", cascade="all, delete-orphan", lazy="selectin"
    )
    artifact_refs: Mapped[list["ArtifactRef"]] = relationship(
        back_populates="pipeline_run", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("trigger_type", TriggerType.manual)
        kwargs.setdefault("started_at", utc_now())
        kwargs.setdefault("status", RunStatus.running)
        kwargs.setdefault("artifacts_index", {})
        kwargs.setdefault("cost_usd", 0.0)
        super().__init__(**kwargs)


class StageRun(Base):
    __tablename__ = "stage_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus), default=RunStatus.running)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="stage_runs")
    artifact_refs: Mapped[list["ArtifactRef"]] = relationship(
        back_populates="stage_run", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("started_at", utc_now())
        kwargs.setdefault("status", RunStatus.running)
        kwargs.setdefault("inputs_snapshot", {})
        kwargs.setdefault("outputs_snapshot", {})
        super().__init__(**kwargs)


class ArtifactRef(Base):
    __tablename__ = "artifact_refs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    stage_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stage_runs.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(511), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="artifact_refs")
    stage_run: Mapped["StageRun | None"] = relationship(back_populates="artifact_refs")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("created_at", utc_now())
        super().__init__(**kwargs)


class CheckpointRecord(Base):
    __tablename__ = "checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    stage_name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("created_at", utc_now())
        super().__init__(**kwargs)


class MarketType(str, Enum):
    crypto = "crypto"
    a_share = "a_share"
    us_equity = "us_equity"
    hk_equity = "hk_equity"


class SignalSide(str, Enum):
    long = "long"
    short = "short"
    close = "close"
    reduce = "reduce"


class SignalStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class Signal(BaseModel):
    """Pydantic contract for a trading signal.

    This model is the source of truth for ``schemas/signal.schema.json`` and for
    runtime validation.  Field names and semantics match the ORM model below.
    """

    model_config = ConfigDict(
        use_enum_values=False,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: str
    strategy_id: str
    symbol: str
    market: MarketType
    side: SignalSide
    strength: float = 0.0
    triggered_at: datetime = Field(default_factory=utc_now)
    valid_until: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: SignalStatus = SignalStatus.pending
    created_at: datetime = Field(default_factory=utc_now)


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    market: Mapped[MarketType] = mapped_column(SQLEnum(MarketType), nullable=False)
    side: Mapped[SignalSide] = mapped_column(SQLEnum(SignalSide), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[SignalStatus] = mapped_column(SQLEnum(SignalStatus), default=SignalStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("payload", {})
        kwargs.setdefault("status", SignalStatus.pending)
        kwargs.setdefault("created_at", utc_now())
        kwargs.setdefault("strength", 0.0)
        super().__init__(**kwargs)
