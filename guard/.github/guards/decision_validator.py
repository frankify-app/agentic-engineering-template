"""Single-source validator for decision-memory records.

This file is the one validation authority for the decision-memory
contract. It lives in the agentic-engineering-template repo (guard
subtemplate) and is copier-vendored into the decision-memory repo,
where BOTH consumers import it:

- the CI guard (guards.py, next to this file), and
- the writer tool (tools/record.py in template-instantiated repos),
  which imports it from the data-repo clone at runtime.

Stdlib only, no dependencies — the vendored copy must keep working
even if the template repo disappears (fails soft: guard keeps
working, only updates stop).

All validators return a list of human-readable error strings (empty =
valid) and TOLERATE unknown fields: new optional fields need no
migration.
"""

from __future__ import annotations

import re

SCHEMA_VERSION = 1
RECORD_TYPE = "decision"

REQUIRED_FIELDS = (
    "v",
    "type",
    "id",
    "date",
    "project",
    "question",
    "options",
    "prediction_stream",
    "artifact_ref",
    "chosen_slot",
    "chosen",
    "rejections",
    "outcome",
)

PREDICTION_ROLES = frozenset({"prediction", "prediction+recommendation"})
OPTION_ROLES = PREDICTION_ROLES | frozenset({"recommendation", "wildcard"})
PREDICTION_STREAMS = frozenset({"preference-driven", "cold"})
OUTCOMES = frozenset({"hit", "miss", "near-tie", "refined"})
REJECTION_STATUSES = frozenset({"operative", "presumed-false"})
# Reason provenance for presumed-false rejections: the model records
# the most-likely reason and DECLARES where it came from; a null
# reason is only valid when explicitly declared "none" — never a lazy
# default.
PRESUMED_REASON_SOURCES = frozenset({"if_clause", "inferred", "none"})
# Operative reasons are decider-confirmed only — deliberately NO
# 'inferred' tier (an inferred why-chosen belongs in the chosen
# option's own reasoning and in the rejections). 'none' declares a
# silent pick: the decider chose without stating a reason.
OPERATIVE_REASON_SOURCES = frozenset({"stated", "none"})

