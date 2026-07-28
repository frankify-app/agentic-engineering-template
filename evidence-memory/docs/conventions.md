# Evidence-Memory Store — Writing Conventions

> Copier-vendored from the agentic-engineering-template evidence
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

The authoritative contract any writer — tool or hand — must satisfy.
The CI guard (`.github/guards/`) enforces it mechanically; this file is
the human-readable authority, `evidence_validator.py` the
machine-readable one. Both live in the template repo's evidence
subtemplate and change together there, in the same PR.

## What this store is

A store of immutable **detection records**: bugs and features found
while working, kept as the substrate for dedup, lookup, and later kata
promotion.

It is **memory, not a tracker**. Progress lives on the forge — every
record names its ticket, and work happens there. A store that also
tracked status would be a second backlog, stale by the following week.

## Storage layout

- `records/<id>.json` — one immutable JSON **file** per detection, flat
  directory. Append-only: existing files are NEVER modified, deleted,
  or renamed.
- ID = filename stem = `<timestamp>-<slug>`, e.g.
  `20260728T161500Z-drift-baseline-ignored`. The slug is a
  writer-chosen kebab-case title, ≤40 chars; the timestamp is minted
  (UTC) by the writer tool.

## Record schema

```json
{
  "v": 1,
  "type": "evidence",
  "id": "20260728T161500Z-drift-baseline-ignored",
  "date": "2026-07-28",

  "symptom": "disambiguate --drift exits 0 with a stale baseline entry",
  "triage": "code-bug",
  "tier": 1,
  "rung": "capsule",
  "ticket": "https://github.com/«owner»/«repo»/issues/«n»",

  "environment": "disambiguate 0.3.0, python 3.13, «repo»@«sha»",
  "expected": "a baselined finding that no longer occurs is pruned",
  "observed": "the entry survives and the run still exits 0",
  "capsule": null,

  "same_symptom_as": null,
  "regression_of": null,
  "session": "session_01ABC…",
  "notes": null
}
```

### Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `symptom` | yes | **One line.** The grep-able fingerprint — dedup starts by grepping this across a local clone, so a multi-line value is invisible to that grep after its first line. Detail belongs in `expected`/`observed`. |
| `triage` | yes | `code-bug` · `doc-bug` · `expectation-bug` · `feature` |
| `tier` | yes | `1` capsule is public (in the ticket) · `2` capsule cannot be sanitized and lives here |
| `rung` | yes | Filing ladder reached: `record` · `ticket` · `capsule` · `repro-branch` |
| `ticket` | yes | Forge ticket URL. The store is memory; this is the link to where work happens. |
| `environment` | yes | Tool versions, repo@SHA — what makes the observation reproducible |
| `expected` / `observed` | yes | The contradiction, stated plainly |
| `capsule` | tier 2 | The repro capsule. Required for a tier-2 record at the `capsule` rung or above — tier 2 exists *because* the capsule cannot be public, so it has to be here. |
| `same_symptom_as` | no | An earlier record covering this symptom — whether it corroborates or suspects a different cause, which the body says |
| `regression_of` | no | An earlier record whose capsule still reproduces *and* whose kata now fails |
| `session` | no | Session pointer. The `Claude-Session:` commit trailer is the standing fallback; never build an uploader. |
| `notes` | no | Anything else |

Unknown fields are tolerated: a new optional field needs no migration.

## Links point backward, always

Records are immutable, so an earlier record can never gain an edge to a
later one. Every link therefore points at an older record, and the
guard enforces it from the IDs alone — they lead with a UTC timestamp.

The consequence worth knowing: reconstructing every record about one
symptom needs a **reverse index built at read time**, not a forward
walk from the oldest. Do not implement a back-edge; it cannot exist.

The forge is where two-way linking happens, because tickets are
mutable. That asymmetry is deliberate, not an oversight.

## Vocabulary this store does NOT use

`related`, `supersedes`, `drill_down_of` belong to the decision store
and mean something else there. A shared spelling with a different
meaning is worse than two spellings.

`duplicate_of` is absent by design: a literal duplicate is *skipped* at
capture rather than filed, so the field would name the one case that
never produces a record. Additional evidence on a known symptom is not
duplication — it is a new record carrying `same_symptom_as`.
