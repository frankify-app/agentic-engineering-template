"""Tests for the shared record contract core (``record_core.py``).

The core is what a second store's writer composes on: the universal
envelope/ID grammar and serialization, carrying no vocabulary from any
one store's schema. ``test_record_core.py`` covers the decision
writer's own surface and is the regression guard that extracting this
core did not change it.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
CORE_PATH = PROJECT_ROOT / "decision-memory" / "tools" / "record_core.py"

core = load_module("record_core", CORE_PATH)

NOW = dt.datetime(2026, 7, 21, 14, 32, 5, tzinfo=dt.timezone.utc)


def test_mint_envelope_takes_the_record_type() -> None:
    """The seam itself: the envelope is the universal write format, so
    the type is an argument rather than a module constant."""
    assert core.mint_envelope("capsule-leak", NOW, "evidence") == {
        "v": 1,
        "type": "evidence",
        "id": "20260721T143205Z-capsule-leak",
    }


def test_mint_id_is_type_independent() -> None:
    assert core.mint_id("capsule-leak", NOW) == "20260721T143205Z-capsule-leak"


@pytest.mark.parametrize(
    "bad_slug",
    ["Capsule-Leak", "capsule_leak", "capsule leak", "", "a" * 41],
)
def test_mint_id_rejects_bad_slugs(bad_slug: str) -> None:
    with pytest.raises(ValueError):
        core.mint_id(bad_slug, NOW)


def test_order_fields_applies_the_callers_field_order() -> None:
    """Field order is per-store policy, so the core takes it as data."""
    ordered = core.order_fields({"notes": "n", "id": "x", "v": 1}, ("v", "id"))
    assert list(ordered) == ["v", "id", "notes"]


def test_order_fields_keeps_unknown_fields_after_the_known_ones() -> None:
    ordered = core.order_fields({"extra": 1, "v": 1}, ("v", "id"))
    assert list(ordered) == ["v", "extra"]


def test_serialize_record_round_trips() -> None:
    import json

    text = core.serialize_record({"v": 1, "type": "evidence", "id": "x"})
    assert text.endswith("\n")
    assert json.loads(text) == {"v": 1, "type": "evidence", "id": "x"}


def test_the_core_carries_no_store_specific_vocabulary() -> None:
    """Guard on the seam, not on the behavior.

    A term from one store's schema appearing here means the split
    leaked, and every later store inherits the leak. Cheaper to catch
    as a string than as a design review.
    """
    source = CORE_PATH.read_text().lower()
    for term in ("preference", "prediction", "chosen_slot", "rejection", "capsule"):
        assert term not in source, f"contract core mentions {term!r}"