MAX_SLUG_LENGTH = 40
ID_RE = re.compile(r"^(\d{8}T\d{6}Z)-([a-z0-9]+(?:-[a-z0-9]+)*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Single source for the preferences counter-line grammar
# ("[confirmed: N, last: YYYY-MM-DD]"): the guard's counter-math check
# and the writer's pref-confirm bumps both consume this regex.
COUNTER_RE = re.compile(r"\[confirmed: (\d+), last: (\d{4}-\d{2}-\d{2})\]")

# ~1-2k-token hard budget on preferences.md (ticket §5); estimated at
# the common ~4 chars/token heuristic — deliberately coarse, the budget
# is a forcing function, not an accounting system.
PREFERENCES_TOKEN_BUDGET = 2000
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Coarse token estimate for the preferences budget check."""
    return len(text) // CHARS_PER_TOKEN


def validate_id(record_id: object) -> list[str]:
    """Check the ID grammar: <YYYYMMDDTHHMMSSZ>-<kebab-slug>, slug <= 40."""
    if not isinstance(record_id, str):
        return ["id: must be a string"]
    match = ID_RE.match(record_id)
    if not match:
        return [
            f"id: {record_id!r} does not match "
            "<UTC-timestamp>Z-<kebab-slug> (lowercase kebab-case slug)"
        ]
    slug = match.group(2)
    if len(slug) > MAX_SLUG_LENGTH:
        return [f"id: slug {slug!r} is {len(slug)} chars (max {MAX_SLUG_LENGTH})"]
    return []


def validate_envelope(record: dict) -> list[str]:
    """Check the universal envelope: v, type, id."""
    errors: list[str] = []
    v = record.get("v")
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        errors.append("v: must be a positive integer schema version")
    record_type = record.get("type")
    if record_type != RECORD_TYPE:
        errors.append(
            f"type: must be {RECORD_TYPE!r} in this repo, got {record_type!r}"
        )
    errors.extend(validate_id(record.get("id")))
    return errors


def _validate_options(record: dict, errors: list[str]) -> dict | None:
    """Validate the options block; return the prediction option if unique."""
    options = record.get("options")
    if not isinstance(options, list) or not options:
        errors.append("options: must be a non-empty list")
        return None
    prediction_options = []
    seen_slots: set[int] = set()
    for i, option in enumerate(options):
        if not isinstance(option, dict):
            errors.append(f"options[{i}]: must be an object")
            continue
        slot = option.get("slot")
        if not isinstance(slot, int) or isinstance(slot, bool):
            errors.append(f"options[{i}].slot: must be an integer")
        elif slot in seen_slots:
            errors.append(f"options[{i}].slot: duplicate slot {slot}")
        else:
            seen_slots.add(slot)
        label = option.get("label")
        if not isinstance(label, str) or not label:
            errors.append(f"options[{i}].label: must be a non-empty string")
        role = option.get("role")
        if role is not None and role not in OPTION_ROLES:
            errors.append(f"options[{i}].role: {role!r} not in {sorted(OPTION_ROLES)}")
        if role in PREDICTION_ROLES:
            prediction_options.append(option)
    if len(prediction_options) != 1:
        errors.append(
            "options: exactly one option must carry a prediction role "
            f"({len(prediction_options)} found)"
        )
        return None
    return prediction_options[0]


def _validate_streams(
    record: dict, prediction_option: dict | None, errors: list[str]
) -> None:
    stream = record.get("prediction_stream")
    if stream not in PREDICTION_STREAMS:
        errors.append(
            f"prediction_stream: {stream!r} not in {sorted(PREDICTION_STREAMS)}"
        )
        return
    if prediction_option is None:
        return
    rules_cited = prediction_option.get("rules_cited", [])
    if not isinstance(rules_cited, list):
        errors.append("options[].rules_cited: must be a list")
        return
    if stream == "preference-driven" and not rules_cited:
        errors.append(
            "rules_cited: must be non-empty when prediction_stream is preference-driven"
        )
    if stream == "cold" and rules_cited:
        errors.append(
            "rules_cited: must be empty when prediction_stream is cold "
            "(cold means no preference rule predicted this)"
        )


def _validate_ruling(
    record: dict, prediction_option: dict | None, errors: list[str]
) -> None:
    chosen_slot = record.get("chosen_slot")
    if not isinstance(chosen_slot, int) or isinstance(chosen_slot, bool):
        errors.append("chosen_slot: must be an integer")
        chosen_slot = None
    chosen = record.get("chosen")
    if not isinstance(chosen, str) or not chosen:
        errors.append("chosen: must be a non-empty string")

    outcome = record.get("outcome")
    if outcome not in OUTCOMES:
        errors.append(f"outcome: {outcome!r} not in {sorted(OUTCOMES)}")
    elif (
        outcome != "near-tie"
        and prediction_option is not None
        and chosen_slot is not None
    ):
        # Scored outcomes must match the slots. Near-ties are exempt by
        # design (never scored as misses); 'refined' requires a slot
        # MISMATCH like miss — the chosen answer CONTAINS the
        # prediction plus an extension, distinguished from miss only by
        # that containment judgment (same slot would be a plain hit).
        hit = chosen_slot == prediction_option.get("slot")
        if outcome == "hit" and not hit:
            errors.append(
                "outcome: 'hit' but chosen_slot differs from the prediction slot"
            )
        if outcome in ("miss", "refined") and hit:
            errors.append(
                f"outcome: {outcome!r} but chosen_slot equals the "
                "prediction slot (that is a hit)"
            )

    # operative_reason is required when a listed non-prediction option
    # won — unless the pick was declared silent.
    operative_source = record.get("operative_reason_source")
    if operative_source is not None:
        if operative_source not in OPERATIVE_REASON_SOURCES:
            errors.append(
                f"operative_reason_source: {operative_source!r} not in "
                f"{sorted(OPERATIVE_REASON_SOURCES)} (operative reasons are "
                "decider-confirmed only — no inferred tier)"
            )
        elif operative_source == "none":
            if record.get("operative_reason") is not None:
                errors.append(
                    "operative_reason: must be null when "
                    "operative_reason_source is 'none' (silent pick)"
                )
        elif not record.get("operative_reason"):
            errors.append(
                "operative_reason: must be a non-empty string when "
                "operative_reason_source is 'stated'"
            )
    options = record.get("options")
    if isinstance(options, list) and chosen_slot is not None:
        chosen_option = next(
            (
                o
                for o in options
                if isinstance(o, dict) and o.get("slot") == chosen_slot
            ),
            None,
        )
        if (
            chosen_option is not None
            and chosen_option.get("role") not in PREDICTION_ROLES
            and not record.get("operative_reason")
            and operative_source != "none"
        ):
            errors.append(
                "operative_reason: required when a listed non-prediction "
                "option is chosen (declare operative_reason_source 'none' "
                "for a silent pick)"
            )

    rejections = record.get("rejections")
    if not isinstance(rejections, list):
        errors.append("rejections: must be a list")
    else:
        for i, rejection in enumerate(rejections):
            if not isinstance(rejection, dict):
                errors.append(f"rejections[{i}]: must be an object")
                continue
            if not isinstance(rejection.get("option"), str) or not rejection["option"]:
                errors.append(f"rejections[{i}].option: must be a non-empty string")
            status = rejection.get("status")
            if status not in REJECTION_STATUSES:
                errors.append(
                    f"rejections[{i}].status: {status!r} not in "
                    f"{sorted(REJECTION_STATUSES)}"
                )
                continue
            reason = rejection.get("reason")
            source = rejection.get("reason_source")
            if status == "operative":
                # Operative reasons are decider-stated by definition.
                if source not in (None, "stated"):
                    errors.append(
                        f"rejections[{i}].reason_source: {source!r} — "
                        "operative rejections are stated by definition"
                    )
                if not isinstance(reason, str) or not reason:
                    errors.append(
                        f"rejections[{i}].reason: operative rejections "
                        "require the stated reason, verbatim"
                    )
            else:  # presumed-false
                if source not in PRESUMED_REASON_SOURCES:
                    errors.append(
                        f"rejections[{i}].reason_source: {source!r} not in "
                        f"{sorted(PRESUMED_REASON_SOURCES)} (required for "
                        "presumed-false rejections)"
                    )
                elif source == "none":
                    if reason is not None:
                        errors.append(
                            f"rejections[{i}].reason: must be null when "
                            "reason_source is 'none'"
                        )
                elif not isinstance(reason, str) or not reason:
                    errors.append(
                        f"rejections[{i}].reason: must be a non-empty "
                        f"string when reason_source is {source!r} (declare "
                        "reason_source 'none' if nothing is inferable)"
                    )


def _validate_optional_fields(record: dict, errors: list[str]) -> None:
    date = record.get("date")
    if date is not None and (not isinstance(date, str) or not DATE_RE.match(date)):
        errors.append(f"date: {date!r} is not YYYY-MM-DD")

    project = record.get("project")
    if project is not None and (not isinstance(project, str) or not project):
        errors.append("project: must be a non-empty string")

    artifact_ref = record.get("artifact_ref")
    if artifact_ref is not None and not isinstance(artifact_ref, dict):
        errors.append("artifact_ref: must be an object or null")

    correction = record.get("correction")
    if correction is not None and not isinstance(correction, bool):
        errors.append("correction: must be a boolean")

    closure_of = record.get("closure_of")
    if closure_of is not None and (
        not isinstance(closure_of, int)
        or isinstance(closure_of, bool)
        or closure_of < 1
    ):
        errors.append(f"closure_of: {closure_of!r} must be a positive PR number")

    related = record.get("related")
    if related is not None:
        if not isinstance(related, list):
            errors.append("related: must be a list of record IDs")
        else:
            for ref in related:
                for err in validate_id(ref):
                    errors.append(f"related: {err}")

    for link_field in ("supersedes", "drill_down_of"):
        ref = record.get(link_field)
        if ref is not None:
            for err in validate_id(ref):
                errors.append(f"{link_field}: {err}")


def validate_record(record: object, filename_stem: str | None = None) -> list[str]:
    """Validate a single decision record against the full contract.

    Returns a list of error strings; empty means valid. Unknown fields
    are tolerated. When ``filename_stem`` is given, the record's ``id``
    must equal it (ID = filename stem, always).
    """
    if not isinstance(record, dict):
        return ["record: must be a JSON object"]
    errors = validate_envelope(record)
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"{field}: required field missing")
    if filename_stem is not None and record.get("id") != filename_stem:
        errors.append(
            f"id: {record.get('id')!r} does not equal the filename stem "
            f"{filename_stem!r}"
        )
    prediction_option = _validate_options(record, errors)
    _validate_streams(record, prediction_option, errors)
    _validate_ruling(record, prediction_option, errors)
    _validate_optional_fields(record, errors)
    return errors


def validate_corpus(records: dict) -> list[str]:
    """Cross-record checks: no dangling related/supersedes/drill_down_of.

    ``records`` maps record ID -> record dict (normally the whole
    ``decisions/`` directory).
    """
    errors: list[str] = []
    for record_id, record in sorted(records.items()):
        if not isinstance(record, dict):
            continue
        refs = []
        related = record.get("related")
        if isinstance(related, list):
            refs.extend(("related", ref) for ref in related)
        for link_field in ("supersedes", "drill_down_of"):
            ref = record.get(link_field)
            if ref is not None:
                refs.append((link_field, ref))
        for field, ref in refs:
            if ref not in records:
                errors.append(
                    f"{record_id}: {field} points to {ref!r}, "
                    "which does not exist in decisions/"
                )
    return errors


def check_preferences_budget(
    text: str, budget_tokens: int = PREFERENCES_TOKEN_BUDGET
) -> list[str]:
    """Enforce the hard token budget on preferences.md."""
    tokens = estimate_tokens(text)
    if tokens > budget_tokens:
        return [
            f"preferences.md: ~{tokens} tokens exceeds the {budget_tokens} "
            "budget — promote requires demote (merge or demote another "
            "rule to make room)"
        ]
    return []
