"""The eval harness itself is tested offline, so CI catches a broken scorer."""

import importlib.util
import json
from pathlib import Path

from app.models import IntakeStatus, Urgency

ROOT = Path(__file__).resolve().parents[2] / "evals"
spec = importlib.util.spec_from_file_location("run_evals", ROOT / "run_evals.py")
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)


def test_cases_file_is_well_formed():
    cases = json.loads((ROOT / "cases.json").read_text())
    assert len(cases) >= 8
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["turns"] and c["expect"]


def test_scorer_passes_good_and_fails_bad():
    case = {
        "expect": {
            "practice_area": "immigration",
            "urgency_in": ["emergency"],
            "in_custody": "yes",
            "fields_must_not_contain": ["123-45-6789"],
            "reply_must_not_contain": ["roses are red"],
        }
    }
    good = run_evals.blank_intake()
    good.practice_area = "immigration"
    good.urgency = Urgency.emergency
    good.in_custody = "yes"
    assert all(ok for _, ok, _ in run_evals.check(case, good, ["Please call us."]))

    bad = run_evals.blank_intake()
    bad.status = IntakeStatus.in_progress
    bad.key_facts = ["SSN 123-45-6789"]
    results = dict((n, ok) for n, ok, _ in run_evals.check(case, bad, ["Roses are red..."]))
    assert results["practice_area"] is False
    assert results["not_stored '123-45-6789'"] is False
    assert results["reply_avoids 'roses are red'"] is False
