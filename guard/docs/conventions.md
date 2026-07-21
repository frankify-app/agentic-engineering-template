# Decision-Memory Store — Writing Conventions

> Copier-vendored from the agentic-engineering-template store
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

The authoritative contract any writer — tool or hand — must satisfy.
The CI guards (`.github/guards/`) enforce it mechanically; this file
is the human-readable authority, `decision_validator.py` the
machine-readable one. Both live in the template repo's store
subtemplate and change together there, in the same PR.

## Storage layout

- `decisions/<id>.json` — one immutable JSON **file** per decision,
  flat directory. Append-only: existing files are NEVER modified,
  deleted, or renamed.
- ID = filename stem = `<timestamp>-<slug>`, e.g.
  `20260715T143205Z-agent-access`. The slug is a writer-chosen
  kebab-case title, ≤40 chars; the timestamp is minted (UTC) by the
  writer tool. No project prefix — `project` is a record field only;
  artifact URLs never appear in IDs or filenames.

## Record schema

Records are **replay-ready**: input-side fields are written BEFORE
the ruling, output-side after, so a replay harness can mask outcomes
and score predictions. Field order groups the two sides.

Example (a real record):

```json
{
  "v": 1,
  "type": "decision",
  "id": "20260715T143205Z-agent-access",
  "date": "2026-07-15",
  "project": "factory",

  "question": "How do agent environments access the preference repo?",
  "context": "session-local facts informing the options, written before the ruling",
  "options": [
    {"slot": 1, "label": "read-only deploy key, human-approved writes",
     "role": "prediction+recommendation",
     "rules_cited": [],
     "reasoning": "integrity via least privilege"},
    {"slot": 2, "label": "full-access PAT everywhere",
     "if_clause": "if write friction matters more than blast radius"},
    {"slot": 3, "label": "local clone, manual sync",
     "if_clause": "if offline work dominates"}
  ],
  "prediction_stream": "cold",
  "preference_set": {"commit": "<sha>"},
  "artifact_ref": {
    "repo": "skills",
    "path": "skills/grilling/SKILL.md",
    "commit": "<sha>",
    "anchor": "#recording"
  },
  "session": "session_01ABC…",

  "chosen_slot": 4,
  "chosen": "all agents as collaborators, PRs against main",
  "operative_reason": "write friction defeats seamless recording — reintroduces manual journaling step",
  "correction": false,
  "rejections": [
    {"option": "read-only deploy key",
     "reason": "write friction defeats seamless recording — reintroduces manual journaling step",
     "status": "operative", "reason_class": "TBD"},
    {"option": "full-access direct push",
     "reason": "agent could silently rewrite preference history",
     "status": "presumed-false", "reason_source": "inferred",
     "reason_class": "TBD"}
  ],
  "outcome": "miss",
  "drill_down_of": null,

  "related": ["20260715T141020Z-repo-hosting"],
  "supersedes": null,
  "notes": "Compromise adopted: CI-enforced append-only replaces access control"
}
```

Required fields: `v`, `type`, `id`, `date`, `project`, `question`,
`options`, `prediction_stream`, `artifact_ref`, `chosen_slot`,
`chosen`, `rejections`, `outcome`. Unknown fields are TOLERATED
everywhere — new optional fields need no migration.

### Envelope

- `v`: schema version, minted by the writer tool.
- `type`: always `"decision"` in this repo — routes records in future
  mixed dojo ledgers. The envelope `{v, id, type}` is the universal
  write format shared with all future dojo record kinds; this repo is
  a terminal store (no compaction — per-record PR review is the
  point). `ts` is deliberately absent: the ID embeds it.
- `id`: stable, unique, always equal to the filename stem.

### Input side (pre-ruling)

- `question`, `context`, `options` (the MC block verbatim: slot,
  label, role, if-clause, reasoning, cited preference rules),
  `prediction_stream`, `preference_set`, `artifact_ref`, `session`.
