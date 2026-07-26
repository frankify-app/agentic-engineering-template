---
name: extract-preferences
description: Extract candidate preference rules from the decision records recorded since the last extraction pass — confirm rules the records support, flag rules they contradict, propose rules for patterns no rule covers — and close with a pref-extract commit. Use when ingesting a decision session, when the user asks to extract preferences or mine decisions for rules, or before compacting a preference set that has never been extracted into.
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

**The watermark is a commit.** Every pass ends with a `pref-extract:`
commit, so the scope is everything recorded since the last one —
derived from history rather than tracked beside it. Nothing to advance,
nothing to keep in sync, nothing to conflict when two branches run a
pass at once.

Two things follow, and both matter to you while running this:

- **A missed pass is not lost.** If a session merged without one, the
  watermark is simply older and this pass picks those records up too.
  Read the scope before assuming it is only your session's.
- **The first pass on a corpus needs no special mode.** No
  `pref-extract:` commit anywhere means the watermark is the beginning
  of the corpus, so everything is in scope by construction.

**An empty pass still commits.** A pass that finds nothing produces no
proposal and no counter bump, so if the watermark keyed on those it
would stall every time extraction legitimately had nothing to say.
"Extraction ran and found nothing" is information, and the commit is
where it goes.

Scope and evidence are different things:

- **Scope** — what you must act on — is the records since the
  watermark.
- **Evidence** — what you may reason from — is the whole corpus. The
  batch ships `history` alongside the scope for exactly this reason. A
  pattern is not new because this session is the first to show it.

A human merges the result.

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
- **The pass commit comes last.** A PR that adds records must contain
  a `pref-extract:` commit with no record added after it — a record
  landing later is one the pass never saw. CI checks both, positionally:
  there is nothing to enumerate and nothing that could be copied from
  another branch.

## Procedure

Run from the repo root, on the session branch whose records you are
ingesting — this is a step in that PR, not a separate branch. Fetch
`main` first so the watermark walk sees every pass that has landed.

### 1. Size and build the batch

```bash
python .github/store/extraction.py status
python .github/store/extraction.py batch --out /tmp/batch.json
```

`scope` is everything recorded since the watermark; `history` is what
earlier passes already covered, shipped as evidence. `watermark` in the
batch names the commit it walked back to, or `null` on a corpus no pass
has touched yet.

If the scope is larger than your own session, an earlier one merged
without a pass. That is the design working — cover them all.

The scope records are sorted into four queues. Work them in order —
the order is the evidence ranking:

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

### 2. Find the patterns

Read `history` before writing anything. A single record cannot
distinguish a principle from a one-off, and two records from the same
session agreeing is one data point, not two — **cross-session
repetition is the evidence**. Scoping the pass to this PR does not
narrow what you may reason from; it narrows what you must act on. A
pattern that appears once here and twice in `history` is a three-record
pattern.

Compare each candidate against the current `preferences.md` and
everything already sitting in `proposals/` — a rule proposed on an
earlier branch and not yet promoted is not a new discovery.

### 3. Classify — exactly one outcome each

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

### 4. Close the pass

The last commit of the PR, after every proposal, drift flag and counter
bump has landed:

```bash
git commit --allow-empty -m "pref-extract: 4 records — 1 proposal, 1 unexplained"
```

`--allow-empty` because a pass that found nothing has nothing else to
commit, and that pass must still move the watermark. Put the detail in
the body — records covered, what was found, what was left unexplained.
Nothing parses it; it is there for whoever reads the log.

This commit is the watermark. It must come **after** every record in
the PR, because extraction is the last step of the pass — CI fails a
record added after it.

### 5. Write the rest of the PR description

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
