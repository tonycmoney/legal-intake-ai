"""Small database helpers shared by the routers."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.conflicts import Party
from app.models import AuditEvent, ConflictParty, Intake, IntakeStatus

SEED_CONFLICTS = [
    ("Bluestone Properties LLC", "client", "Commercial lease portfolio"),
    ("Greenleaf Management Corp", "client", "Building compliance"),
    ("Harbor Freight Movers Inc", "former_client", "Contract dispute (closed 2025)"),
    ("Dmitri Volkov", "adverse", "Volkov v. Patel"),
    ("Patricia Okafor", "adverse", "People v. R. Mendez (complainant)"),
]


def known_parties(db: Session) -> list[Party]:
    rows = db.scalars(select(ConflictParty)).all()
    return [Party(r.name, r.relationship_type, r.matter) for r in rows]


def seed_conflicts(db: Session) -> None:
    if db.scalars(select(ConflictParty).limit(1)).first() is not None:
        return
    for name, rel, matter in SEED_CONFLICTS:
        db.add(ConflictParty(name=name, relationship_type=rel, matter=matter))
    db.commit()


def audit(db: Session, intake: Intake, actor: str, action: str) -> None:
    db.add(AuditEvent(intake_id=intake.id, actor=actor, action=action[:200]))


def purge_declined(db: Session, retention_days: int, now: datetime | None = None) -> int:
    """Delete declined prospective client records past the retention window."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    ids = [
        i.id
        for i in db.scalars(select(Intake).where(Intake.status == IntakeStatus.declined))
        if _aware(i.updated_at) < cutoff
    ]
    if ids:
        db.execute(delete(AuditEvent).where(AuditEvent.intake_id.in_(ids)))
        db.execute(delete(Intake).where(Intake.id.in_(ids)))
        db.commit()
    return len(ids)


def _aware(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; treat them as UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
