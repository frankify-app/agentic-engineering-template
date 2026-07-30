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

The store-independent half — ID grammar, envelope, required-field
presence, corpus link integrity — lives in ``validator_core.py`` next
to this file and is shared with every other store's validator. What
stays here is the decision contract itself.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import validator_core  # noqa: E402  (path bootstrap above)

SCHEMA_VERSION = validator_core.SCHEMA_VERSION
RECORD_TYPE = "decision"

# The store's own link vocabulary, walked by the corpus check.
LINK_FIELDS = ("related", "supersedes", "drill_down_of")
STORE_DIR = "decisions"

# Autonomous agent records: same schema, same append-only guarantee,
# outside the preference pipeline entirely. A run with no decider
# present is a prediction under the active set, not a ruling — so
# extraction never walks this directory and no record in it can bump a
# counter. Naming it for what it holds keeps `decisions/` meaning
# a-human-ruled.
PREDICTIONS_DIR = "predictions"

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

MAX_SLUG_LENGTH = validator_core.MAX_SLUG_LENGTH
ID_RE = validator_core.ID_RE
DATE_RE = validator_core.DATE_RE

# Single source for the preferences metadata-suffix grammar (see
# decision-memory/docs/conventions.md): one trailing bracket holding
# comma-separated `key: value` pairs. The guard's counter-math check
# and the writer's pref-confirm bumps both consume these.
#
# Parsed rather than pattern-matched so the key set is one tuple a
# reader can check against the doc, not a shape encoded in a regex.
METADATA_RE = re.compile(r"\[([^\]\[]*)\]\s*$")

COUNTER_KEY = "confirmed"
INDEPENDENT_KEY = "independent"
DATE_KEY = "last"

# Exactly these, on every rule, in this order. A closed set is what
# keeps the suffix from gaining keys nothing reads: adding one is a
# deliberate change here, with its consumer, rather than something a
# writer can introduce in passing.
SUFFIX_KEYS = (COUNTER_KEY, INDEPENDENT_KEY, DATE_KEY)


def parse_metadata(line: str) -> dict[str, str] | None:
    """Parse a rule line's trailing metadata bracket.

    Returns the key/value pairs, or None when the line carries no
    bracket or the bracket is not this grammar (a bare `[note]`, a
    markdown link). Values are returned as written; callers coerce.
    """
    match = METADATA_RE.search(line)
    if not match:
        return None
    pairs: dict[str, str] = {}
    for chunk in match.group(1).split(","):
        key, sep, value = chunk.partition(":")
        if not sep:
            return None
        pairs[key.strip()] = value.strip()
    return pairs or None


def format_metadata(pairs: dict[str, str]) -> str:
    """Render pairs back into a suffix, in SUFFIX_KEYS order."""
    body = ", ".join(f"{k}: {pairs[k]}" for k in SUFFIX_KEYS if k in pairs)
    return f"[{body}]"


def strip_metadata(line: str) -> str:
    """The rule text alone — what two rules are compared on."""
    return METADATA_RE.sub("", line).rstrip()


def counter_of(line: str) -> int | None:
    """The `confirmed` value of a rule line, if it has a valid one."""
    pairs = parse_metadata(line)
    if not pairs or COUNTER_KEY not in pairs:
        return None
    try:
        return int(pairs[COUNTER_KEY])
    except ValueError:
        return None


def check_metadata_suffix(line: str) -> str | None:
    """Return an error for a rule bullet whose suffix is malformed.

    Applied to every `- ` bullet in preferences.md, so a rule that
    silently lost its counters fails the guard instead of merging and
    reading as a rule nobody has ever confirmed.
    """
    pairs = parse_metadata(line)
    if pairs is None:
        return f"rule has no metadata suffix: {line.strip()!r}"
    if set(pairs) != set(SUFFIX_KEYS):
        missing = [key for key in SUFFIX_KEYS if key not in pairs]
        unknown = [key for key in pairs if key not in SUFFIX_KEYS]
        return (
            f"rule suffix must carry exactly {list(SUFFIX_KEYS)} "
            f"(missing {missing}, unknown {unknown}): {line.strip()!r}"
        )
    for key in (COUNTER_KEY, INDEPENDENT_KEY):
        if not pairs[key].isdigit():
            return f"rule suffix {key}={pairs[key]!r} is not a count: {line.strip()!r}"
    if not DATE_RE.fullmatch(pairs[DATE_KEY]):
        return (
            f"rule suffix {DATE_KEY}={pairs[DATE_KEY]!r} is not YYYY-MM-DD: "
            f"{line.strip()!r}"
        )
    if int(pairs[INDEPENDENT_KEY]) > int(pairs[COUNTER_KEY]):
        return (
            f"rule suffix has {INDEPENDENT_KEY} > {COUNTER_KEY} "
            f"({pairs[INDEPENDENT_KEY]} > {pairs[COUNTER_KEY]}): independent "
            f"confirmations are a subset of all of them: {line.strip()!r}"
        )
    return None


# ~1-2k-token hard budget on preferences.md (ticket §5); estimated at
# the common ~4 chars/token heuristic — deliberately coarse, the budget
# is a forcing function, not an accounting system.
PREFERENCES_TOKEN_BUDGET = 2000
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Coarse token estimate for the preferences budget check."""
    return len(text) // CHARS_PER_TOKEN


validate_id = validator_core.validate_id


def validate_envelope(record: dict) -> list[str]:
    """Check the universal envelope against this store's record type."""
    return validator_core.validate_envelope(record, RECORD_TYPE)


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
    errors.extend(validator_core.validate_required(record, REQUIRED_FIELDS))
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
    """Cross-record checks: no dangling link into a record that is not
    in the corpus.

    ``records`` maps record ID -> record dict (normally the whole
    ``decisions/`` directory).
    """
    return validator_core.validate_corpus(records, LINK_FIELDS, STORE_DIR)


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
