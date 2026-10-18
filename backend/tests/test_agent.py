from app.agent import LOOP_LIMIT_REPLY, MAX_TOOL_ROUNDS, REFUSAL_REPLY, TOOLS, run_turn
from app.conflicts import Party
from app.guardrails import SAFE_FALLBACK
from app.models import Intake, IntakeStatus, Urgency
from tests.fakes import FakeLLM, details, resp, text, tool

FIRM = {"name": "Hudson Row Legal", "phone": "(555) 010-0199"}
KNOWN = [Party("Bluestone Properties LLC", "client", "Lease portfolio")]


def new_intake() -> Intake:
    return Intake(
        transcript=[],
        chat=[],
        adverse_parties=[],
        key_facts=[],
        conflict_matches=[],
        guardrail_flags=[],
        turns=0,
        status=IntakeStatus.in_progress,
        urgency=Urgency.normal,
        in_custody="unknown",
        client_name="",
    )


def test_tools_are_strict_with_closed_schemas():
    for t in TOOLS:
        assert t["strict"] is True
        schema = t["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_records_details_then_replies():
    intake = new_intake()
    llm = FakeLLM(
        [
            resp(
                tool(
                    "record_intake_details",
                    details(client_name="Ana Lima", practice_area="real_estate"),
                )
            ),
            resp(text("Thanks Ana. Who is the landlord?")),
        ]
    )
    result = run_turn(intake, "Hi, I'm Ana Lima, I have a lease problem", llm, KNOWN, FIRM)

    assert result.reply == "Thanks Ana. Who is the landlord?"
    assert intake.client_name == "Ana Lima"
    assert intake.practice_area == "real_estate"
    assert intake.turns == 1
    # user, assistant(tool_use), user(tool_result), assistant(text)
    roles = [m["role"] for m in intake.transcript]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert intake.transcript[2]["content"][0]["type"] == "tool_result"
    assert intake.chat[-1] == {"role": "assistant", "text": result.reply}


def test_transcript_is_replayed_unchanged_including_thinking():
    intake = new_intake()
    thinking = {"type": "thinking", "thinking": "", "signature": "sig123"}
    llm = FakeLLM([resp(thinking, text("Hello")), resp(text("Got it"))])
    run_turn(intake, "first", llm, KNOWN, FIRM)
    run_turn(intake, "second", llm, KNOWN, FIRM)

    sent = llm.calls[1]["messages"]
    assert sent[1] == {"role": "assistant", "content": [thinking, text("Hello")]}
    assert sent[-1]["content"][0]["text"] == "second"


def test_lists_merge_without_duplicates():
    intake = new_intake()
    llm = FakeLLM(
        [
            resp(tool("record_intake_details", details(adverse_parties=["Greenpoint Realty"]))),
            resp(
                tool(
                    "record_intake_details",
                    details(adverse_parties=["greenpoint realty", "Jo Park"]),
                    "toolu_2",
                )
            ),
            resp(text("Thanks.")),
        ]
    )
    run_turn(intake, "msg", llm, KNOWN, FIRM)
    assert intake.adverse_parties == ["Greenpoint Realty", "Jo Park"]


def test_conflict_puts_intake_on_hold_and_tells_model():
    intake = new_intake()
    llm = FakeLLM(
        [
            resp(tool("record_intake_details", details(adverse_parties=["Bluestone Properties"]))),
            resp(text("Thank you. A staff member will contact you shortly.")),
        ]
    )
    result = run_turn(intake, "My landlord is Bluestone Properties", llm, KNOWN, FIRM)

    assert intake.status == IntakeStatus.conflict_hold
    assert intake.conflict_matches[0]["matched_name"] == "Bluestone Properties LLC"
    tool_result = llm.calls[1]["messages"][-1]["content"][0]["content"]
    assert "CONFLICT_HOLD" in tool_result
    assert "conflict hold" in result.audit


def test_emergency_screen_raises_urgency_even_if_model_says_normal():
    intake = new_intake()
    llm = FakeLLM(
        [
            resp(tool("record_intake_details", details(urgency="normal"))),
            resp(text("Please call us right away.")),
        ]
    )
    result = run_turn(intake, "ICE detained my husband this morning", llm, KNOWN, FIRM)
    assert intake.urgency == Urgency.emergency
    assert "custody" in result.emergency_reasons


def test_custody_from_model_raises_urgency():
    intake = new_intake()
    llm = FakeLLM(
        [resp(tool("record_intake_details", details(in_custody="yes"))), resp(text("ok"))]
    )
    run_turn(intake, "my son is at the precinct", llm, KNOWN, FIRM)
    assert intake.urgency == Urgency.emergency
    assert intake.in_custody == "yes"


def test_urgency_never_lowered():
    intake = new_intake()
    intake.urgency = Urgency.high
    llm = FakeLLM([resp(tool("record_intake_details", details(urgency="low"))), resp(text("ok"))])
    run_turn(intake, "msg", llm, KNOWN, FIRM)
    assert intake.urgency == Urgency.high


def test_complete_intake_submits():
    intake = new_intake()
    llm = FakeLLM(
        [
            resp(
                text("Thank you, I'm sending this to the firm."),
                tool(
                    "complete_intake",
                    {"summary": "Tenant dispute.", "recommended_next_step": "Schedule consult"},
                ),
            ),
            resp(text("The firm will reach out within one business day.")),
        ]
    )
    result = run_turn(intake, "that's everything", llm, KNOWN, FIRM)
    assert result.submitted
    assert intake.status == IntakeStatus.submitted
    assert intake.summary == "Tenant dispute."
    assert result.reply == "The firm will reach out within one business day."


def test_submit_keeps_conflict_hold():
    intake = new_intake()
    intake.status = IntakeStatus.conflict_hold
    llm = FakeLLM(
        [
            resp(tool("complete_intake", {"summary": "x", "recommended_next_step": "y"})),
            resp(text("done")),
        ]
    )
    run_turn(intake, "done", llm, KNOWN, FIRM)
    assert intake.status == IntakeStatus.conflict_hold


def test_legal_advice_is_replaced_and_flagged():
    intake = new_intake()
    llm = FakeLLM([resp(text("Honestly, you have a strong case. You will definitely win."))])
    result = run_turn(intake, "Will I win?", llm, KNOWN, FIRM)
    assert result.reply == SAFE_FALLBACK
    assert intake.guardrail_flags
    assert intake.chat[-1]["text"] == SAFE_FALLBACK


def test_refusal_stop_reason():
    intake = new_intake()
    llm = FakeLLM([resp(text(""), stop="refusal")])
    assert run_turn(intake, "something off topic", llm, KNOWN, FIRM).reply == REFUSAL_REPLY


def test_tool_loop_is_bounded():
    intake = new_intake()
    llm = FakeLLM(
        [resp(tool("record_intake_details", details(), f"t{i}")) for i in range(MAX_TOOL_ROUNDS)]
    )
    result = run_turn(intake, "msg", llm, KNOWN, FIRM)
    assert result.reply == LOOP_LIMIT_REPLY
    assert len(llm.calls) == MAX_TOOL_ROUNDS


def test_system_prompt_has_firm_details():
    intake = new_intake()
    llm = FakeLLM([resp(text("hi"))])
    run_turn(intake, "hello", llm, KNOWN, FIRM)
    system = llm.calls[0]["system"]
    assert "Hudson Row Legal" in system and "(555) 010-0199" in system
    assert "Never give legal advice" in system
