"""Batch extraction of preference rules from decision records.

Copier-vendored from the agentic-engineering-template decision-memory
subtemplate — change it there, pull via `copier update`.

Records are what happened; `preferences.md` is what the next session is
told to expect. Extraction is the bridge, and without it the corpus
grows while the rule set does not — every record lands
`prediction_stream: cold` because no rule was there to drive it, and
the replay gate has nothing to measure.

Extraction is a BATCH pass, never per-session. The evidence it looks
for is cross-session repetition: one session cannot tell a principle
from a one-off, so a per-session pass would structurally miss the thing
extraction exists to find. The batch is everything recorded since the
marker.

This module is the read side plus the marker. It emits a prioritized
batch as JSON and the skill
(`.agents/skills/extract-preferences/SKILL.md`) does the judgement —
the same split as the replay harness, and for the same reason: the
decisions live in pure functions that CI can test, and the part needing
a model stays outside them.

**Extraction never writes to `decisions/`.** It reads history and
proposes rules; the append-only guarantee is not negotiated here.

Stdlib only. Usage:

    python .github/store/extraction.py status
    python .github/store/extraction.py batch --out /tmp/batch.json
    python .github/store/extraction.py mark --record-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MARKER_FILENAME = "extraction-marker.json"
MARKER_KEY = "last_extracted_record_id"

# Queues, most informative first. A record lands in exactly one.
QUEUE_CORRECTIONS = "corrections"
QUEUE_MISSES = "misses"
QUEUE_REFINEMENTS = "refinements"
QUEUE_CONFIRMATIONS = "confirmations"
QUEUES = (QUEUE_CORRECTIONS, QUEUE_MISSES, QUEUE_REFINEMENTS, QUEUE_CONFIRMATIONS)

PREFERENCE_DRIVEN = "preference-driven"


class MarkerError(Exception):
    """Raised when `extraction-marker.json` is unusable."""


def marker_path(root: str = ".") -> str:
    return os.path.join(root, MARKER_FILENAME)


def load_marker(root: str = ".") -> str | None:
    """The last extracted record ID, or None if nothing has been extracted.

    A missing file means "never extracted" — a store that has not run
    extraction yet is not misconfigured, and requiring the file would
    make the first run a chicken-and-egg problem.
    """
    path = marker_path(root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MarkerError(f"{path}: unreadable or invalid JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise MarkerError(f"{path}: must contain a JSON object")
    value = loaded.get(MARKER_KEY)
    if value is not None and not isinstance(value, str):
        raise MarkerError(f"{path}: {MARKER_KEY} must be a record ID string or null")
    return value or None


def write_marker(root: str, record_id: str | None) -> str:
    """Point the marker at `record_id`. Returns the path written."""
    path = marker_path(root)
    body = {
        "_comment": (
            "Store-owned. The last decision record covered by an extraction "
            "pass; everything with a later ID is the next batch. Advanced by "
            "the final commit of an extraction PR, never by hand."
        ),
        MARKER_KEY: record_id,
    }
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    return path


def check_marker(root: str, record_ids: set[str]) -> list[str]:
    """Guard check: the marker must name a record that exists.

    A marker pointing at nothing would silently skip or re-process a
    whole batch, and the failure would look like "extraction found
    nothing" — the one outcome that is indistinguishable from success.
    """
    try:
        marker = load_marker(root)
    except MarkerError as exc:
        return [str(exc)]
    if marker is None:
        return []
    if marker not in record_ids:
        return [
            f"{MARKER_FILENAME}: {MARKER_KEY} is {marker!r}, which is not a "
            "record in decisions/ — the marker must name an existing record"
        ]
    return []


def unprocessed(records: list[dict], marker: str | None) -> list[dict]:
    """Records recorded after the marker, oldest first.

    IDs begin with a UTC timestamp and `decisions/` is append-only, so
    "later than the marker" is a plain string comparison over IDs. That
    is the whole reason the marker is a record ID and not a commit SHA:
    the question "which records are new" is answerable from the corpus
    itself, with no git archaeology and nothing to break when history
    is rewritten around it.
    """
    if marker is None:
        return list(records)
    return [record for record in records if str(record.get("id") or "") > marker]


def prediction_option(record: dict) -> dict | None:
    """The option carrying the prediction role, if any.

    Exactly one option carries it per the record contract; this returns
    the first, so a malformed record degrades to a wrong-but-harmless
    answer instead of an exception.
    """
    for option in record.get("options") or []:
        if not isinstance(option, dict):
            continue
        if "prediction" in str(option.get("role") or ""):
            return option
    return None


def is_rule_driven_acceptance(record: dict) -> bool:
    """Did this record's rules merely confirm their own recommendation?

    A rule that cited itself into slot 1 and got slot 1 chosen has
    produced no independent evidence: the recommendation caused the
    choice it is now counted as predicting. Extraction flags these and
    never strengthens the rule on them.
    """
    option = prediction_option(record)
    if option is None or not option.get("rules_cited"):
        return False
    return option.get("slot") == record.get("chosen_slot")


def queue_for(record: dict) -> str:
    """Which extraction queue a record belongs in.

    Corrections first — a `"N, but actually because…"` ruling carries
    the decider's own reason where the model's guess was wrong, which is
    the only place the corpus records a reason nobody inferred. Misses
    second: each one must refine a rule, split one, or spawn a
    candidate. Then refinements, then plain confirmations.
    """
    if record.get("correction") is True:
        return QUEUE_CORRECTIONS
    outcome = record.get("outcome")
    if outcome == "miss":
        return QUEUE_MISSES
    if outcome in ("refined", "near-tie"):
        return QUEUE_REFINEMENTS
    return QUEUE_CONFIRMATIONS


def summarise(record: dict) -> dict:
    """One record, reduced to what a rule-extraction pass reads.

    Unlike the replay harness this deliberately keeps the output side:
    extraction is looking at what the decider actually did and why,
    which is exactly the half replay has to mask.
    """
    option = prediction_option(record)
    return {
        "id": record.get("id"),
        "date": record.get("date"),
        "project": record.get("project"),
        "question": record.get("question"),
        "chosen": record.get("chosen"),
        "chosen_slot": record.get("chosen_slot"),
        "operative_reason": record.get("operative_reason"),
        "operative_reason_source": record.get("operative_reason_source"),
        "correction": bool(record.get("correction")),
        "outcome": record.get("outcome"),
        "prediction_stream": record.get("prediction_stream"),
        "rules_cited": (option or {}).get("rules_cited") or [],
        "rule_driven_acceptance": is_rule_driven_acceptance(record),
        "rejections": [
            {
                "option": rejection.get("option"),
                "reason": rejection.get("reason"),
                "status": rejection.get("status"),
                "reason_source": rejection.get("reason_source"),
            }
            for rejection in record.get("rejections") or []
            if isinstance(rejection, dict)
        ],
        "supersedes": record.get("supersedes"),
        "related": record.get("related") or [],
        "notes": record.get("notes"),
    }


def build_batch(records: list[dict], marker: str | None) -> dict:
    """Everything since the marker, sorted into queues."""
    pending = unprocessed(records, marker)
    queues: dict[str, list[dict]] = {name: [] for name in QUEUES}
    for record in pending:
        queues[queue_for(record)].append(summarise(record))

    flagged = [
        summary["id"]
        for queue in queues.values()
        for summary in queue
        if summary["rule_driven_acceptance"]
    ]
    return {
        "marker": marker,
        "next_marker": pending[-1].get("id") if pending else marker,
        "count": len(pending),
        "instructions": (
            "Work the queues in order. For each candidate pattern choose "
            "EXACTLY one outcome: confirm an existing rule (counter bump), "
            "flag drift against one (propose conditionalize or retire — never "
            "a silent overwrite), or propose a new rule in conditional, "
            "falsifiable form. A miss that does none of the three is logged "
            "as unexplained; unexplained is a state, not a silence. Rules "
            "listed under rule_driven_acceptances have confirmed only their "
            "own recommendation and carry no independent evidence — never "
            "strengthen them on those records."
        ),
        "queues": {name: queues[name] for name in QUEUES},
        "queue_counts": {name: len(queues[name]) for name in QUEUES},
        "rule_driven_acceptances": flagged,
        "preference_driven_count": sum(
            1
            for queue in queues.values()
            for summary in queue
            if summary["prediction_stream"] == PREFERENCE_DRIVEN
        ),
    }


def _load_records(root: str) -> list[dict]:
    """Read `decisions/` without importing the replay harness.

    Kept local so extraction stays usable in a store whose replay
    harness is mid-update; the corpus layout is fixed by the record
    contract, not by that module.
    """
    directory = os.path.join(root, "decisions")
    records: list[dict] = []
    if not os.path.isdir(directory):
        return records
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as handle:
            records.append(json.load(handle))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="how many records are waiting for extraction")

    batch = sub.add_parser("batch", help="emit the prioritized unprocessed batch")
    batch.add_argument("--out")

    mark = sub.add_parser("mark", help="advance the marker (the PR's last commit)")
    mark.add_argument(
        "--record-id",
        required=True,
        help="the last record this pass covered (batch's next_marker)",
    )

    args = parser.parse_args(argv)

    try:
        marker = load_marker(args.root)
    except MarkerError as exc:
        print(f"MARKER FAIL: {exc}", file=sys.stderr)
        return 2

    records = _load_records(args.root)

    if args.command == "mark":
        known = {str(record.get("id")) for record in records}
        if args.record_id not in known:
            print(
                f"MARKER FAIL: {args.record_id!r} is not a record in decisions/",
                file=sys.stderr,
            )
            return 2
        if marker is not None and args.record_id < marker:
            print(
                f"MARKER FAIL: {args.record_id!r} is older than the current "
                f"marker {marker!r} — the marker never moves backwards",
                file=sys.stderr,
            )
            return 2
        print(f"wrote {write_marker(args.root, args.record_id)}")
        return 0

    payload = build_batch(records, marker)

    if args.command == "status":
        print(
            f"extraction: {payload['count']} record(s) since "
            f"{marker or 'the beginning of the corpus'} "
            f"({payload['queue_counts']})"
        )
        return 0

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
        print(f"wrote {args.out}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
