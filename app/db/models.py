"""Tabel database (SQLAlchemy 2.0).

Tipe kolom sengaja portabel (String untuk UUID, JSON) agar test bisa memakai SQLite,
sementara deployment memakai PostgreSQL.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (
        # Idempotensi: satu listing dengan isi yang sama hanya punya satu check.
        UniqueConstraint("listing_id", "content_hash", name="uq_checks_listing_content"),
        Index("ix_checks_cache_key", "cache_key"),
        Index("ix_checks_decision", "decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    listing_id: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    cache_key: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(16))
    decided_by: Mapped[str] = mapped_column(String(16))
    review_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    violations: Mapped[list] = mapped_column(JSON, default=list)
    rule_hits: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_policy_ids: Mapped[list] = mapped_column(JSON, default=list)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    llm_raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_errors: Mapped[list] = mapped_column(JSON, default=list)
    policy_version: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    check_id: Mapped[str] = mapped_column(ForeignKey("checks.id"), index=True)
    moderator_id: Mapped[str] = mapped_column(String(64))
    final_decision: Mapped[str] = mapped_column(String(16))
    policy_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BatchItem(Base):
    __tablename__ = "batch_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="pending")   # pending/done/failed
    check_id: Mapped[str | None] = mapped_column(ForeignKey("checks.id"), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
