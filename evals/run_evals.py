"""Run scripted intake conversations against the real model and score them.

    ANTHROPIC_API_KEY=... python evals/run_evals.py [--min-pass 0.85]

Each case plays scripted client turns through the same agent loop the app
uses (guardrails included), then checks the structured result. Writes a
markdown report to evals/results/latest.md and exits non zero below the
pass threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.agent import run_turn  # noqa: E402
from app.conflicts import Party  # noqa: E402
from app.llm import AnthropicLLM  # noqa: E402
from app.models import Intake, IntakeStatus, Urgency  # noqa: E402
from app.services import SEED_CONFLICTS  # noqa: E402

FIRM = {"name": "Hudson Row Legal", "phone": "(555) 010-0199"}
KNOWN = [Party(n, r, m) for n, r, m in SEED_CONFLICTS]


def blank_intake() -> Intake:
    return Intake(
        transcript=[], chat=[], adverse_parties=[], key_facts=[], conflict_matches=[],
        guardrail_flags=[], turns=0, status=IntakeStatus.in_progress,
        urgency=Urgency.normal, in_custody="unknown", client_name="", practice_area="",
        phone="", email="", county="", deadline="", summary="", recommended_next_step="",
    )  # fmt: skip


def check(case: dict, intake: Intake, replies: list[str]) -> list[tuple[str, bool, str]]:
    exp = case["expect"]
    out: list[tuple[str, bool, str]] = []
    last = replies[-1].lower() if replies else ""
    all_replies = " ".join(replies).lower()

    if "practice_area" in exp:
        out.append(("practice_area", intake.practice_area == exp["practice_area"],
                    intake.practice_area or "(empty)"))  # fmt: skip
    if "urgency_in" in exp:
        out.append(("urgency", intake.urgency.value in exp["urgency_in"], intake.urgency.value))
    if "in_custody" in exp:
        out.append(("in_custody", intake.in_custody == exp["in_custody"], intake.in_custody))
    if "status_in" in exp:
        out.append(("status", intake.status.value in exp["status_in"], intake.status.value))
    if "adverse_party_contains" in exp:
        joined = " ".join(intake.adverse_parties).lower()
        out.append(("adverse_party", exp["adverse_party_contains"] in joined, joined or "(none)"))
    if "client_name_contains" in exp:
        name = intake.client_name.lower()
        out.append(("client_name", exp["client_name_contains"] in name, intake.client_name))
    if "county_contains" in exp:
        out.append(("county", exp["county_contains"] in intake.county.lower(), intake.county))
    if exp.get("reply_mentions_phone"):
        out.append(("reply_gives_phone", "010-0199" in all_replies, "firm phone in replies"))
    for banned in exp.get("reply_must_not_contain", []):
        out.append((f"reply_avoids '{banned[:30]}'", banned not in all_replies, ""))
    if "guardrail_replacements" in exp:
        n = len(intake.guardrail_flags)
        out.append(("no_guardrail_needed", n == exp["guardrail_replacements"], f"{n} replaced"))
    for secret in exp.get("fields_must_not_contain", []):
        stored = json.dumps(
            [intake.client_name, intake.phone, intake.email, intake.key_facts, intake.summary]
        )
        out.append((f"not_stored '{secret}'", secret not in stored, ""))
    if not last:
        out.append(("got_reply", False, "empty reply"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-pass", type=float, default=0.85)
    parser.add_argument("--only", help="run a single case id")
    args = parser.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set; evals need the real model.", file=sys.stderr)
        return 2
    llm = AnthropicLLM(
        api_key=key,
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        effort=os.environ.get("ANTHROPIC_EFFORT", "low"),
        max_tokens=2048,
    )

    cases = json.loads((ROOT / "cases.json").read_text())
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]

    rows, passed, total = [], 0, 0
    started = time.time()
    for case in cases:
        intake = blank_intake()
        replies = []
        for turn in case["turns"]:
            replies.append(run_turn(intake, turn, llm, KNOWN, FIRM).reply)
        results = check(case, intake, replies)
        ok = sum(1 for _, good, _ in results if good)
        passed += ok
        total += len(results)
        status = "PASS" if ok == len(results) else "FAIL"
        print(f"{status} {case['id']}: {ok}/{len(results)}")
        for name, good, detail in results:
            if not good:
                print(f"    x {name} ({detail})")
        rows.append((case, results, replies[-1] if replies else ""))

    rate = passed / total if total else 0.0
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    lines = [
        "# Intake eval results",
        "",
        f"Model: `{llm.model}` (effort {llm.effort}) · {len(cases)} cases · "
        f"{passed}/{total} checks passed ({rate:.0%}) · {time.time() - started:.0f}s",
        "",
        "| Case | Checks | Failed |",
        "|---|---|---|",
    ]
    for case, results, _ in rows:
        failed = ", ".join(n for n, g, _ in results if not g) or "none"
        good = sum(1 for _, g, _ in results if g)
        lines.append(f"| {case['id']} | {good}/{len(results)} | {failed} |")
    (out_dir / "latest.md").write_text("\n".join(lines) + "\n")
    print(f"\n{passed}/{total} checks passed ({rate:.0%})")
    return 0 if rate >= args.min_pass else 1


if __name__ == "__main__":
    sys.exit(main())
