"""Conflict of interest screening.

Under NY Rule of Professional Conduct 1.18 a firm must screen prospective
clients for conflicts, ideally before learning much about the matter. Names
are normalized (case, punctuation, corporate suffixes, word order) and
compared with a fuzzy ratio so "Smith, John" matches "John Smith" and
"Acme Corp." matches "ACME Corporation".
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

SUFFIXES = {
    "llc", "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "llp", "pllc", "pc", "lp", "jr", "sr", "ii", "iii", "the",
}  # fmt: skip

MATCH_THRESHOLD = 0.88


def normalize(name: str) -> str:
    text = name.lower()
    # "Smith, John" -> "john smith"
    if text.count(",") == 1:
        last, first = (part.strip() for part in text.split(","))
        if first and last and len(first.split()) <= 2:
            text = f"{first} {last}"
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t not in SUFFIXES]
    return " ".join(sorted(tokens))


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


@dataclass(frozen=True)
class Party:
    name: str
    relationship_type: str
    matter: str = ""


@dataclass(frozen=True)
class ConflictMatch:
    query: str
    matched_name: str
    relationship_type: str
    matter: str
    score: float

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "matched_name": self.matched_name,
            "relationship_type": self.relationship_type,
            "matter": self.matter,
            "score": round(self.score, 2),
        }


def check_conflicts(
    client_name: str, adverse_parties: list[str], known: list[Party]
) -> list[ConflictMatch]:
    """Flag known parties that could make representation a conflict.

    * A prospective client's adversary who is our client -> conflict.
    * A prospective client who is a known adverse party -> conflict.
    """
    matches: list[ConflictMatch] = []
    for party in known:
        for name in adverse_parties:
            if party.relationship_type in ("client", "former_client"):
                score = similarity(name, party.name)
                if score >= MATCH_THRESHOLD:
                    matches.append(
                        ConflictMatch(
                            name, party.name, party.relationship_type, party.matter, score
                        )
                    )
        if client_name and party.relationship_type == "adverse":
            score = similarity(client_name, party.name)
            if score >= MATCH_THRESHOLD:
                matches.append(
                    ConflictMatch(client_name, party.name, "adverse", party.matter, score)
                )
    # One entry per known party, best score first.
    best: dict[str, ConflictMatch] = {}
    for m in sorted(matches, key=lambda m: -m.score):
        best.setdefault(m.matched_name, m)
    return list(best.values())
