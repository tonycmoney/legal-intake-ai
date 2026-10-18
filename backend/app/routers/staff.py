"""Staff dashboard endpoints. All require a signed session cookie."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.models import URGENCY_RANK, ConflictParty, Intake, IntakeStatus, Urgency
from app.schemas import (
    ConflictIn,
    ConflictOut,
    IntakeDetail,
    IntakeSummary,
    IntakeUpdate,
    LoginIn,
    Stats,
)
from app.security import (
    SESSION_COOKIE,
    client_ip,
    issue_session,
    limiter,
    password_ok,
    require_staff,
)
from app.services import audit, purge_declined

router = APIRouter(prefix="/api/staff", tags=["staff"])

# What a reviewer may do from each state.
STAFF_TRANSITIONS: dict[IntakeStatus, set[IntakeStatus]] = {
    IntakeStatus.in_progress: {IntakeStatus.declined},
    IntakeStatus.submitted: {IntakeStatus.accepted, IntakeStatus.declined},
    IntakeStatus.conflict_hold: {IntakeStatus.accepted, IntakeStatus.declined},
    IntakeStatus.accepted: {IntakeStatus.declined},
    IntakeStatus.declined: set(),
}


def _summary(i: Intake) -> dict:
    return {
        "id": i.id,
        "status": i.status,
        "urgency": i.urgency,
        "practice_area": i.practice_area,
        "client_name": i.client_name,
        "county": i.county,
        "in_custody": i.in_custody,
        "deadline": i.deadline,
        "has_conflict": bool(i.conflict_matches),
        "has_guardrail_flags": bool(i.guardrail_flags),
        "turns": i.turns,
        "created_at": i.created_at,
        "updated_at": i.updated_at,
    }


def _detail(i: Intake) -> IntakeDetail:
    return IntakeDetail(
        **_summary(i),
        phone=i.phone,
        email=i.email,
        adverse_parties=i.adverse_parties,
        key_facts=i.key_facts,
        summary=i.summary,
        recommended_next_step=i.recommended_next_step,
        conflict_matches=i.conflict_matches,
        guardrail_flags=i.guardrail_flags,
        staff_notes=i.staff_notes,
        chat=i.chat,
        events=i.events,
    )


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.staff_password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Staff access is not configured")
    if not limiter.allow(f"login:{client_ip(request)}", 10, 900):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts")
    if not password_ok(payload.password, settings):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(db),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        samesite="strict",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me")
def me(_: str = Depends(require_staff)):
    return {"role": "staff"}


@router.get("/intakes", response_model=list[IntakeSummary])
def list_intakes(
    status_filter: IntakeStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: str = Depends(require_staff),
):
    purge_declined(db, settings.declined_retention_days)
    query = select(Intake)
    if status_filter:
        query = query.where(Intake.status == status_filter)
    intakes = list(db.scalars(query))
    # Emergencies first, then newest.
    intakes.sort(key=lambda i: (-URGENCY_RANK[i.urgency], -i.created_at.timestamp()))
    return [_summary(i) for i in intakes]


@router.get("/stats", response_model=Stats)
def stats(db: Session = Depends(get_db), _: str = Depends(require_staff)):
    counts = dict(db.execute(select(Intake.status, func.count()).group_by(Intake.status)).all())
    open_statuses = (IntakeStatus.in_progress, IntakeStatus.submitted, IntakeStatus.conflict_hold)
    emergencies = db.scalar(
        select(func.count()).where(
            Intake.urgency == Urgency.emergency, Intake.status.in_(open_statuses)
        )
    )
    return Stats(
        by_status={s.value: int(counts.get(s, 0)) for s in IntakeStatus},
        emergencies_open=int(emergencies or 0),
        conflict_holds=int(counts.get(IntakeStatus.conflict_hold, 0)),
    )


@router.get("/intakes/{intake_id}", response_model=IntakeDetail)
def get_intake(intake_id: int, db: Session = Depends(get_db), _: str = Depends(require_staff)):
    intake = db.scalars(
        select(Intake).options(selectinload(Intake.events)).where(Intake.id == intake_id)
    ).first()
    if intake is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Intake not found")
    return _detail(intake)


@router.patch("/intakes/{intake_id}", response_model=IntakeDetail)
def update_intake(
    intake_id: int,
    payload: IntakeUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_staff),
):
    intake = db.get(Intake, intake_id)
    if intake is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Intake not found")
    if payload.status and payload.status != intake.status:
        if payload.status not in STAFF_TRANSITIONS[intake.status]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Cannot move from {intake.status.value} to {payload.status.value}",
            )
        audit(db, intake, "staff", f"status {intake.status.value} -> {payload.status.value}")
        intake.status = payload.status
    if payload.staff_notes is not None:
        intake.staff_notes = payload.staff_notes
        audit(db, intake, "staff", "notes updated")
    db.commit()
    return get_intake(intake_id, db, "staff")


@router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(db: Session = Depends(get_db), _: str = Depends(require_staff)):
    return db.scalars(select(ConflictParty).order_by(ConflictParty.name)).all()


@router.post("/conflicts", response_model=ConflictOut, status_code=status.HTTP_201_CREATED)
def add_conflict(payload: ConflictIn, db: Session = Depends(get_db), _=Depends(require_staff)):
    party = ConflictParty(**payload.model_dump())
    db.add(party)
    db.commit()
    db.refresh(party)
    return party


@router.delete("/conflicts/{party_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conflict(party_id: int, db: Session = Depends(get_db), _=Depends(require_staff)):
    party = db.get(ConflictParty, party_id)
    if party is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(party)
    db.commit()
