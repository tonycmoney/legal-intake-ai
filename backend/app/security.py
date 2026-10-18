"""Staff authentication, rate limiting and server generated secrets."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import AppSecret

SESSION_COOKIE = "intake_staff"


def get_or_create_secret(db: Session, name: str) -> str:
    row = db.get(AppSecret, name)
    if row is None:
        row = AppSecret(name=name, value=secrets.token_urlsafe(48))
        db.add(row)
        db.commit()
    return row.value


def _serializer(db: Session) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_or_create_secret(db, "session_key"), salt="staff-session")


def password_ok(candidate: str, settings: Settings) -> bool:
    if not settings.staff_password:
        return False
    return hmac.compare_digest(candidate.encode(), settings.staff_password.encode())


def issue_session(db: Session) -> str:
    return _serializer(db).dumps({"role": "staff"})


def require_staff(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.staff_password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Staff access is not configured")
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    try:
        _serializer(db).loads(token, max_age=settings.session_hours * 3600)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from exc
    return "staff"


def client_ip(request: Request) -> str:
    # Behind Railway's proxy the client is the first X-Forwarded-For entry.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding window limiter per key, in memory (one instance per process)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window_s:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
