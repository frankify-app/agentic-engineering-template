---
name: compact-preferences
description: Compact preferences.md — merge overlapping rules, drop superseded or expired ones, tighten wording — then replay the last decisions against the compacted set and open a gated carve-out PR. Use when the budget workflow reports "compression due", when preferences.md is at or over its token budget, or when the user asks to compact, shrink, or clean up the preference set.
---

# Compacting the active preference set

> Copier-vendored from the agentic-engineering-template guard
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

`preferences.md` is injected into every grilled session, so every rule
in it costs context on every session, forever. Compaction is how that
cost comes back down without losing what the rules encode.

Manual trigger only — never on a schedule, never as a side effect of
another task. A human merges the result.

## Invariants

Break any of these and CI rejects the PR, as it should.

- `decisions/` stays append-only. Compaction rewrites the ACTIVE SET,
  never history. Do not modify, delete, or rename a single record —
  there is no carve-out for `decisions/`, ever.
- Every surviving rule keeps its conditional, falsifiable form: one
  bullet, a condition, an outcome you could be wrong about, and its
  `[confirmed: N, last: YYYY-MM-DD]` counter.
- The replay gate is a gate, not a report. A failing gate means the
  compaction is wrong; revise or abandon it.
- The compacted set is smaller than what it replaces. If it is not,
  there was nothing to compact.

## Procedure

Run from the repo root, on a clean tree, with `main` up to date.

### 1. Measure

```bash
python .github/store/budget.py
```

Note the starting token count — the PR description reports the
before/after.

### 2. Branch

```bash
git switch -c "compaction/$(date -u +%Y%m%dT%H%M%SZ)" origin/main
```

Compaction branches are not `session/` branches: no records are being
written.

### 3. Build the replay cases and the baseline rule set

```bash
git show origin/main:preferences.md > /tmp/baseline-preferences.md
python .github/store/replay.py cases --out /tmp/cases.json
```

`cases.json` holds the last ~20 decisions **masked to their input
side** — question, context, and the options with the recorded
prediction role, cited rules and in-session reasoning stripped out.
The window comes from `replay_window` in `store.config.json`.

### 4. Predict under the baseline set

This is the grilling skill in eval mode: given a rule set and a case's
input side, predict which slot the decider chose.

Delegate this to a **subagent**, one per run, and give it only
`/tmp/cases.json` and the rule-set file. Tell it explicitly: do not
open `decisions/`, do not open `preferences.md`, do not search the
repo. The answers are sitting in this repository, and a scoring run
that has read them measures nothing.

The subagent returns, for every case:

```json
{"predictions": [
  {"id": "<record id>", "predicted_slot": 2, "rules_cited": ["<verbatim rule>"]}
]}
```

`rules_cited` MUST be empty when no rule applies. An honest cold claim
is not a penalty — cold is the control stream. A false cold claim, or
a rule cited that did not drive the prediction, corrupts the gate in
both directions.

Save it, then score:

```bash
python .github/store/replay.py score \
  --predictions /tmp/baseline-predictions.json \
  --preferences /tmp/baseline-preferences.md \
  --out /tmp/baseline-report.json
```

### 5. Compact

Now edit `preferences.md`. The moves, in order of preference:

1. **Drop what is dead.** A rule superseded by a later rule, or whose
   condition can no longer occur, goes. Check the records for a
   `supersedes` chain before assuming.
2. **Merge overlapping rules.** Two rules firing on the same condition
   become one. The merged rule takes the **lowest** counter of its
   constituents and the **most recent** `last:` date — a merged claim
   is only as well-evidenced as its weakest part.
3. **Tighten wording.** Same condition, same falsifiable outcome,
   fewer tokens. This is the safest move and usually the smallest win.

What not to do:

- Do not generalise two narrow rules into one vague one. A rule that
  cannot be wrong is worth less than the tokens it costs.
- Do not invent rules. Compaction has no promotion power; new rules go
  through `proposals/` and a human `pref-promote`.
- Do not touch a counter except as part of a documented merge. Counter
  bumps are `pref-confirm`'s job.
- Do not reflow untouched lines — keep the diff readable.

### 6. Predict under the compacted set and gate

Fresh subagent, same cases, same rules of engagement, the compacted
`preferences.md` as the rule set:

```bash
python .github/store/replay.py score \
  --predictions /tmp/candidate-predictions.json \
  --out /tmp/candidate-report.json
python .github/store/replay.py gate \
  --baseline /tmp/baseline-report.json \
  --candidate /tmp/candidate-report.json \
  --out /tmp/replay-report.json
```

`gate` exits non-zero when the **preference-driven** hit rate
degrades. That stream is the gate. The **cold** stream is the control
group: it measures plain judgment, which a rule-set edit should barely
move — a large swing there says the two runs were not comparable, so
re-run rather than explain it away.

Cases shift streams under the compacted set (a merged rule may now
match a case that was cold, or a dropped rule may leave one cold).
Each case scores under the stream the candidate set assigns; the
report counts the shifts so a hit-rate change caused by re-labelling
rather than by better rules is visible. Read them before trusting a
pass.

If the gate fails: revise the compaction and re-run this step. Never
merge a failing gate, and never edit the report to make it pass.

### 7. Commit

One commit, `pref-promote:` type:

```text
pref-promote: compact active set — 7 rules -> 4 (~1.8k -> ~1.1k tokens)
```

`pref-promote` is the only commit type the vendored guard permits to
remove lines from `preferences.md`. Promotion stays human-only where
it matters: a human merges the PR, and compaction adds no rule that
was not already promoted.

### 8. Open the PR

Draft PR, carrying:

- the carve-out label from `store.config.json`
  (`carve_out_label`, default `preferences-carve-out`) — without it
  CI rejects the edit to existing lines. Create it once if it does not
  exist yet: `gh label create preferences-carve-out`. In managed
  environments use the forge tooling the environment declares, not
  `gh`.
- the replay report, verbatim, in the description:

````markdown
<!-- replay-report -->
```json
{ ...contents of /tmp/replay-report.json... }
```
````

CI checks that the report is gated `pass` AND that its
`candidate_preferences_sha256` matches the `preferences.md` in the PR
head, so a report from before the last edit fails. Re-run step 6 after
any further change to the file, and update the report in the
description.

- a summary of every merge and drop: which rules went, which survived,
  which counter the merged rule inherited, and the before/after token
  count.

## Afterwards

Merging a compaction PR is a decision. If the session that produced it
was a grilling session, it gets a record like any other — through the
recorder, in its own PR. Compaction itself never writes to
`decisions/`.
