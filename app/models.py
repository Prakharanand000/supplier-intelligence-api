"""SQLAlchemy models.

Types are chosen to work identically on PostgreSQL and SQLite (generic JSON,
no dialect-specific columns) so the fallback path is a true drop-in.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lei_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    identity_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    persons: Mapped[list["Person"]] = relationship(back_populates="company")
    documents: Mapped[list["Document"]] = relationship(back_populates="company")
    risk_signals: Mapped[list["RiskSignal"]] = relationship(back_populates="company")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    role: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )

    company: Mapped["Company"] = relationship(back_populates="persons")


class Document(Base):
    """Evidence. Every claim in a report traces back to a row here."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="documents")


class Relationship(Base):
    """Entity graph edges: person -> company, company -> parent, etc."""

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_entity: Mapped[str] = mapped_column(String(512), index=True)
    target_entity: Mapped[str] = mapped_column(String(512), index=True)
    relationship_type: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="risk_signals")


class Investigation(Base):
    """Full stored result of one investigate_supplier() call."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_name: Mapped[str] = mapped_column(String(512), index=True)
    query_country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    query_website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="unknown")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HttpCache(Base):
    """Raw upstream responses, so repeat investigations don't re-fetch."""

    __tablename__ = "http_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OfacEntry(Base):
    """Flattened OFAC SDN record - one row per name (primary or alias)."""

    __tablename__ = "ofac_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ent_num: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(512))
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    program: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_alias: Mapped[int] = mapped_column(Integer, default=0)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class OfacMeta(Base):
    """Single-row table tracking when the SDN list was last ingested."""

    __tablename__ = "ofac_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_documents_company_source", Document.company_id, Document.source)
Index("ix_risk_company_category", RiskSignal.company_id, RiskSignal.category)
