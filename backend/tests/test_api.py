from datetime import UTC, datetime, timedelta

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Intake, IntakeStatus
from app.routers.public import get_llm
from app.services import purge_declined
from tests.fakes import details, resp, text, tool


def start(client) -> str:
    res = client.post("/api/intakes")
    assert res.status_code == 201
    return res.json()["token"]


def say(client, token, msg):
    return client.post(f"/api/intakes/{token}/messages", json={"text": msg})


# Public flow


def test_health_and_security_headers(client):
    res = client.get("/api/health")
    assert res.json() == {"status": "ok"}
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["cache-control"] == "no-store"


def test_config(client):
    data = client.get("/api/config").json()
    assert data["ai_enabled"] is True
    assert data["firm_name"] == "Hudson Row Legal"


def test_start_returns_greeting_without_model_call(client, fake_llm):
    res = client.post("/api/intakes").json()
    assert res["chat"][0]["role"] == "assistant"
    assert "intake assistant" in res["chat"][0]["text"]
    assert len(res["token"]) > 20
    assert fake_llm.calls == []


def test_full_conversation_reaches_staff(client, fake_llm):
    fake_llm.responses = [
        resp(
            tool(
                "record_intake_details",
                details(
                    client_name="Ana Lima",
                    phone="718-555-0142",
                    practice_area="real_estate",
                    adverse_parties=["Greenpoint Realty"],
                    county="Kings",
                ),
            )
        ),
        resp(text("Thanks Ana. What happened?")),
        resp(
            tool("complete_intake", {"summary": "Repairs dispute.", "recommended_next_step": "X"})
        ),
        resp(text("The firm will contact you within one business day.")),
    ]
    token = start(client)
    first = say(client, token, "Ana Lima, 718-555-0142, landlord Greenpoint Realty, Brooklyn")
    assert first.status_code == 200
    assert first.json()["reply"] == "Thanks Ana. What happened?"

    second = say(client, token, "No heat for 3 weeks").json()
    assert second["status"] == "submitted"
    assert second["open"] is False

    session = client.get(f"/api/intakes/{token}").json()
    assert [line["role"] for line in session["chat"]] == [
        "assistant",
        "client",
        "assistant",
        "client",
        "assistant",
    ]
    # Submitted intakes are closed to further messages.
    assert say(client, token, "one more thing").status_code == 409


def test_emergency_and_crisis_flags(client, fake_llm):
    fake_llm.responses = [resp(text("Please call us now.")), resp(text("Please call 988."))]
    token = start(client)
    assert say(client, token, "ICE detained my husband this morning").json()["emergency"] is True
    body = say(client, token, "I don't want to be alive anymore").json()
    assert body["show_crisis_resources"] is True


def test_unknown_token_404(client):
    assert client.get("/api/intakes/nope").status_code == 404
    assert say(client, "nope", "hi").status_code == 404


def test_message_validation(client):
    token = start(client)
    assert say(client, token, "").status_code == 422
    assert say(client, token, "x" * 2001).status_code == 413


def test_rate_limit(client, fake_llm, settings):
    settings.rate_limit_messages = 2
    fake_llm.responses = [resp(text("a")), resp(text("b"))]
    token = start(client)
    assert say(client, token, "1").status_code == 200
    assert say(client, token, "2").status_code == 200
    assert say(client, token, "3").status_code == 429


def test_turn_limit(client, fake_llm, settings):
    settings.max_turns_per_session = 1
    fake_llm.responses = [resp(text("a"))]
    token = start(client)
    assert say(client, token, "1").status_code == 200
    assert say(client, token, "2").status_code == 409


def test_no_api_key_means_503_not_a_fake_reply(client, settings):
    app.dependency_overrides.pop(get_llm)
    no_key = Settings(database_url=settings.database_url, staff_password="x")
    app.dependency_overrides[get_settings] = lambda: no_key
    token = start(client)
    res = say(client, token, "hello")
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"]
    assert client.get("/api/config").json()["ai_enabled"] is False


# Staff


def test_staff_requires_login(client):
    assert client.get("/api/staff/intakes").status_code == 401
    assert client.post("/api/staff/login", json={"password": "wrong"}).status_code == 401
    client.cookies.set("intake_staff", "forged.value.here")
    assert client.get("/api/staff/intakes").status_code == 401


