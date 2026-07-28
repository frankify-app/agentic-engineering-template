"""Single-source validator for evidence-memory records.

This file is the one validation authority for the evidence-memory
contract. It lives in the agentic-engineering-template repo (evidence
subtemplate) and is copier-vendored into the evidence-memory repo,
where BOTH consumers import it:

- the CI guard (guards.py, next to this file), and
- the writer tool (tools/capture.py), which imports it from the
  data-repo clone at runtime.

Stdlib only, no dependencies — the vendored copy must keep working
even if the template repo disappears (fails soft: guard keeps working,
only updates stop).

The store-independent half — ID grammar, envelope, required-field
presence, corpus link integrity — lives in ``validator_core.py`` next
to this file, shared with every other store's validator. What stays
here is the evidence contract itself.

All validators return a list of human-readable error strings (empty =
valid) and TOLERATE unknown fields: new optional fields need no
migration.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validator_core  # noqa: E402  (path bootstrap above)

SCHEMA_VERSION = validator_core.SCHEMA_VERSION
RECORD_TYPE = "evidence"

# This store's link vocabulary. Deliberately NOT related/supersedes/
# drill_down_of: those carry decision-memory meanings, and a shared
# spelling with a different meaning is worse than two spellings.
LINK_FIELDS = ("same_symptom_as", "regression_of")
STORE_DIR = "records"

REQUIRED_FIELDS = (
    "v",
    "type",
    "id",
    "date",
    "symptom",
    "triage",
    "tier",
    "ticket",
    "environment",
    "expected",
    "observed",
    "rung",
)

# The meta-loop taxonomy plus 'feature': a feature-kata's capsule is a
# test failing because the capability is absent, which is TDD red — so
# bug-vs-feature is a triage value, not a separate record kind.
TRIAGE = frozenset({"code-bug", "doc-bug", "expectation-bug", "feature"})

# 1: capsule can be synthesized leak-free and lives in the public
# ticket. 2: capsule cannot be sanitized and lives here instead, the
# ticket carrying a leak-free summary.
TIERS = frozenset({1, 2})

# The filing ladder, monotonic: capacity decides how high it goes.
RUNGS = ("record", "ticket", "capsule", "repro-branch")
CAPSULE_RUNGS = frozenset({"capsule", "repro-branch"})

validate_id = validator_core.validate_id


def validate_envelope(record: dict) -> list[str]:
    """Check the universal envelope against this store's record type."""
    return validator_core.validate_envelope(record, RECORD_TYPE)


def _validate_symptom(record: dict, errors: list[str]) -> None:
    """The symptom is the grep-able fingerprint, so it must stay one line.

    Dedup starts with a human or an agent grepping this field across a
    local clone. A multi-line symptom is invisible to that grep for
    every line after the first, which defeats the field's only job.
    """
    symptom = record.get("symptom")
    if not isinstance(symptom, str) or not symptom.strip():
        errors.append("symptom: must be a non-empty string")
        return
    if "\n" in symptom:
        errors.append(
            "symptom: must be a single line — it is the grep-able "
            "fingerprint; detail belongs in observed/expected"
        )


def _validate_vocabularies(record: dict, errors: list[str]) -> None:
    triage = record.get("triage")
    if triage not in TRIAGE:
        errors.append(f"triage: {triage!r} not in {sorted(TRIAGE)}")

    tier = record.get("tier")
    if not isinstance(tier, int) or isinstance(tier, bool) or tier not in TIERS:
        errors.append(f"tier: {tier!r} not in {sorted(TIERS)}")

    rung = record.get("rung")
    if rung not in RUNGS:
        errors.append(f"rung: {rung!r} not in {list(RUNGS)}")


def _validate_placement(record: dict, errors: list[str]) -> None:
    """Tier 2 keeps its capsule here; that is the whole point of tier 2.

    A tier-2 record that reached the capsule rung with no capsule in
    the store means the capsule went somewhere public, which is the
    leak this tier exists to prevent.
    """
    if record.get("tier") != 2:
        return
    if record.get("rung") not in CAPSULE_RUNGS:
        return
    capsule = record.get("capsule")
    if not isinstance(capsule, str) or not capsule.strip():
        errors.append(
            "capsule: required for a tier-2 record at the capsule rung "
            "or above — tier 2 exists because the capsule cannot be "
            "public, so it has to be here"
        )


def _validate_ticket(record: dict, errors: list[str]) -> None:
    """Every record names its forge ticket: the store is memory, the
    forge is the actionable backlog, and the link is what keeps them
    from drifting into two trackers."""
    ticket = record.get("ticket")
    if not isinstance(ticket, str) or not ticket.startswith("http"):
        errors.append("ticket: must be the forge ticket URL")


def _validate_links_point_backward(record: dict, errors: list[str]) -> None:
    """Links only ever point at older records.

    Records are immutable, so an earlier record can never gain an edge
    to a later one; every link is therefore backward by construction.
    IDs lead with a UTC timestamp, so this is checkable from the IDs
    alone — no corpus needed. Ties are tolerated: two records minted in
    the same second are not evidence of a forward link.
    """
    record_id = record.get("id")
    if not isinstance(record_id, str) or not validator_core.ID_RE.match(record_id):
        return
    own_stamp = record_id.split("-", 1)[0]
    for field in LINK_FIELDS:
        ref = record.get(field)
        if not isinstance(ref, str) or not validator_core.ID_RE.match(ref):
            continue
        if ref.split("-", 1)[0] > own_stamp:
            errors.append(
                f"{field}: points to {ref!r}, which is newer than this "
                "record — links are backward-only"
            )


def validate_record(record: object, filename_stem: str | None = None) -> list[str]:
    """Validate a single evidence record against the full contract.

    Returns a list of error strings; empty means valid. Unknown fields
    are tolerated. When ``filename_stem`` is given, the record's ``id``
    must equal it (ID = filename stem, always).
    """
    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    errors = validate_envelope(record)
    errors.extend(validator_core.validate_required(record, REQUIRED_FIELDS))
    if filename_stem is not None and record.get("id") != filename_stem:
        errors.append(
            f"id: {record.get('id')!r} does not equal the filename stem "
            f"{filename_stem!r}"
        )
    _validate_symptom(record, errors)
    _validate_vocabularies(record, errors)
    _validate_placement(record, errors)
    _validate_ticket(record, errors)
    _validate_links_point_backward(record, errors)
    return errors


def validate_corpus(records: dict) -> list[str]:
    """Cross-record checks: no link into a record outside the corpus.

    ``records`` maps record ID -> record dict (normally the whole
    ``records/`` directory).
    """
    return validator_core.validate_corpus(records, LINK_FIELDS, STORE_DIR)
