"""Endpoints used by prospective clients on the intake page."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import run_turn
from app.config import Settings, get_settings
from app.db import get_db
from app.guardrails import redact
from app.llm import LLM, AnthropicLLM, LLMUnavailable
from app.models import Intake, IntakeStatus, Urgency
from app.schemas import MessageIn, MessageOut, PublicConfig, SessionOut
from app.security import client_ip, limiter
from app.services import audit, known_parties

log = logging.getLogger("intake")
router = APIRouter(prefix="/api", tags=["intake"])

GREETING = (
    "Hi, I'm the intake assistant for {firm}. I'll ask a few questions so an attorney can "
    "review your situation. To start, what's your name and the best phone number or email "
    "to reach you?"
)

# Intakes the client can keep writing to.
OPEN_STATUSES = {IntakeStatus.in_progress, IntakeStatus.conflict_hold}


def get_llm(settings: Settings = Depends(get_settings)) -> LLM:
    if not settings.anthropic_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI intake assistant is not configured yet. Please call the office.",
        )
    return AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        effort=settings.anthropic_effort,
        max_tokens=settings.max_output_tokens,
    )


def _get_intake(db: Session, token: str) -> Intake:
    intake = db.scalars(select(Intake).where(Intake.token == token)).first()
    if intake is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Intake not found")
    return intake


@router.get("/config", response_model=PublicConfig)
def config(settings: Settings = Depends(get_settings)):
    return PublicConfig(
        firm_name=settings.firm_name,
        firm_phone=settings.firm_phone,
        ai_enabled=bool(settings.anthropic_api_key),
        max_message_chars=settings.max_message_chars,
    )


@router.post("/intakes", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_intake(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not limiter.allow(f"start:{client_ip(request)}", 10, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many new sessions")
    greeting = GREETING.format(firm=settings.firm_name)
    intake = Intake(chat=[{"role": "assistant", "text": greeting}])
    db.add(intake)
    db.commit()
    return SessionOut(token=intake.token, status=intake.status, chat=intake.chat, open=True)


@router.get("/intakes/{token}", response_model=SessionOut)
def get_intake(token: str, db: Session = Depends(get_db)):
    intake = _get_intake(db, token)
    return SessionOut(
        token=intake.token,
        status=intake.status,
        chat=intake.chat,
        open=intake.status in OPEN_STATUSES,
    )


@router.post("/intakes/{token}/messages", response_model=MessageOut)
def send_message(
    token: str,
    payload: MessageIn,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm: LLM = Depends(get_llm),
):
    text = payload.text.strip()
    if len(text) > settings.max_message_chars:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Please keep messages under {settings.max_message_chars} characters",
        )
    if not limiter.allow(
        f"msg:{client_ip(request)}", settings.rate_limit_messages, settings.rate_limit_window_s
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many messages, slow down")

    intake = _get_intake(db, token)
    if intake.status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This intake has been submitted")
    if intake.turns >= settings.max_turns_per_session:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This conversation is at its limit; the firm will follow up"
        )

    firm = {"name": settings.firm_name, "phone": settings.firm_phone}
    try:
        result = run_turn(intake, text, llm, known_parties(db), firm)
    except LLMUnavailable as exc:
        db.rollback()
        log.warning("LLM unavailable: %s", redact(str(exc))[:300])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The assistant is temporarily unavailable. Please call {settings.firm_phone}.",
        ) from exc

    for line in result.audit:
        audit(db, intake, "assistant", line)
    db.commit()

    return MessageOut(
        reply=result.reply,
        status=intake.status,
        open=intake.status in OPEN_STATUSES,
        emergency=intake.urgency == Urgency.emergency,
        show_crisis_resources=result.self_harm,
    )
