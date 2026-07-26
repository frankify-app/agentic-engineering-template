---
name: extract-preferences
description: Extract candidate preference rules from decision records — confirm rules the records support, flag rules they contradict, propose rules for patterns no rule covers — then open one PR with the marker advanced. Use when records have accumulated since the last extraction pass, when the user asks to extract preferences or mine decisions for rules, or before compacting a preference set that has never been extracted into.
---

# Extracting preference rules from decision records

> Copier-vendored from the agentic-engineering-template decision-memory
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

`decisions/` records what happened.
`preferences.md` tells the next session what to expect.
Extraction is the only thing connecting the two,
and until it runs the corpus grows while the rule set stands still —
every record lands `prediction_stream: cold`,
because no rule was ever there to drive a prediction.

**Extraction precedes compaction.**
There is nothing to compact until rules have been extracted,
and the compaction replay gate cannot measure a rule set
that no record was ever scored against.
If a store has never been extracted into,
run this before reaching for `compact-preferences`.

Manual trigger only. A human merges the result.

## Invariants

Break any of these and CI rejects the PR, as it should.

- **`decisions/` is read-only here.** Extraction reads history and
  proposes rules. It never modifies, deletes, or renames a record, and
  there is no carve-out that would let it.
- **Merging is not promotion.** Agents write candidate rules to
  `proposals/`; only a human `pref-promote` commit moves text into
  `preferences.md`. This skill never edits the active set except for
  `pref-confirm` counter bumps.
- **One outcome per pattern.** Confirm, flag drift, or propose. Never
  two, never a silent overwrite of a rule the records contradict.
- **The marker moves once, at the end.** Advancing it mid-pass loses
  the batch if the pass is abandoned.

## Procedure

Run from the repo root, on a clean tree, with `main` up to date.

### 1. Size the batch

```bash
python .github/store/extraction.py status
```

Nothing since the marker means nothing to do. Stop.

### 2. Branch

```bash
git switch -c "extraction/$(date -u +%Y%m%dT%H%M%SZ)" origin/main
```

Not a `session/` branch: no decisions are being recorded.

### 3. Build the batch

```bash
python .github/store/extraction.py batch --out /tmp/batch.json
```

The batch holds every record after the marker, sorted into four queues.
Work them in order — the order is the evidence ranking:

1. **`corrections`** — a `"N, but actually because…"` ruling. The
   decider stated their own reason where the model had guessed wrong,
   so this is the one place the corpus carries a reason nobody
   inferred. Highest signal in the store; process these first and let
   what they teach reshape how you read the rest.
2. **`misses`** — the prediction was wrong. Every miss must do one of
   three things: refine an existing rule, split one that was covering
   two conditions, or spawn a candidate. A miss that does none of them
   is written down as unexplained. Unexplained is a state, not a
   silence — an unexplained miss is the seed of the next pass.
3. **`refinements`** — `refined` and `near-tie` outcomes. The rule was
   directionally right and incomplete. Usually a wording or condition
   change, rarely a new rule.
4. **`confirmations`** — clean hits. Cheap counter bumps, and the
   evidence that a rule is earning its tokens.

### 4. Find the patterns

Read across the whole batch before writing anything. A single record
cannot distinguish a principle from a one-off; **cross-session
repetition is the evidence**, and it is the only evidence a per-session
pass could never see. Two records from the same session agreeing is one
data point, not two.

Compare each candidate pattern against the current `preferences.md` and
everything already sitting in `proposals/` — a rule proposed last pass
and not yet promoted is not a new discovery.

### 5. Classify — exactly one outcome each

**a) Matches an existing rule → confirm.**

Bump the counter and the date. One commit per rule:

```text
pref-confirm: rejects new infrastructure dependencies (n=5)
```

CI validates the math: increment by exactly 1, rule text unchanged.

Do **not** bump on a record listed in `rule_driven_acceptances`. There
the rule cited itself into the prediction slot and that slot was
chosen — the recommendation caused the choice it would now be credited
with predicting. Zero independent evidence. The batch flags these
because the temptation to count them is the whole problem.

**b) Contradicts an existing rule → flag drift.**

Never rewrite the rule. Write `proposals/<YYYY-MM-DD>-drift-<slug>.md`
naming the rule, the records that contradict it, and a choice between
conditionalizing it (the rule holds, but only under a condition the
records now show) and retiring it (the principle changed).

```text
pref-drift: infrastructure rule mispredicts solution shape (3 records)
```

The decision between the two belongs to the human merging the PR.
Present it as a decision, not as a recommendation dressed up as one.

**c) Genuinely new → propose.**

`proposals/<YYYY-MM-DD>-<slug>.md`, one rule per file, in conditional
and falsifiable form: a condition, an outcome, and a way to be wrong.

```text
pref-proposal: prefers the simplest solution that solves the actual problem
```

A rule that cannot be wrong is worth less than the tokens it costs. If
you cannot state what would falsify it, it is an observation, not a
rule.

### 6. Advance the marker

The final commit of the PR, and only once the rest of the pass is
committed:

```bash
python .github/store/extraction.py mark --record-id "$(python -c 'import json;print(json.load(open("/tmp/batch.json"))["next_marker"])')"
git add extraction-marker.json
git commit -m "chore: extraction marker -> <id>"
```

The marker never moves backwards and must name a record that exists —
CI checks both.

### 7. Open the PR

Draft PR, carrying:

- what was found, per queue, with counts;
- every proposal and drift flag, and the records behind each;
- every unexplained miss, named. A pass that explains nothing is a
  legitimate result and must be visible as one;
- the counter bumps, and — separately — the rule-driven acceptances
  that were deliberately NOT counted.

Merging is promotion only for the `pref-confirm` bumps. Proposals and
drift flags land as files; a human turns them into rules with a
`pref-promote` commit, or does not.

## Afterwards

A preference set that has just grown is a candidate for compaction, not
an obligation. Check the budget:

```bash
python .github/store/budget.py
```

Compact when the budget workflow says compression is due — through
`compact-preferences`, which now has a preference-driven stream to
measure itself against.
