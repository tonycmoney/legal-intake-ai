from __future__ import annotations

import enum
import secrets
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_token() -> str:
    return secrets.token_urlsafe(24)


class IntakeStatus(enum.StrEnum):
    in_progress = "in_progress"  # client is still chatting
    submitted = "submitted"  # assistant finished; waiting for staff
    accepted = "accepted"  # staff will schedule a consultation
    declined = "declined"  # firm will not take the matter
    conflict_hold = "conflict_hold"  # possible conflict; attorney must review


class Urgency(enum.StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    emergency = "emergency"


URGENCY_RANK = {Urgency.low: 0, Urgency.normal: 1, Urgency.high: 2, Urgency.emergency: 3}


class Intake(Base):
    __tablename__ = "intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Unguessable handle the browser uses; the numeric id is never exposed publicly.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_token)
    status: Mapped[IntakeStatus] = mapped_column(
        Enum(IntakeStatus, native_enum=False, length=20), default=IntakeStatus.in_progress
    )
    urgency: Mapped[Urgency] = mapped_column(
        Enum(Urgency, native_enum=False, length=20), default=Urgency.normal
    )
    practice_area: Mapped[str] = mapped_column(String(40), default="")
    client_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    county: Mapped[str] = mapped_column(String(100), default="")
    in_custody: Mapped[str] = mapped_column(String(10), default="unknown")
    deadline: Mapped[str] = mapped_column(String(200), default="")
    adverse_parties: Mapped[list[str]] = mapped_column(JSON, default=list)
    key_facts: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    recommended_next_step: Mapped[str] = mapped_column(Text, default="")

    conflict_matches: Mapped[list[dict]] = mapped_column(JSON, default=list)
    guardrail_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    staff_notes: Mapped[str] = mapped_column(Text, default="")

    # Raw Messages API content, replayed unchanged on the next turn
    # (thinking blocks included, as the API requires).
    transcript: Mapped[list[dict]] = mapped_column(JSON, default=list)
    turns: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    events: Mapped[list[AuditEvent]] = relationship(
        back_populates="intake", cascade="all, delete-orphan", order_by="AuditEvent.id"
    )


class AuditEvent(Base):
    """Who changed what on an intake. Never stores message content."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intake_id: Mapped[int] = mapped_column(ForeignKey("intakes.id", ondelete="CASCADE"))
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    intake: Mapped[Intake] = relationship(back_populates="events")


class ConflictParty(Base):
    """Current and former clients and adverse parties, for conflict checks."""

    __tablename__ = "conflict_parties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    relationship_type: Mapped[str] = mapped_column(String(50))  # client | adverse | former_client
    matter: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSecret(Base):
    """Server generated secrets (e.g. session signing key), created on first start."""

    __tablename__ = "app_secrets"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
