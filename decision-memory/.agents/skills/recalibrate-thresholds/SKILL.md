---
name: recalibrate-thresholds
description: Re-measure the ingestion gate's calibrated thresholds against the current corpus and propose per-constant changes with their evidence. Use when the gate reports thresholds due a re-measurement, when a threshold looks wrong on real output, after a large ingestion batch, or when asked to recalibrate or re-evaluate the similarity thresholds.
---

# Recalibrating the ingestion gate's thresholds

> Copier-vendored from the agentic-engineering-template decision-memory
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

The gate's thresholds are not settings. Each one is a **claim about
where a real distribution separates**, and a claim can be false — and
stay false silently, for as long as nobody re-measures.

That is not hypothetical. `false_cold_threshold` was once set to a
value the measure could not reach at any input: rules ran 7–8 tokens,
records 20–42, and jaccard's denominator capped a verbatim quote at
0.167 against a 0.18 bar. The check was dead for its entire life and
every run reported "no false colds", which read exactly like good news.

**This is why the numbers live in `store.config.json` and not in the
vendored module.** The right value is a property of *this store's*
corpus. Two stores with different corpora should hold different
numbers, and neither should have to edit vendored code to say so.

## What you do NOT do

- **Never apply a change yourself.** Propose; the human decides. A
  threshold quietly tuned until the gate stops complaining is a gate
  that has been switched off without anyone deciding to switch it off.
- **Never move a threshold to make a specific verdict go away.** That
  is the Goodhart failure this whole loop is built to resist: the
  measure stops measuring the moment it becomes the target.
- **Never report a batch verdict.** "Thresholds look fine" is not a
  finding. Each constant gets its own number, its own separation, and
  its own recommendation.
- **Never inherit a stamp you did not measure.** A constant with no
  calibration record has never been checked *here*, whatever the
  template's default implies.

## The constants

`config.CALIBRATED` is the authoritative list. What each one governs:

| Constant | Governs | Fails by |
| --- | --- | --- |
| `similarity_threshold` | Which pairs reach a human at all | Too high: duplicates ingest silently and become permanent |
| `containment_threshold` | The split channel — one draft re-extracted as two | Too high: splits stay invisible, since jaccard cannot see them |
| `artifact_boost` | How much repo+path agreement lifts a borderline pair | Wrong either way *without ever showing in a score you read* |
| `answer_agreement` | Whether two rewordings count as the same answer | Too high: every reworded duplicate lands in `uncertain` |
| `false_cold_threshold` | Rule coverage that flags a suspect `cold` | Too high: the check cannot fire, and reports success |

Watch `artifact_boost` hardest. It has the weakest evidence and it acts
*through* `similarity_threshold`, so a wrong value changes verdicts
without appearing anywhere in the output a human reads.

## Procedure

### 1. Ask what is actually due

```bash
python .github/store/similarity.py --json --out /tmp/gate.json
```

The `stale_calibrations` block names each constant and why:

- **never measured** — no stamp. Nobody has checked this *here*.
- **outgrown** — the corpus has grown past the stamp by
  `calibration_growth_factor`. What expired is the evidence; the value
  may well still be right.

Recalibrate a constant that is due, or one whose output looks wrong.
Re-measuring everything on a schedule invites tuning-to-taste.

### 2. Measure the distribution, do not guess at it

For each constant, score **every** pair or record in the corpus and
look at where the values actually fall. You are looking for a **gap**:
a range with values above it and values below it and nothing inside.

```text
0.4286   <- above
  ...gap...
0.25     <- below
0.1429
```

A threshold in a gap is robust: small corpus changes do not move
verdicts. A threshold on a slope, with values packed either side, is
one ingestion away from flipping — and that is a finding worth
reporting even when you leave the number alone.

Record two things per constant:

- **separation** — the width of the gap the threshold sits in.
- **corpus_size** — how many records the measurement covered.

### 3. Check both directions against the cost

The costs are not symmetric, and the asymmetry differs per constant.
For the pair thresholds, a false cluster costs one glance; a missed
duplicate costs an immutable record that can never be withdrawn. Lean
generous. For `false_cold_threshold`, a false flag costs a dismissal; a
miss permanently understates a rule's evidence and silently corrupts
the replay gate's stream split.

State, per constant, what moving it each way would have changed **in
the corpus you just measured** — how many pairs enter or leave. A
recommendation with no count behind it is a preference.

### 4. Propose, one constant at a time

```markdown
### «constant» — «keep 0.4» / «change 0.4 -> 0.45»

**Measured:** «n» values over «corpus_size» records.
Nearest above: «x». Nearest below: «y». Separation: «x - y».

**Today's value sits:** in the gap / on a slope between «y» and «x».

**Moving it up to «z»:** «n» pairs stop surfacing — «which ones, and
whether any looked real».

**Moving it down to «w»:** «n» pairs start surfacing — «how many are
noise».

**Recommendation:** «keep / change», because «the cost that decides
it».
```

If a constant has no gap — values smeared across the range — say so
plainly. That means the measure is not separating anything, and the
answer is a better measure, not a better number. Moving the threshold
around a smear only relocates the errors.

### 5. Hand over

The human applies the change to `store.config.json`: the value, and its
stamp under `calibration`:

```json
{
  "false_cold_threshold": 0.4,
  "calibration": {
    "false_cold_threshold": {
      "corpus_size": 94,
      "separation": 0.18,
      "measured": "2026-07-27"
    }
  }
}
```

Stamp every constant you measured, **including the ones you left
alone** — "measured and unchanged" is a result, and without the stamp
it is indistinguishable from never having looked.

## A recalibration is a decision

Changing a threshold changes which records the store will ever see as
duplicates. It has options, a chosen one, and rejected alternatives
with reasons — which is the definition of a record this store already
exists to keep.

Log it: the constant, the value chosen, the values rejected and their
measured consequences. A later reader asking "why 0.4?" should find the
distribution that answered it, not a commit message.

Commit as `chore(calibration): ...` with the measurement in the body,
and open it as a PR. The human gate is the point — an agent that can
both move a threshold and merge the move has closed a loop nobody is
watching.
