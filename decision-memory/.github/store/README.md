# Preference-set lifecycle

Copier-vendored from the agentic-engineering-template guard
subtemplate — do NOT edit these files in the store repo;
change them in the template and pull via `copier update`.

Everything under `.github/store/`, plus
`.github/workflows/preferences-budget.yml`,
`.github/workflows/preferences-guard.yml` and the
`extract-preferences` and `compact-preferences` skills, is vendored
alongside the record guard in `.github/guards/`.

The two directories stay separate because they answer to different
things: `guards/` gates the record corpus, `store/` runs the
preference-set lifecycle on top of it.
They are not separate trust domains — the record guard reads this
layer's config for the token budget, so there is one budget number and
one place to change it.
Both are vendored, so neither can drift from the schema —
which is the point.
N stores share one budget rule, one carve-out rule, one replay gate.

`store.config.json` is the exception: it is seeded once and owned by
the store, so a human adjusts the knobs below without fighting
`copier update`.

## Why

`preferences.md` is injected into every grilled session. Everything in
it costs context on every session, forever — so it is a hard budget,
not a wishlist, and shrinking it needs to be safe rather than brave.
That gives four jobs: grow the set from what the records actually
show, measure the budget, protect the file from casual edits, and make
a compaction provably non-degrading before it merges.

Growing comes first. Until rules are extracted, every record is
recorded `prediction_stream: cold`, the preference-driven stream is
empty, and the compaction gate has nothing to measure.

## Configuration

`store.config.json`, at the repo root — the one place a human adjusts
these knobs:

| key | default | meaning |
| --- | --- | --- |
| `budget_tokens` | 2000 | hard budget for `preferences.md` |
| `warn_at_percent` | 80 | "compression due" threshold |
| `carve_out_label` | `preferences-carve-out` | label permitting edits to existing lines |
| `budget_issue_label` | `preferences-budget` | label on the automated budget issue |
| `replay_waiver_label` | `preferences-replay-waiver` | label accepting an `insufficient-evidence` gate |
| `replay_window` | 20 | how many recent decisions the replay scores |
| `min_gated_cases` | 8 | below this many preference-driven cases the gate reports `insufficient-evidence` |

A missing file is fine — the defaults are the contract. Unknown keys
are tolerated (`_comment` is one), invalid values fail loudly.

`budget_tokens` is the ONLY budget. The vendored record guard loads
this config and enforces whatever the store chose;
`decision_validator.PREFERENCES_TOKEN_BUDGET` is the default it falls
back to when a store ships no config file, not a ceiling over it. One
number, one place to change it, checked once.

Token counting is not reimplemented here either — `estimate_tokens`
from the vendored validator is the single authority, so this layer and
the vendored guard can never disagree about how big the file is.

`extraction-marker.json` is store-owned for the same reason: it is
per-store state, and `copier update` clobbering it would silently
re-run extraction over a batch already processed.

## Enforcement

**On push to `main`** (`preferences-budget.yml`) the file is counted
and one pinned issue is kept in sync: opened or updated at or above
`warn_at_percent`, closed once the file is back under it. It reports;
it never blocks.

**On every PR** (`preferences-guard.yml`, alongside the vendored
`guards.yml`):

- Over 100% of budget, a PR that touches `preferences.md` fails. PRs
  that do not touch it are not blocked by someone else's overspend.
- Editing an EXISTING line in `preferences.md` requires the carve-out
  label. Pure additions never need it; mechanical `pref-confirm`
  counter bumps are exempt, since the vendored guard already validates
  their counter math.
- A carve-out PR must carry a replay report in its description, gated
  `pass`, whose `candidate_preferences_sha256` matches the
  `preferences.md` in the PR head — a stale report from an earlier
  round fails.
- A report gated `insufficient-evidence` merges only with
  `replay_waiver_label` on the PR. A report gated `fail` never merges;
  the waiver does not apply to a measured regression.

The vendored record guard additionally checks that
`extraction-marker.json` names a record that exists — a marker
pointing at nothing would silently skip or re-process a whole batch,
and that failure is indistinguishable from "extraction found nothing".

