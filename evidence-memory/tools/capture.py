"""Evidence recorder — mints one immutable record per detection.

Copier-vendored from the agentic-engineering-template — do NOT edit in
the store repo; change it in the template and pull via `copier update`.

The sibling of the decision recorder, not a mode of it: both compose
on ``record_core.py``, and neither carries a branch for the other's
lifecycle. What differs is entirely policy — this store's record type,
its field order, and the detection facts a record carries.

Deliberately no git or forge mechanics. The decision recorder owns
clone/branch/commit/PR because a decision session ends in one PR of
many records; an evidence filing is a single record dropped mid-task,
and the caller is already in a repo with a commit to make. Revisit
when writing the record by hand is what hurts, not before.

Stdlib only. Usage:

    python tools/capture.py --draft draft.json
    cat draft.json | python tools/capture.py --draft -
    python tools/capture.py --draft draft.json --store «path»
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import record_core  # noqa: E402  (path bootstrap above)

RECORD_TYPE = "evidence"
RECORDS_DIR = "records"
VALIDATOR_RELPATH = Path(".github") / "guards" / "evidence_validator.py"

# Envelope, then the detection itself, then where it was filed, then
# the links. A reader scanning a record top-to-bottom meets the
# symptom before anything else, because that is the field every lookup
# starts from.
FIELD_ORDER = (
    "v",
    "type",
    "id",
    "date",
    "symptom",
    "triage",
    "tier",
    "rung",
    "ticket",
    "environment",
    "expected",
    "observed",
    "capsule",
    "same_symptom_as",
    "regression_of",
    "session",
    "notes",
)


def draft_to_record(draft: dict, now: dt.datetime) -> dict:
    """Turn a draft (the schema minus tool-minted fields, plus ``slug``)
    into a full record.

    Draft-supplied values always win over minted defaults; unknown
    fields are preserved. Raises ValueError when ``slug`` is missing or
    malformed.
    """
    payload = dict(draft)
    slug = payload.pop("slug", None)
    if not isinstance(slug, str) or not slug:
        raise ValueError("draft is missing the writer-chosen 'slug' field")

    merged = record_core.mint_envelope(slug, now, RECORD_TYPE)
    merged["date"] = now.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")
    merged.update(payload)
    return record_core.order_fields(merged, FIELD_ORDER)


def load_validator(store_root: Path):
    """Import the store's own vendored validator.

    Writer-side and CI validation must be the same code: a record that
    the writer accepts and CI rejects is a record that cannot be
    filed, and one the writer rejects and CI would accept is lost
    evidence.
    """
    path = store_root / VALIDATOR_RELPATH
    if not path.exists():
        raise SystemExit(f"no validator at {path} — is {store_root} an evidence store?")
    spec = importlib.util.spec_from_file_location("evidence_validator", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"could not load the validator at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_record(record: dict, store_root: Path) -> Path:
    """Write a record to its immutable ``records/<id>.json``.

    Refuses to overwrite: the store is append-only, so an existing
    path means the ID collided and the caller has to mint again.
    """
    directory = store_root / RECORDS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['id']}.json"
    if path.exists():
        raise SystemExit(f"{path} already exists — records are immutable")
    path.write_text(record_core.serialize_record(record), encoding="utf-8")
    return path


def read_draft(source: str) -> dict:
    text = (
        sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    )
    try:
        draft = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"draft is not valid JSON: {exc}") from exc
    if not isinstance(draft, dict):
        raise SystemExit("draft must be a JSON object")
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--draft", required=True, help="path to the draft JSON, or - for stdin"
    )
    parser.add_argument(
        "--store",
        default=".",
        help="the evidence store's root (default: current directory)",
    )
    args = parser.parse_args(argv)

    store_root = Path(args.store).resolve()
    draft = read_draft(args.draft)

    try:
        record = draft_to_record(draft, dt.datetime.now(dt.timezone.utc))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    validator = load_validator(store_root)
    errors = validator.validate_record(record, filename_stem=record["id"])
    if errors:
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        raise SystemExit(f"{len(errors)} contract error(s) — nothing written")

    path = write_record(record, store_root)
    print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