def test_staff_disabled_without_password(client, settings):
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url=settings.database_url, anthropic_api_key="k"
    )
    assert client.post("/api/staff/login", json={"password": "x"}).status_code == 503
    assert client.get("/api/staff/intakes").status_code == 503


def test_login_cookie_is_hardened(client):
    from tests.conftest import PASSWORD

    res = client.post("/api/staff/login", json={"password": PASSWORD})
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_login_rate_limited(client):
    for _ in range(10):
        client.post("/api/staff/login", json={"password": "wrong"})
    assert client.post("/api/staff/login", json={"password": "wrong"}).status_code == 429


def test_triage_queue_orders_emergencies_first(staff, fake_llm):
    fake_llm.responses = [resp(text("ok")), resp(text("ok"))]
    calm = start(staff)
    say(staff, calm, "I'm buying a condo")
    urgent = start(staff)
    say(staff, urgent, "My son was arrested last night")

    queue = staff.get("/api/staff/intakes").json()
    assert queue[0]["urgency"] == "emergency"
    assert queue[1]["urgency"] == "normal"


def test_conflict_hold_visible_to_staff(staff, fake_llm):
    fake_llm.responses = [
        resp(tool("record_intake_details", details(adverse_parties=["Bluestone Properties"]))),
        resp(text("A staff member will contact you shortly.")),
    ]
    token = start(staff)
    body = say(staff, token, "My landlord is Bluestone Properties").json()
    assert body["status"] == "conflict_hold"
    assert body["open"] is True

    item = staff.get("/api/staff/intakes?status=conflict_hold").json()[0]
    assert item["has_conflict"] is True
    detail = staff.get(f"/api/staff/intakes/{item['id']}").json()
    assert detail["conflict_matches"][0]["matched_name"] == "Bluestone Properties LLC"
    assert any("conflict hold" in e["action"] for e in detail["events"])
    assert staff.get("/api/staff/stats").json()["conflict_holds"] == 1


def test_staff_status_transitions_and_audit(staff, fake_llm):
    fake_llm.responses = [
        resp(tool("complete_intake", {"summary": "s", "recommended_next_step": "n"})),
        resp(text("done")),
    ]
    token = start(staff)
    say(staff, token, "that's all")
    intake_id = staff.get("/api/staff/intakes").json()[0]["id"]

    url = f"/api/staff/intakes/{intake_id}"
    assert staff.patch(url, json={"status": "in_progress"}).status_code == 409
    res = staff.patch(url, json={"status": "accepted", "staff_notes": "Call Tue"}).json()
    assert res["status"] == "accepted"
    assert res["staff_notes"] == "Call Tue"
    actions = [e["action"] for e in res["events"]]
    assert "status submitted -> accepted" in actions
    assert staff.patch(url, json={"status": "declined"}).json()["status"] == "declined"
    assert staff.patch(url, json={"status": "accepted"}).status_code == 409


def test_conflict_list_crud(staff):
    names = [p["name"] for p in staff.get("/api/staff/conflicts").json()]
    assert "Bluestone Properties LLC" in names
    created = staff.post(
        "/api/staff/conflicts", json={"name": "Jo Park", "relationship_type": "adverse"}
    ).json()
    bad = {"name": "X Y", "relationship_type": "friend"}
    assert staff.post("/api/staff/conflicts", json=bad).status_code == 422
    assert staff.delete(f"/api/staff/conflicts/{created['id']}").status_code == 204


def test_declined_intakes_purged_after_retention(client):
    with SessionLocal() as db:
        old = Intake(status=IntakeStatus.declined)
        recent = Intake(status=IntakeStatus.declined)
        kept = Intake(status=IntakeStatus.accepted)
        db.add_all([old, recent, kept])
        db.commit()
        old.updated_at = datetime.now(UTC) - timedelta(days=45)
        kept.updated_at = datetime.now(UTC) - timedelta(days=45)
        db.commit()

        assert purge_declined(db, 30) == 1
        remaining = {i.status for i in db.query(Intake).all()}
        assert remaining == {IntakeStatus.declined, IntakeStatus.accepted}
