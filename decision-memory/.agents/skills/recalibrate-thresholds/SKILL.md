---
name: recalibrate-thresholds
description: Re-measure the ingestion gate's thresholds against the current corpus and propose new values. Use when the gate reports thresholds due a re-measurement, or when a threshold looks wrong on real output.
---

# Recalibrating the ingestion gate's thresholds

> Copier-vendored from the agentic-engineering-template decision-memory
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

Each threshold is a claim about where this corpus separates, and a
false claim stays false silently until someone re-measures.
`false_cold_threshold` once held a value the measure could not reach at
any input — the check was dead for its whole life while every run
reported "no false colds".

The values live in `store.config.json`, not the vendored module,
because the right value is a property of *this* corpus.

## Rules

- Never apply a change yourself. Propose; the human decides.
- Never move a threshold to make a specific verdict go away — the
  measure stops measuring the moment it becomes the target.
- Never report a batch verdict. Each constant gets its own number,
  separation and recommendation.
- Never inherit a stamp you did not measure.

## The constants

`config.CALIBRATED` is the authoritative list.

| Constant | Governs | Fails by |
| --- | --- | --- |
| `similarity_threshold` | Which pairs reach a human at all | Too high: duplicates ingest silently and become permanent |
| `containment_threshold` | The split channel — one draft re-extracted as two | Too high: splits stay invisible, since jaccard cannot see them |
| `artifact_boost` | How much repo+path agreement lifts a borderline pair | Wrong either way *without showing in a score you read* |
| `answer_agreement` | Whether two rewordings count as the same answer | Too high: every reworded duplicate lands in `uncertain` |
| `false_cold_threshold` | Rule coverage that flags a suspect `cold` | Too high: the check cannot fire, and reports success |

Watch `artifact_boost` hardest: weakest evidence, and it acts *through*
`similarity_threshold`, so a wrong value changes verdicts without
appearing in any output a human reads.

## 1. Ask what is due

```bash
python .github/store/similarity.py --json --out /tmp/gate.json
```

`stale_calibrations` names each constant and why:

- **never measured** — no stamp; nobody has checked this *here*.
- **outgrown** — the corpus grew past the stamp by
  `calibration_growth_factor`. The evidence expired, not necessarily
  the value.

Recalibrate what is due, or what looks wrong on real output.
Re-measuring everything on a schedule invites tuning-to-taste.

## 2. Measure the distribution

Score **every** pair or record in the corpus and find the **gap**: a
range with values above and below it and nothing inside.

```text
0.4286   <- above
  ...gap...
0.25     <- below
0.1429
```

A threshold in a gap is robust. A threshold on a slope, values packed
either side, is one ingestion away from flipping — report that even
when you leave the number alone.

Record per constant: **separation** (gap width) and **corpus_size**.

## 3. Check both directions against the cost

Costs are asymmetric, differently per constant. For the pair
thresholds a false cluster costs one glance while a missed duplicate
costs an immutable record — lean generous. For `false_cold_threshold` a
false flag costs a dismissal while a miss permanently understates a
rule's evidence and corrupts the replay gate's stream split.

State what moving it each way would have changed **in the corpus you
just measured** — how many pairs enter or leave. A recommendation with
no count behind it is a preference.

## 4. Propose, one constant at a time

```markdown
### «constant» — «keep «current»» / «change «current» -> «proposed»»

**Measured:** «n» values over «corpus_size» records.
Nearest above: «x». Nearest below: «y». Separation: «x - y».

**Today's value sits:** in the gap / on a slope between «y» and «x».

**Moving it up to «z»:** «n» pairs stop surfacing — «which, and
whether any looked real».

**Moving it down to «w»:** «n» pairs start surfacing — «how many are
noise».

**Recommendation:** «keep / change», because «the deciding cost».
```

If a constant has no gap — values smeared across the range — say so.
The answer is a better measure, not a better number; moving a threshold
around a smear only relocates the errors.

## 5. Hand over

The human applies value and stamp to `store.config.json`:

```json
{
  "false_cold_threshold": "«value»",
  "calibration": {
    "false_cold_threshold": {
      "corpus_size": "«n»",
      "separation": "«gap»",
      "measured": "«YYYY-MM-DD»"
    }
  }
}
```

Stamp every constant you measured, **including unchanged ones** —
without the stamp, "measured and unchanged" is indistinguishable from
never having looked.

## A recalibration is a decision

It has options, a chosen one, and rejected alternatives with reasons.
Log the constant, the chosen value, and the rejected values with their
measured consequences, so a later reader asking "why this number?"
finds the distribution rather than a commit message.

Commit as `chore(calibration): ...` with the measurement in the body
and open a PR. An agent that can both move a threshold and merge the
move has closed a loop nobody is watching.
