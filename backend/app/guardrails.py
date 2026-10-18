"""Deterministic safety checks that run around every model call.

The model is instructed to follow the firm's rules, but these checks do not
rely on it: they run in code before and after each turn.

* Emergency detection (before): custody, imminent court dates, lockouts and
  threats to safety raise urgency and show the client an immediate contact.
* Self harm detection (before): shows crisis resources (988).
* Reply review (after): a reply that predicts outcomes, guarantees results or
  tells the person what legal step to take is replaced and flagged for staff,
  since only a lawyer may give legal advice (NY Rules 5.5, 7.1).
"""

import re
from dataclasses import dataclass, field

from app.models import Urgency

_EMERGENCY_PATTERNS = {
    "custody": [
        r"\b(detained|in custody|locked up|in jail)\b",
        r"\barrested (today|tonight|yesterday|last night)\b",
        r"\bice (has|took|picked up|detained|arrested)\b",
        r"\b(deportation|removal) (hearing|order)\b.*\b(today|tomorrow|this week)\b",
    ],
    "imminent_court_date": [
        r"\b(court|hearing|arraignment|trial)\b[^.?!]{0,40}\b(today|tomorrow|tonight)\b",
        r"\b(today|tomorrow)\b[^.?!]{0,40}\b(court|hearing|arraignment|trial)\b",
    ],
    "lockout_or_eviction": [
        r"\b(locked out|changed the locks|marshal)\b",
        r"\beviction\b[^.?!]{0,40}\b(today|tomorrow|this week)\b",
    ],
    "safety": [
        r"\b(threaten(ed|ing)? to (kill|hurt)|in danger|not safe|domestic violence|beat me)\b",
    ],
}

_SELF_HARM = [
    r"\b(kill myself|end my life|suicid(e|al)|hurt myself|don'?t want to (live|be alive))\b",
]

# Phrases that cross from intake into legal advice or outcome promises.
_ADVICE_PATTERNS = [
    r"\byou (will|would|are going to) (definitely |certainly |probably )?"
    r"(win|lose|be deported|go to jail|get custody)\b",
    # "I can't guarantee anything" is fine; "I guarantee" is not.
    r"(?<!can't )(?<!cannot )(?<!not )(?<!no )\b(guarantee|guaranteed)\b",
    r"\b(100% sure|no doubt you)\b",
    r"\byou (should|must|need to) (plead|sign|file|stop paying|sue|not pay|withhold rent)\b",
    r"\b(you have a (strong|weak|great|good) case)\b",
    r"\bthe (law|statute) says you (can|can't|cannot|must)\b",
]

SAFE_FALLBACK = (
    "I'm not able to give legal advice or predict how a case will turn out. "
    "An attorney will review what you've shared and can talk through your options "
    "during a consultation. Is there anything else about your situation you'd like "
    "the attorney to know?"
)


@dataclass
class Screen:
    urgency: Urgency | None = None
    reasons: list[str] = field(default_factory=list)
    self_harm: bool = False


def screen_message(text: str) -> Screen:
    lowered = text.lower()
    screen = Screen()
    for reason, patterns in _EMERGENCY_PATTERNS.items():
        if any(re.search(p, lowered) for p in patterns):
            screen.reasons.append(reason)
    if screen.reasons:
        screen.urgency = Urgency.emergency
    if any(re.search(p, lowered) for p in _SELF_HARM):
        screen.self_harm = True
        screen.reasons.append("self_harm")
    return screen


@dataclass
class ReplyReview:
    text: str
    flags: list[str]


def review_reply(text: str) -> ReplyReview:
    lowered = text.lower()
    hits = [p for p in _ADVICE_PATTERNS if re.search(p, lowered)]
    if hits:
        return ReplyReview(SAFE_FALLBACK, ["replaced_reply:legal_advice_or_outcome_prediction"])
    return ReplyReview(text, [])


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact(text: str) -> str:
    """Strip contact details and SSNs before anything is written to logs."""
    text = _SSN.sub("[ssn]", text)
    text = _EMAIL.sub("[email]", text)
    return _PHONE.sub("[phone]", text)
