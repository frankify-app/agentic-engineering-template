"""Universal validation core — the checks every store's records share.

Copier-vendored from the agentic-engineering-template — do NOT edit in
a store repo; change it in the template and pull via `copier update`.

The reading-side mirror of ``record_core.py``: one writer core and one
validation core serve every store, and only lifecycle policy differs
per store. What lives here is what cannot know which store it is
checking — ID grammar, the envelope, required-field presence, and link
integrity across a corpus. Which fields are required, which links
exist, and what a record means are the store's own contract, and
arrive as arguments.

Stdlib only, so a guard runs with no install step.
"""

from __future__ import annotations

import re

SCHEMA_VERSION = 1
MAX_SLUG_LENGTH = 40
ID_RE = re.compile(r"^(\d{8}T\d{6}Z)-([a-z0-9]+(?:-[a-z0-9]+)*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def validate_envelope(record: dict, record_type: str) -> list[str]:
    """Check the universal envelope: v, type, id.

    ``record_type`` is the type this store's records must carry — the
    envelope routes records in a mixed ledger, so which value is
    correct is the store's policy rather than the core's.
    """
    errors: list[str] = []
    v = record.get("v")
    if not isinstance(v, int) or isinstance(v, bool) or v < 1:
        errors.append("v: must be a positive integer schema version")
    actual = record.get("type")
    if actual != record_type:
        errors.append(f"type: must be {record_type!r} in this repo, got {actual!r}")
    errors.extend(validate_id(record.get("id")))
    return errors


def validate_required(record: dict, required_fields: tuple) -> list[str]:
    """Report every required field the record does not carry."""
    return [
        f"{field}: required field missing"
        for field in required_fields
        if field not in record
    ]


def validate_corpus(records: dict, link_fields: tuple, store_dir: str) -> list[str]:
    """Check that no link points outside the corpus.

    ``records`` maps record ID -> record dict (normally a whole store
    directory). ``link_fields`` is the store's own link vocabulary; a
    field's value may be a single reference or a list of them, so both
    are walked. ``store_dir`` only names the directory in the message.

    A dangling reference is an error rather than a warning because a
    record must not point at something that may never exist: records
    are immutable, so a link that is wrong when written stays wrong.
    """
    errors: list[str] = []
    for record_id, record in sorted(records.items()):
        if not isinstance(record, dict):
            continue
        for field in link_fields:
            value = record.get(field)
            if value is None:
                continue
            refs = value if isinstance(value, list) else [value]
            for ref in refs:
                if ref not in records:
                    errors.append(
                        f"{record_id}: {field} points to {ref!r}, "
                        f"which does not exist in {store_dir}/"
                    )
    return errors
