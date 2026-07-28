"""Universal record contract core — the write format every store shares.

Copier-vendored from the agentic-engineering-template — do NOT edit in
a store repo; change it in the template and pull via `copier update`.

Pure functions, no IO: this is the dojo lift-target, the part a future
dojo package lifts verbatim. Everything here is common to every record
kind. What a store calls its fields, and which of them it writes
first, is that store's own policy and arrives as data.

Validation is deliberately NOT defined here: each store's validator is
vendored beside its own records, so writer-side and CI validation
cannot drift.

Stdlib only.
"""

from __future__ import annotations

import datetime as dt
import json
import re

# Mint-side mirror of the envelope/ID grammar. The vendored validator
# in a store checkout stays authoritative — minted records are
# re-validated against it; these constants only make minting fail fast
# with better messages.
SCHEMA_VERSION = 1
MAX_SLUG_LENGTH = 40
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def mint_id(slug: str, now: dt.datetime) -> str:
    """Mint a record ID: <UTC timestamp>Z-<slug>."""
    if not SLUG_RE.match(slug):
        raise ValueError(f"slug {slug!r} must be lowercase kebab-case ([a-z0-9-])")
    if len(slug) > MAX_SLUG_LENGTH:
        raise ValueError(f"slug {slug!r} is {len(slug)} chars (max {MAX_SLUG_LENGTH})")
    timestamp = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{slug}"


def mint_envelope(slug: str, now: dt.datetime, record_type: str) -> dict:
    """Mint the universal envelope: v, type, id.

    ``record_type`` is what routes a record in a mixed ledger, so it is
    the calling store's to supply rather than a constant here.
    """
    return {
        "v": SCHEMA_VERSION,
        "type": record_type,
        "id": mint_id(slug, now),
    }


def order_fields(merged: dict, field_order: tuple) -> dict:
    """Order a record's fields by its store's declared order.

    Fields the order does not name keep their incoming order after the
    ones it does, so an unrecognized field is preserved rather than
    silently dropped.
    """
    record = {key: merged[key] for key in field_order if key in merged}
    for key, value in merged.items():
        if key not in record:
            record[key] = value
    return record


def serialize_record(record: dict) -> str:
    """Serialize a record for its immutable ``<id>.json`` file."""
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def resolve_batch_refs(drafts: list, now: dt.datetime) -> list:
    """Resolve batch-local slug references to minted IDs.

    Drafts written in one pass cannot know each other's final IDs, so
    cross-draft links name their target by slug: ``supersedes_slug``
    and ``drill_down_of_slug`` (single), ``related_slugs`` (list,
    appended to any repo-ID ``related`` entries). This maps every
    reference to the ID the batch will mint (order-independent).
    Raises ValueError on unknown slugs or when a draft carries both a
    slug reference and its resolved field.
    """
    minted = {}
    for d in drafts:
        slug = d.get("slug")
        if isinstance(slug, str) and SLUG_RE.match(slug):
            minted[slug] = mint_id(slug, now)

    def resolve(draft_slug, ref):
        if ref not in minted:
            raise ValueError(
                f"draft {draft_slug!r}: batch reference {ref!r} matches "
                "no slug in this batch"
            )
        return minted[ref]

    resolved = []
    for d in drafts:
        d = dict(d)
        for slug_field, target in (
            ("supersedes_slug", "supersedes"),
            ("drill_down_of_slug", "drill_down_of"),
        ):
            ref = d.pop(slug_field, None)
            if ref is not None:
                if d.get(target):
                    raise ValueError(
                        f"draft {d.get('slug')!r}: both {target} and "
                        f"{slug_field} given — use one"
                    )
                d[target] = resolve(d.get("slug"), ref)
        refs = d.pop("related_slugs", None)
        if refs is not None:
            if not isinstance(refs, list):
                raise ValueError(
                    f"draft {d.get('slug')!r}: related_slugs must be a list"
                )
            existing = d.get("related") or []
            d["related"] = existing + [resolve(d.get("slug"), r) for r in refs]
        resolved.append(d)
    return resolved
