import pytest

from app.conflicts import Party, check_conflicts, normalize, similarity
from app.guardrails import SAFE_FALLBACK, redact, review_reply, screen_message
from app.models import Urgency

# Conflicts


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Smith, John", "John Smith"),
        ("ACME Corporation", "Acme Corp."),
        ("Bluestone Properties LLC", "bluestone properties"),
        ("Maria  Gonzalez-Ruiz", "maria gonzalez ruiz"),
    ],
)
def test_equivalent_names_match(a, b):
    assert similarity(a, b) >= 0.88


@pytest.mark.parametrize(("a", "b"), [("John Smith", "Jane Doe"), ("Acme", "Apex Holdings")])
def test_different_names_do_not_match(a, b):
    assert similarity(a, b) < 0.88


def test_normalize_handles_empty():
    assert normalize("") == ""
    assert similarity("", "John") == 0.0


KNOWN = [
    Party("Bluestone Properties LLC", "client", "Lease portfolio"),
    Party("Dmitri Volkov", "adverse", "Volkov v. Patel"),
    Party("Harbor Freight Movers Inc", "former_client", "Contract dispute"),
]


def test_adverse_party_who_is_our_client_is_a_conflict():
    matches = check_conflicts("Ana Lima", ["Bluestone Properties"], KNOWN)
    assert [m.matched_name for m in matches] == ["Bluestone Properties LLC"]
    assert matches[0].relationship_type == "client"


def test_prospective_client_who_is_adverse_is_a_conflict():
    matches = check_conflicts("Volkov, Dmitri", [], KNOWN)
    assert matches and matches[0].relationship_type == "adverse"


def test_former_client_flagged():
    matches = check_conflicts("Ana Lima", ["Harbor Freight Movers"], KNOWN)
    assert matches[0].relationship_type == "former_client"


def test_no_conflict():
    assert check_conflicts("Ana Lima", ["Greenpoint Realty"], KNOWN) == []


# Emergency and self harm screening


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("My husband was detained by ICE this morning", "custody"),
        ("ICE picked up my brother", "custody"),
        ("I have court tomorrow and no lawyer", "imminent_court_date"),
        ("The landlord changed the locks while I was at work", "lockout_or_eviction"),
        ("My ex threatened to kill me", "safety"),
    ],
)
def test_emergencies_detected(text, reason):
    screen = screen_message(text)
    assert screen.urgency == Urgency.emergency
    assert reason in screen.reasons


def test_routine_message_not_flagged():
    screen = screen_message("I'm buying a condo in Queens and need help with the closing")
    assert screen.urgency is None
    assert not screen.self_harm


def test_self_harm_detected_without_emergency_urgency():
    screen = screen_message("Honestly I don't want to be alive anymore")
    assert screen.self_harm
    assert screen.urgency is None


# Reply review


@pytest.mark.parametrize(
    "reply",
    [
        "Don't worry, you will definitely win this case.",
        "I can guarantee the charges will be dropped.",
        "You should plead guilty to get a better deal.",
        "You have a strong case against your landlord.",
        "You need to stop paying rent until they fix it.",
    ],
)
def test_advice_and_predictions_replaced(reply):
    review = review_reply(reply)
    assert review.text == SAFE_FALLBACK
    assert review.flags


def test_disclaiming_a_guarantee_is_allowed():
    reply = "I can't guarantee any outcome, but an attorney will review this today."
    assert review_reply(reply).text == reply


def test_normal_intake_reply_untouched():
    reply = "Thank you. What county is the property in, and when did you receive the notice?"
    assert review_reply(reply).text == reply


def test_redact():
    text = "Call me at (718) 555-0142 or ana@example.com, SSN 123-45-6789"
    assert redact(text) == "Call me at [phone] or [email], SSN [ssn]"
