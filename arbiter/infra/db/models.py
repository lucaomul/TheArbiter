from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

try:  # pragma: no cover - optional production dependency
    from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
except Exception:  # pragma: no cover - graceful fallback when DB deps are absent
    DeclarativeBase = object  # type: ignore[assignment]
    Mapped = Any  # type: ignore[assignment]
    mapped_column = None  # type: ignore[assignment]
    relationship = None  # type: ignore[assignment]
    DateTime = Float = ForeignKey = Integer = JSON = String = Text = None  # type: ignore[assignment]


SQLALCHEMY_MODELS_AVAILABLE = mapped_column is not None and relationship is not None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


if SQLALCHEMY_MODELS_AVAILABLE:
    class Base(DeclarativeBase):
        pass


    class Run(Base):
        __tablename__ = "runs"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
        task_mode: Mapped[str] = mapped_column(String(120), default="", nullable=False)
        user_input: Mapped[str] = mapped_column(Text, default="", nullable=False)
        best_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        best_solution: Mapped[str] = mapped_column(Text, default="", nullable=False)
        iteration_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        stop_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
        ship_readiness: Mapped[str] = mapped_column(String(40), default="UNASSESSED", nullable=False)
        verification_status: Mapped[str] = mapped_column(String(40), default="UNVERIFIED", nullable=False)
        validity_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False)
        run_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

        iterations: Mapped[list["Iteration"]] = relationship(
            back_populates="run",
            cascade="all, delete-orphan",
        )


    class Iteration(Base):
        __tablename__ = "iterations"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
        run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False, index=True)
        iteration_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        tech_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        logic_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
        avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        ship_readiness: Mapped[str] = mapped_column(String(40), default="UNASSESSED", nullable=False)
        verification_status: Mapped[str] = mapped_column(String(40), default="UNVERIFIED", nullable=False)
        verification_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        architect_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
        tech_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
        logic_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
        preflight_issues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
        tech_issues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
        logic_issues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
        janitor_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
        solution: Mapped[str] = mapped_column(Text, default="", nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

        run: Mapped["Run"] = relationship(back_populates="iterations")


    class MemoryEntry(Base):
        __tablename__ = "memory_entries"

        id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
        run_id: Mapped[str] = mapped_column(String(36), default="", nullable=False, index=True)
        task_mode: Mapped[str] = mapped_column(String(120), default="", nullable=False)
        task_hash: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
        avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        memory_status: Mapped[str] = mapped_column(String(40), default="ACCEPT", nullable=False)
        consensus_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        repair_patterns: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
else:
    class Base:
        pass


    class Run:
        pass


    class Iteration:
        pass


    class MemoryEntry:
        pass
