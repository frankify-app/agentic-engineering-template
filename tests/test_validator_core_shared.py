"""Tests for the shared validation core (``validator_core.py``).

The mirror of ``record_core.py`` on the reading side: meta#13 rules
that one writer core and one validator core serve every store, and
only lifecycle policy differs per store. What lives here is the part
that cannot know which store it is checking — ID grammar, the
envelope, required-field presence, and link integrity across a corpus.

``test_decision_validator.py`` covers the decision contract itself and
is the regression guard that extracting this core did not change it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
CORE_PATH = (
    PROJECT_ROOT / "decision-memory" / ".github" / "guards" / "validator_core.py"
)

core = load_module("validator_core", CORE_PATH)

VALID_ID = "20260721T143205Z-agent-access"


def test_validate_envelope_takes_the_expected_record_type() -> None:
    """The seam: which type is correct is the store's policy, not the
    core's, so it arrives as an argument."""
    record = {"v": 1, "type": "evidence", "id": VALID_ID}
    assert core.validate_envelope(record, "evidence") == []


def test_validate_envelope_rejects_a_foreign_record_type() -> None:
    record = {"v": 1, "type": "decision", "id": VALID_ID}
    errors = core.validate_envelope(record, "evidence")
    assert len(errors) == 1
    assert "evidence" in errors[0]


@pytest.mark.parametrize("bad_v", [0, -1, "1", True, None])
def test_validate_envelope_rejects_a_bad_schema_version(bad_v: object) -> None:
    record = {"v": bad_v, "type": "evidence", "id": VALID_ID}
    assert any(e.startswith("v:") for e in core.validate_envelope(record, "evidence"))


def test_validate_id_is_type_independent() -> None:
    assert core.validate_id(VALID_ID) == []


@pytest.mark.parametrize(
    "bad_id",
    [
        "20260721T143205Z-Agent-Access",
        "20260721-agent-access",
        "agent-access",
        "20260721T143205Z-" + "a" * 41,
        42,
    ],
)
def test_validate_id_rejects_bad_ids(bad_id: object) -> None:
    assert core.validate_id(bad_id) != []


def test_validate_required_reports_each_missing_field() -> None:
    errors = core.validate_required({"v": 1}, ("v", "symptom", "tier"))
    assert errors == [
        "symptom: required field missing",
        "tier: required field missing",
    ]


def test_validate_corpus_takes_the_stores_link_fields() -> None:
    """Link vocabulary is per-store — evidence links by
    same_symptom_as and regression_of, decisions by related and
    friends — so the core is told which fields to walk."""
    records = {
        "a": {"same_symptom_as": "missing-record"},
        "b": {"same_symptom_as": "a"},
    }
    errors = core.validate_corpus(records, ("same_symptom_as",), "records")
    assert errors == [
        "a: same_symptom_as points to 'missing-record', "
        "which does not exist in records/"
    ]


def test_validate_corpus_walks_list_valued_link_fields() -> None:
    records = {"a": {"related": ["b", "gone"]}, "b": {}}
    errors = core.validate_corpus(records, ("related",), "decisions")
    assert len(errors) == 1
    assert "'gone'" in errors[0]


def test_the_core_carries_no_store_specific_vocabulary() -> None:
    """Same guard as the writer core, for the same reason: a leak here
    is inherited by every store that composes on it."""
    source = CORE_PATH.read_text().lower()
    for term in ("preference", "prediction", "chosen_slot", "rejection", "capsule"):
        assert term not in source, f"validation core mentions {term!r}"
