"""Fixture tests for the single-source decision-record validator.

The validator is the guard subtemplate's core (vendored into the
decision-memory repo via copier); every change to it must pass these
tests in this repo's CI before it can be vendored downstream.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
VALIDATOR_PATH = PROJECT_ROOT / "guard" / ".github" / "guards" / "decision_validator.py"

dv = load_module("decision_validator", VALIDATOR_PATH)


def valid_record() -> dict:
    """A schema-complete record (adapted from the ticket's real example)."""
    return {
        "v": 1,
        "type": "decision",
        "id": "20260715T143205Z-agent-access",
        "date": "2026-07-15",
        "project": "factory",
        "question": "How do agent environments access the preference repo?",
        "context": "session-local facts informing the options",
        "options": [
            {
                "slot": 1,
                "label": "read-only deploy key, human-approved writes",
                "role": "prediction+recommendation",
                "rules_cited": [],
                "reasoning": "integrity via least privilege",
            },
            {
                "slot": 2,
                "label": "full-access PAT everywhere",
                "if_clause": "if write friction matters more than blast radius",
            },
            {
                "slot": 3,
                "label": "local clone, manual sync",
                "if_clause": "if offline work dominates",
            },
        ],
        "prediction_stream": "cold",
        "preference_set": {"commit": "0000000000000000000000000000000000000000"},
        "artifact_ref": {
            "repo": "skills",
            "path": "skills/grilling/SKILL.md",
            "commit": "1111111111111111111111111111111111111111",
            "anchor": "#recording",
        },
        "session": "session_01ABC",
        "chosen_slot": 4,
        "chosen": "all agents as collaborators, PRs against main",
        "operative_reason": "write friction defeats seamless recording",
        "correction": False,
        "rejections": [
            {
                "option": "read-only deploy key",
                "reason": "write friction defeats seamless recording",
                "status": "operative",
                "reason_class": "TBD",
            },
            {
                "option": "full-access direct push",
                "reason": "agent could silently rewrite preference history",
                "status": "presumed-false",
                "reason_source": "inferred",
                "reason_class": "TBD",
            },
        ],
        "outcome": "miss",
        "drill_down_of": None,
        "related": [],
        "supersedes": None,
        "notes": "CI-enforced append-only replaces access control",
    }


def test_valid_record_passes() -> None:
    assert dv.validate_record(valid_record()) == []


def test_filename_stem_must_match_id() -> None:
    errors = dv.validate_record(valid_record(), filename_stem="20990101T000000Z-other")
    assert any("filename" in e for e in errors)
    assert (
        dv.validate_record(
            valid_record(), filename_stem="20260715T143205Z-agent-access"
        )
        == []
    )


@pytest.mark.parametrize("field", list(dv.REQUIRED_FIELDS))
def test_missing_required_field_fails(field: str) -> None:
    record = valid_record()
    del record[field]
    assert any(field in e for e in dv.validate_record(record))


def test_unknown_fields_tolerated() -> None:
    record = valid_record()
    record["closure_of"] = 2
    record["some_future_field"] = {"nested": True}
    assert dv.validate_record(record) == []


def test_bad_closure_of_rejected() -> None:
    record = valid_record()
    record["closure_of"] = "PR #2"
    assert any("closure_of" in e for e in dv.validate_record(record))


@pytest.mark.parametrize(
    "bad_id",
    [
        "20260715T143205Z-Agent-Access",  # uppercase
        "20260715T143205Z_agent",  # underscore separator
        "agent-access",  # missing timestamp
        "20260715T143205Z-" + "a" * 41,  # slug over 40 chars
    ],
)
def test_bad_id_rejected(bad_id: str) -> None:
    record = valid_record()
    record["id"] = bad_id
    assert any("id" in e for e in dv.validate_record(record))


def test_envelope_type_must_be_decision() -> None:
    record = valid_record()
    record["type"] = "note"
    assert any("type" in e for e in dv.validate_record(record))


def test_exactly_one_prediction_role_required() -> None:
    record = valid_record()
    record["options"][1]["role"] = "prediction"
    assert any("prediction" in e for e in dv.validate_record(record))

    record = valid_record()
    record["options"][0]["role"] = "recommendation"
    assert any("prediction" in e for e in dv.validate_record(record))


def test_rules_cited_iff_preference_driven() -> None:
    # preference-driven with empty rules_cited: fail
    record = valid_record()
    record["prediction_stream"] = "preference-driven"
    assert any("rules_cited" in e for e in dv.validate_record(record))

    # cold with non-empty rules_cited: fail
    record = valid_record()
    record["options"][0]["rules_cited"] = ["some rule"]
    assert any("rules_cited" in e for e in dv.validate_record(record))

    # preference-driven with cited rules: pass
    record = valid_record()
    record["prediction_stream"] = "preference-driven"
    record["options"][0]["rules_cited"] = ["some rule"]
    assert dv.validate_record(record) == []


def test_outcome_consistency_with_chosen_slot() -> None:
    # chosen_slot != prediction slot, outcome hit: inconsistent
    record = valid_record()
    record["outcome"] = "hit"
    assert any("outcome" in e for e in dv.validate_record(record))

    # chosen_slot == prediction slot, outcome miss: inconsistent
    record = valid_record()
    record["chosen_slot"] = 1
    record["operative_reason"] = None
    assert any("outcome" in e for e in dv.validate_record(record))

    # near-tie is never scored against the slots
    record = valid_record()
    record["outcome"] = "near-tie"
    assert dv.validate_record(record) == []


def test_operative_reason_required_for_listed_non_prediction_choice() -> None:
    record = valid_record()
    record["chosen_slot"] = 2
    record["operative_reason"] = None
    assert any("operative_reason" in e for e in dv.validate_record(record))


def test_rejection_status_vocabulary() -> None:
    record = valid_record()
    record["rejections"][0]["status"] = "maybe"
    assert any("status" in e for e in dv.validate_record(record))


def test_presumed_false_requires_reason_source() -> None:
    record = valid_record()
    del record["rejections"][1]["reason_source"]
    assert any("reason_source" in e for e in dv.validate_record(record))


def test_reason_source_none_requires_null_reason() -> None:
    # Declared-none with null reason: valid (silent MC pick, nothing
    # stated or inferable — never a filler string).
    record = valid_record()
    record["rejections"][1]["reason_source"] = "none"
    record["rejections"][1]["reason"] = None
    assert dv.validate_record(record) == []

    # none + a reason string is contradictory.
    record = valid_record()
    record["rejections"][1]["reason_source"] = "none"
    assert any("reason" in e for e in dv.validate_record(record))

    # Lazy null without the declaration is rejected.
    record = valid_record()
    record["rejections"][1]["reason"] = None
    record["rejections"][1]["reason_source"] = "inferred"
    assert any("reason" in e for e in dv.validate_record(record))


def test_if_clause_reason_source_accepted() -> None:
    record = valid_record()
    record["rejections"][1]["reason_source"] = "if_clause"
    record["rejections"][1]["reason"] = "if write friction matters more"
    assert dv.validate_record(record) == []


def test_operative_rejections_are_stated_by_definition() -> None:
    record = valid_record()
    record["rejections"][0]["reason_source"] = "inferred"
    assert any("operative" in e for e in dv.validate_record(record))

    record = valid_record()
    record["rejections"][0]["reason_source"] = "stated"
    assert dv.validate_record(record) == []


def test_refined_outcome_requires_slot_mismatch() -> None:
    # chosen differs from the prediction slot but CONTAINS the
    # prediction plus an extension: refined, not a miss.
    record = valid_record()
    record["outcome"] = "refined"
    assert dv.validate_record(record) == []

    # refined with chosen_slot == prediction slot is really a hit —
    # same slot rule as miss, distinguished only by containment.
    record = valid_record()
    record["chosen_slot"] = 1
    record["operative_reason"] = None
    record["outcome"] = "refined"
    assert any("refined" in e for e in dv.validate_record(record))


def test_corpus_dangling_references() -> None:
    a = valid_record()
    b = valid_record()
    b["id"] = "20260716T090000Z-follow-up"
    b["related"] = [a["id"]]
    b["drill_down_of"] = a["id"]
    corpus = {r["id"]: r for r in (a, b)}
    assert dv.validate_corpus(corpus) == []

    b["supersedes"] = "20990101T000000Z-missing"
    errors = dv.validate_corpus(corpus)
    assert any("supersedes" in e and "missing" in e for e in errors)


def test_preferences_budget() -> None:
    assert dv.check_preferences_budget("## Rules\n- one short rule\n") == []
    errors = dv.check_preferences_budget("x" * 50_000)
    assert any("promote requires demote" in e for e in errors)
