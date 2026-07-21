"""Tests for the recorder's contract core (tools/record.py).

The contract core is pure (no IO) and is the dojo lift-target:
mint_id, mint_envelope, draft_to_record, serialize_record. Validation
itself is NOT tested here — it lives in the vendored validator (see
test_decision_validator.py); these tests only cross-check that minted
records satisfy it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent

record_tool = load_module(
    "record_tool", PROJECT_ROOT / "template" / "tools" / "record.py"
)
dv = load_module(
    "decision_validator",
    PROJECT_ROOT / "guard" / ".github" / "guards" / "decision_validator.py",
)

NOW = dt.datetime(2026, 7, 21, 14, 32, 5, tzinfo=dt.timezone.utc)


def draft() -> dict:
    """A draft record: the schema minus tool-minted fields, plus slug."""
    return {
        "slug": "agent-access",
        "project": "factory",
        "question": "How do agent environments access the preference repo?",
        "context": "session-local facts informing the options",
        "options": [
            {
                "slot": 1,
                "label": "read-only deploy key",
                "role": "prediction+recommendation",
                "rules_cited": [],
                "reasoning": "integrity via least privilege",
            },
            {"slot": 2, "label": "full-access PAT", "if_clause": "if speed"},
        ],
        "prediction_stream": "cold",
        "artifact_ref": None,
        "chosen_slot": 1,
        "chosen": "read-only deploy key",
        "correction": False,
        "rejections": [
            {
                "option": "full-access PAT",
                "reason": "blast radius",
                "status": "presumed-false",
                "reason_class": "TBD",
            }
        ],
        "outcome": "hit",
    }


def test_mint_id_format() -> None:
    assert record_tool.mint_id("agent-access", NOW) == "20260721T143205Z-agent-access"


@pytest.mark.parametrize(
    "bad_slug",
    ["Agent-Access", "agent_access", "agent access", "", "a" * 41],
)
def test_mint_id_rejects_bad_slugs(bad_slug: str) -> None:
    with pytest.raises(ValueError):
        record_tool.mint_id(bad_slug, NOW)


def test_mint_envelope() -> None:
    envelope = record_tool.mint_envelope("agent-access", NOW)
    assert envelope == {
        "v": 1,
        "type": "decision",
        "id": "20260721T143205Z-agent-access",
    }


def test_draft_to_record_mints_and_validates() -> None:
    record = record_tool.draft_to_record(
        draft(),
        NOW,
        session="session_01ABC",
        preference_commit="0" * 40,
    )
    assert record["id"] == "20260721T143205Z-agent-access"
    assert record["date"] == "2026-07-21"
    assert record["session"] == "session_01ABC"
    assert record["preference_set"] == {"commit": "0" * 40}
    assert "slug" not in record
    assert dv.validate_record(record, filename_stem=record["id"]) == []


def test_draft_values_win_over_minted_defaults() -> None:
    d = draft()
    d["session"] = "session_from_chat"
    d["preference_set"] = {"commit": "f" * 40}
    record = record_tool.draft_to_record(
        d, NOW, session="ignored", preference_commit="0" * 40
    )
    assert record["session"] == "session_from_chat"
    assert record["preference_set"] == {"commit": "f" * 40}


def test_draft_without_slug_is_an_error() -> None:
    d = draft()
    del d["slug"]
    with pytest.raises(ValueError):
        record_tool.draft_to_record(d, NOW)


def test_record_field_order_groups_input_before_output() -> None:
    record = record_tool.draft_to_record(draft(), NOW)
    keys = list(record.keys())
    assert keys[:3] == ["v", "type", "id"]
    assert keys.index("question") < keys.index("chosen_slot")
    assert keys.index("prediction_stream") < keys.index("outcome")


def test_unknown_draft_fields_are_preserved() -> None:
    d = draft()
    d["some_future_field"] = {"nested": True}
    record = record_tool.draft_to_record(d, NOW)
    assert record["some_future_field"] == {"nested": True}


def test_serialize_record_round_trips() -> None:
    record = record_tool.draft_to_record(draft(), NOW)
    text = record_tool.serialize_record(record)
    assert text.endswith("\n")
    assert json.loads(text) == record
    # Serialization must preserve the constructed field order.
    assert text.index('"question"') < text.index('"chosen_slot"')


def test_repo_url_tail_matches_across_url_forms() -> None:
    tail = record_tool.repo_url_tail
    assert tail("https://github.com/acme/decision-memory.git") == (
        "acme/decision-memory"
    )
    assert tail("git@github.com:acme/decision-memory.git") == ("acme/decision-memory")
    # Managed environments rewrite remotes through a local proxy.
    assert tail("http://local_proxy@127.0.0.1:41729/git/acme/decision-memory") == (
        "acme/decision-memory"
    )
    assert tail("https://github.com/acme/OTHER") != tail(
        "https://github.com/acme/decision-memory"
    )