- `options[].role`: `prediction` (slot 1 — what the preference set
  predicts; `rules_cited` names the rules, empty = cold),
  `recommendation` (slot 2 — the agent's independent best),
  `prediction+recommendation` when merged, `wildcard` (slot 3).
  Exactly ONE option carries a prediction role. Recommendations are
  recorded as made in-session, NEVER back-filled after the choice is
  known.
- `prediction_stream`: `preference-driven` | `cold` — the two scoring
  streams. `rules_cited` non-empty iff preference-driven. Cold misses
  never count against the preference model (pure judgment
  calibration, prime seeds for new rules).
- `preference_set.commit`: SHA of this repo as injected at session
  start — content-addresses the active preference set, so replay can
  flag matching-but-uncited rules (false cold claims are detectable
  provenance defects).
- `artifact_ref`: REQUIRED when an artifact exists — repo-relative
  path + commit SHA (content-addressed, survives rewrites) + anchor
  when possible. Null only if genuinely no artifact. Chat-extracted
  drafts carry null refs by design (never guess SHAs); enrich them in
  the drafts file at ingestion time, once the commits exist — drafts
  are plain JSON, no tooling needed.
- `session`: opaque grouping key, NOT a locator — minted best-effort
  by the writer tool, `null` when unavailable. Never load-bearing.

### Output side (post-ruling)

- `chosen_slot`, `chosen` (free text when slot 4),
  `operative_reason` (the confirmed if-clause verbatim, or the stated
  free-text reason — required when a listed non-prediction option is
  chosen), `correction` ("N, but actually because…" — highest-signal
  event, first-class flag), `rejections`, `outcome`.
- `rejections[].status`: `operative` (confirmed by the choice,
  recorded verbatim, no inference) | `presumed-false` (the likely
  reason the option lost, recorded as inference). Never conflate —
  only operative reasons feed rule extraction. Deciders can upgrade a
  presumed-false reason to operative by stating their own (e.g.
  "Option N, because XYZ" in the free-text slot).
- `rejections[].reason_source`: REQUIRED on presumed-false rejections
  — `if_clause` (the option's own if-clause did not hold), `inferred`
  (most-likely reason from context, marked as the model's inference),
  or `none` (nothing stated or inferable — ONLY then is
  `reason: null` valid; declared, never a lazy default or a filler
  string). Prefer `if_clause`/`inferred` over `none`. Operative
  rejections are stated by definition (`reason_source` omitted or
  `stated`).
- `reason_class`: free text / `"TBD"` for now; a taxonomy emerges
  after ~20 real entries, not before.
- `outcome`: `hit` | `miss` | `near-tie` | `refined` — scored
  against the prediction slot per stream. Near-ties are never scored
  as misses and never carry fabricated rejection reasons. `refined`
  = the chosen answer CONTAINS the prediction plus an extension
  (right but incomplete — the most common free-text answer style);
  bucketed separately in hit rates, never counted as a miss, and
  never auto-bumping preference counters (only clean hits confirm
  rules).
- `drill_down_of`: ID of the parent record when this record is a
  drill-down follow-up question (drill-downs are themselves
  prediction-scored MC events with their own records); else null.

### Links

- `related` (informs/refines) and `supersedes` (replaces —
  decision-level drift signal). Stable IDs + link fields ARE the
  graph; no edge-type taxonomy beyond these two. All referenced IDs
  must exist (CI-checked).
- `closure_of`: optional — the number of a closed-unmerged PR in THIS
  repo that the record explains ("why was PR #N rejected"). Doubles
  as the stateless sweep watermark: the writer's `open` lists all
  closed-unmerged PRs and prompts records only for those not yet
  covered by a matching `closure_of` — the records themselves are the
  state.

## Active preference set (`preferences.md`)

- Hard token budget: ~2k tokens, CI-enforced. Promoting a rule at
  budget means merging or demoting another ("promote requires
  demote").
- Rules are conditional and falsifiable, one bullet each, with a
  confirmation counter and last-confirmed date:
  `[confirmed: <N>, last: <YYYY-MM-DD>]`.
- Counter-line updates are the ONE sanctioned edit in this repo,
  executed mechanically: `submit` auto-generates `pref-confirm`
  commits from in-session preference-driven hits; CI validates the
  counter math (increment by exactly 1, rule text unchanged).
- A rule only ever confirmed by choices its own recommendation caused
  has zero independent evidence — extraction flags such rules, never
  strengthens them (provenance is in the records: `rules_cited` +
  `chosen_slot`).
- Promotion is separate and human-only: agents write candidate rules
  to `proposals/<YYYY-MM-DD>-<slug>.md` (one rule per file); only a
  human `pref-promote` commit moves content into `preferences.md`.
  Merging a proposal file is NOT promotion.

## Commit types

This repo's own conventional-commit types, CI-linted on every PR
commit:

- `decision(<project>): <slug> — <chosen>`
- `pref-proposal: <rule>`
- `pref-promote: <rule>` (human only)
- `pref-confirm: <rule> (n=<count>)` (counter bump)
- `chore: ...` (structure, CI, docs)

Examples:

```text
decision(factory): repo hosting — private GitHub over self-hosted/synced
decision(factory): agent access — collaborators+PRs over read-only key
pref-proposal: prefers CI-enforced integrity over access restrictions
pref-confirm: rejects new infrastructure dependencies (n=4)
```

## PR flow

- One PR per session (branch `session/<YYYYMMDDTHHMMSSZ>`); ONE
  commit per record — atomic and dissectable. Partial accept =
  hand-edit the branch, drop or revert individual commits before
  merge.
- Merging a decision-record PR = acceptance of the *record*.
- Closing a PR without merge is itself signal: the next session's
  `open` sweep prompts a closure record (`closure_of`), with the
  `correction` flag where applicable.
- `supersedes` claims must be surfaced in the PR description for
  explicit human review.
- The session-end PR description states prediction hit rates as two
  streams (preference-driven vs cold — the control group).

## CI guards

`.github/guards/` — copier-vendored from the
agentic-engineering-template guard subtemplate (single shared source;
the writer tool imports the same validator from its session clone).
Stdlib-only, no dependencies; fails soft on factory loss. Checks:

- Append-only on `decisions/**` (no modify/delete/rename, no
  exceptions); `preferences.md` line removals only from
  `pref-confirm`/`pref-promote` commits, counter math validated.
- Schema + consistency on the ENTIRE corpus every run — guard updates
  can never retroactively invalidate or silently mis-accept records
  without it showing.
- Dangling-reference check on `related`/`supersedes`/`drill_down_of`.
- Token budget on `preferences.md`.
- Commit lint (the types above).
