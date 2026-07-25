# Preference-set lifecycle

Copier-vendored from the agentic-engineering-template guard
subtemplate — do NOT edit these files in the store repo;
change them in the template and pull via `copier update`.

Everything under `.github/store/`, plus
`.github/workflows/preferences-budget.yml`,
`.github/workflows/preferences-guard.yml` and
`.claude/skills/compact-preferences/`, is vendored alongside the
record guard in `.github/guards/`.
This layer sits on top of that one and imports it read-only,
so the vendored contract stays the single authority for records.

The two directories stay separate because they answer to different
things: `guards/` gates the record corpus, `store/` runs the
preference-set lifecycle on top of it.
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
That gives three jobs: measure the budget, protect the file from
casual edits, and make a compaction provably non-degrading before it
merges.

## Configuration

`store.config.json`, at the repo root — the one place a human adjusts
these knobs:

| key | default | meaning |
| --- | --- | --- |
| `budget_tokens` | 2000 | hard budget for `preferences.md` |
| `warn_at_percent` | 80 | "compression due" threshold |
| `carve_out_label` | `preferences-carve-out` | label permitting edits to existing lines |
| `budget_issue_label` | `preferences-budget` | label on the automated budget issue |
| `replay_window` | 20 | how many recent decisions the replay scores |

A missing file is fine — the defaults are the contract. Unknown keys
are tolerated (`_comment` is one), invalid values fail loudly.

`budget_tokens` cannot exceed the vendored
`decision_validator.PREFERENCES_TOKEN_BUDGET`: the vendored guard
would fail the PR first, so a higher local value would be a lie.
Raising it means raising it in the template's guard subtemplate and
pulling that through `copier update`.

Token counting is not reimplemented here — `estimate_tokens` from the
vendored validator is the single authority, so this layer and the
vendored guard can never disagree about how big the file is.

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

`decisions/` gets **no carve-out**. Append-only there is absolute and
this layer does not touch that rule.

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
recorded `chosen_slot`. `gate` compares two scored runs and exits
non-zero when the **preference-driven** hit rate degrades.

Two streams, exactly as recording uses them: a prediction citing rules
scores preference-driven, one citing none scores cold. The gate is the
preference-driven stream. The cold stream is the control group — plain
judgment, which a rule-set edit should not move — so it is reported
and never gated. Cases that change stream under the candidate set are
counted separately, so a hit-rate change caused by re-labelling rather
than by better rules is visible.

Slot order is deliberately left alone: slot 1 is the prediction slot
by convention, so some ordering signal survives masking. It is
identical across both runs, which is what a before/after comparison
needs.

## Tests

```bash
python .github/store/tests/test_store.py
```

The git-facing adapters are thin; the decisions live in pure functions,
which is what the tests cover. They also build replay cases from the
real corpus, so a record the harness cannot handle fails CI.

## Known seams

- The compaction commit type is `pref-promote:` because that is the
  only vendored type allowed to remove lines from `preferences.md`.
  Compaction is not promotion; the human gate is the merge, not the
  commit authorship. A dedicated `pref-compact:` type would be
  cleaner and needs a template-side change.
- Nothing here is store-local any more,
  so a store that wants a different budget policy cannot have one —
  it gets the vendored policy and tunes it through `store.config.json`.
  A store needing more than the knobs allow changes the template.
