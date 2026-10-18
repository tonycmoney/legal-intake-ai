from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import IntakeStatus, Urgency


class PublicConfig(BaseModel):
    firm_name: str
    firm_phone: str
    ai_enabled: bool
    max_message_chars: int


class ChatLine(BaseModel):
    role: str
    text: str


class SessionOut(BaseModel):
    token: str
    status: IntakeStatus
    chat: list[ChatLine]
    open: bool


class MessageIn(BaseModel):
    text: str = Field(min_length=1)


class MessageOut(BaseModel):
    reply: str
    status: IntakeStatus
    open: bool
    emergency: bool
    show_crisis_resources: bool


class LoginIn(BaseModel):
    password: str


class IntakeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: IntakeStatus
    urgency: Urgency
    practice_area: str
    client_name: str
    county: str
    in_custody: str
    deadline: str
    has_conflict: bool
    has_guardrail_flags: bool
    turns: int
    created_at: datetime
    updated_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    actor: str
    action: str
    created_at: datetime


class IntakeDetail(IntakeSummary):
    phone: str
    email: str
    adverse_parties: list[str]
    key_facts: list[str]
    summary: str
    recommended_next_step: str
    conflict_matches: list[dict]
    guardrail_flags: list[str]
    staff_notes: str
    chat: list[ChatLine]
    events: list[AuditOut]


class IntakeUpdate(BaseModel):
    status: IntakeStatus | None = None
    staff_notes: str | None = Field(default=None, max_length=5000)


class ConflictIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    relationship_type: str = Field(pattern="^(client|former_client|adverse)$")
    matter: str = Field(default="", max_length=200)


class ConflictOut(ConflictIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class Stats(BaseModel):
    by_status: dict[str, int]
    emergencies_open: int
    conflict_holds: int