`decisions/` gets **no carve-out**. Append-only there is absolute and
neither this layer nor extraction touches that rule.

## Replay regression

`replay.py` is the harness the compaction skill drives; the predicting
agent sits in the middle, so this repo depends on no skill.

```bash
python .github/store/replay.py cases   --out cases.json
python .github/store/replay.py score   --predictions preds.json \
    --preferences preferences.md --out report.json
python .github/store/replay.py gate    --baseline base.json \
    --candidate cand.json --out replay-report.json
```

`cases` masks each record to its input side and strips the fields that
leak the old rule set's answer (`role`, `rules_cited`, and the
in-session `reasoning`). `score` joins an agent's predictions with the
recorded `chosen_slot`. `gate` compares two scored runs: exit 0 on
`pass`, 1 on `fail` when the **preference-driven** hit rate degrades,
and 3 on `insufficient-evidence`.

Two streams, exactly as recording uses them: a prediction citing rules
scores preference-driven, one citing none scores cold. The gate is the
preference-driven stream. The cold stream is the control group — plain
judgment, which a rule-set edit should not move — so it is reported
and never gated. Cases that change stream under the candidate set are
counted separately, so a hit-rate change caused by re-labelling rather
than by better rules is visible.

### What the calibration fixed

A null test — two blind runs over the *same* rule set — passed the
gate by luck rather than by design, and both problems are addressed
here.

**The gated denominator was unstable.** Both runs picked the same slot
on all 17 cases but disagreed on whether a rule drove the pick for 4
of them, so `n` moved 3 -> 5 under a change that was not a change. At
that size one case flipping swings the hit rate 20-33 points, so a
`pass` meant nothing. `min_gated_cases` is the answer: below it the
gate reports `insufficient-evidence`, and merging takes a waiver label
that puts a human's name on an unvalidated compaction. On a corpus
with no extracted rules, every compaction needs the waiver — that is
the honest state, and it is meant to be visible rather than papered
over with a green check.

**Slot ordering leaked.** `chosen_slot` was 1 in 14 of 17 records, so
a blind "always slot 1" scored 82% and both runs scored 94%. Masking
stripped `role` and `rules_cited` but left slot order, and slot 1 is
the prediction slot by convention. `cases` now presents each record's
options in an order derived from its ID and `score` derives the same
order to map predictions back, so the number measures rules rather
than ordering. The mapping is never written into the cases file:
shipping it would hand the signal straight back.

The remaining calibration is data, not code — the gate is trustworthy
once records carry `prediction_stream: preference-driven`, which is
what extraction produces. Re-run the null test then.

## Extraction

`extraction.py` is the read side of the growth half, driven by the
`extract-preferences` skill:

```bash
python .github/store/extraction.py status
python .github/store/extraction.py batch --out batch.json
python .github/store/extraction.py mark --record-id <id>
```

`batch` emits every record after the marker, sorted into four queues in
descending evidence order — `corrections`, `misses`, `refinements`,
`confirmations` — plus the rule-driven acceptances, where a rule cited
itself into the prediction slot and that slot was chosen. Those confirm
nothing: the recommendation caused the choice it would be credited with
predicting. They are flagged precisely because counting them is
tempting.

The pass is a BATCH, never per-session: the evidence extraction looks
for is cross-session repetition, which no single session can see.

The marker is a record ID, not a commit SHA. IDs begin with a UTC
timestamp and `decisions/` is append-only, so "which records are new"
is a string comparison over the corpus — no git archaeology, nothing
to break when history is rewritten around it, and a guard check that
can actually verify the marker points at something real.

## Tests

```bash
python .github/store/tests/test_store.py
```

The git-facing adapters are thin; the decisions live in pure functions,
which is what the tests cover. They also build replay cases from the
real corpus, so a record the harness cannot handle fails CI.

## Known seams

- Nothing here is store-local any more,
  so a store that wants a different budget policy cannot have one —
  it gets the vendored policy and tunes it through `store.config.json`.
  A store needing more than the knobs allow changes the template.
