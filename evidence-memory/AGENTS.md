# Evidence-Memory Store — Agent Guidelines

> Copier-vendored from the agentic-engineering-template evidence
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

Private evidence store for one principal (a person or a team):
detection records for bugs and features, the CI guard protecting them,
and the writer that mints them.
The data is this repo's; every line of code around it is vendored from
the agentic-engineering-template evidence subtemplate,
so N stores cannot drift from one schema.
`tools/capture.py --help` is the writer's authoritative behavior doc.

## Golden rules

Compressed summary — [docs/conventions.md](docs/conventions.md) is the
authoritative contract.

- `records/` is append-only: NEVER modify, delete, or rename an
  existing record. CI rejects it; do not try.
- This store is **memory, not a tracker**. Every record names its forge
  ticket, and progress is tracked there. Never add status to a record,
  and never add a status file — a local mirror of forge state is stale
  by the following week.
- New evidence on a known symptom is a **new record** carrying
  `same_symptom_as`, never an edit to the existing one.
- Links point backward only. An older record cannot gain an edge to a
  newer one, because it is immutable. Do not implement a back-edge.
- A literal duplicate is **skipped**, not filed. If the case adds
  nothing, there is nothing to record.
- Never write this repo's URL into a public artifact.

## Tiers, and the leak that matters

- **Tier 1** — the capsule can be synthesized leak-free, so it goes in
  the public ticket and is cold-reproducible by anyone.
- **Tier 2** — the capsule cannot be sanitized (production data, org
  internals, security). It lives here; the public ticket carries a
  leak-free summary only.

Sanitize by **synthesis, not redaction**: a synthetic fixture is both
leak-free and runnable, a redacted one is neither. Tier 1 is preferred
whenever synthesis is possible at all.

Before filing anything public, re-read what you are about to write for
paths, hostnames, tokens, and internal identifiers. A record here is
private; the ticket it links is not.

## Filing

```bash
python tools/capture.py --draft draft.json
```

The writer mints the ID, orders the fields, validates against this
store's own vendored validator, and refuses to overwrite. Hand-written
records are allowed; they get no help and face the same guard.

Evidence PRs auto-merge on green, so the guard is the review. That is
the reason the guard checks what a machine can check and claims nothing
more — it never asserts that a record is *useful*, only that it is
well-formed.
