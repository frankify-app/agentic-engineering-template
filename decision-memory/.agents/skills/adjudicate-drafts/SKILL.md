---
name: adjudicate-drafts
description: Work the ingestion gate's clusters into a decision the human can make in one pass — propose a resolution per cluster, lay out what each way costs, and name what becomes irreversible. Use after running the ingestion gate, when drafts are flagged duplicate/re-decision/uncertain, or when a drafts batch is about to be ingested.
---

# Adjudicating flagged drafts before ingestion

> Copier-vendored from the agentic-engineering-template decision-memory
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

The ingestion gate finds clusters.
It deliberately does not resolve them:
every resolution trades one loss against another,
and picking the trade is the human's job.

This skill is the bridge.
It turns each cluster into a **decision with its implications laid out**,
so the human answers rather than investigates.

**Why the deadline is real.**
`decisions/` is append-only with no carve-out.
Once ingested, a duplicate cannot be withdrawn,
a missing link cannot be added,
and a wrong resolution is permanent.
Every option below is available exactly once.

**Why it is not cosmetic.**
An undetected duplicate does not merely waste a file —
it **double-counts as evidence**.
Extraction reads cross-record repetition as the signal that a pattern
is a principle rather than a one-off,
so one ruling recorded twice manufactures the exact evidence the
preference set is supposed to earn.
The replay harness then scores the same case twice.

## What you do NOT do

- **Never edit `decisions/`.** Everything here happens in the drafts.
- **Never delete a draft.** Discards move to `discarded-drafts.json`,
  which keeps the record of what was rejected and why.
- **Never resolve silently.** Every cluster gets a stated resolution,
  including "these are genuinely independent" — that is a finding, not
  a non-answer.
- **Never pick for the human on a judgement call.** Propose, with the
  cost of each way. `uncertain` exists because the tool could not tell;
  inheriting that uncertainty and hiding it is worse than surfacing it.

## Procedure

### 1. Run the gate

```bash
python .github/store/similarity.py --drafts <drafts.json> --json --out /tmp/gate.json
python .github/store/similarity.py --drafts <drafts.json>
```

Work the clusters in the order the gate ranks them: `duplicate`,
`re-decision`, `uncertain`, `linked`. A `linked` cluster is
informational — confirm the existing edge points the right way and move
on.

Note how each pair surfaced. A pair surfaced by **containment** rather
than similarity is the signature of a **split**: one draft
re-extracted as two. Check whether a third draft covers the rest of the
bundle, because pairwise comparison will not tell you.

### 2. Read both drafts fully

The gate's field diff is a pointer, not a summary. Before proposing
anything, know for each side:

- **The operative reason and its source.** A `stated` reason is the
  decider's own words and the highest-value field in the record.
  `inferred` is the model's guess. Discarding the side that carries the
  only stated reason destroys evidence the other side never had.
- **`artifact_ref` completeness.** Complete beats partial beats null,
  and this is the last moment enrichment is possible.
- **Rejection depth.** More rejections with `operative` status means
  more recoverable reasoning.
- **Links already written.** `related_slugs`, `supersedes_slug`,
  `drill_down_of_slug` — a draft embedded in a graph costs more to
  discard than an isolated one.
- **Scope.** Two drafts of one ruling often differ in how much they
  claim. The wider one may be a genuine refinement rather than a
  restatement.

### 3. Propose a resolution, with its cost

Per cluster, write the human a block they can answer without opening
the files. Name the resolution, then what it costs, then what it makes
permanent.

The resolutions available:

| Resolution | When | What it costs |
| --- | --- | --- |
| **Keep one, discard the other** | Same ruling, one side strictly richer | Whatever the discarded side held that the kept side does not — check the stated reason first |
| **Keep both, add a link** | Distinct rulings that inform each other, or a genuine re-decision | Nothing, if the edge direction is right; a wrong direction is permanent |
| **Keep both, no link** | Genuinely independent despite the overlap | A missed edge, permanently — the graph stays disconnected |
| **Merge into one draft** | Each side carries something the other lacks | Hand-writing a draft that is faithful to both; the two originals go to `discarded-drafts.json` |
| **Split is real** | One draft covers what two others cover separately | Deciding which granularity is the record — the bundle or the parts, not both |

Write it in this shape:

```markdown
### «left-slug» ~ «right-slug» — «verdict» «score»

**Same ruling?** Yes — both rule «what was decided».

**Proposed:** keep «right-slug», discard «left-slug».

**Why that direction:** «right-slug» carries a stated operative reason
(«quote»); «left-slug» has only inferred rejections. Both have a null
artifact_ref.

**What it costs:** «left-slug»'s «field» is not represented in
«right-slug» — «what is lost».

**Irreversible after ingestion:** the discard, and the absence of a
`related` edge between them.

**The other way:** keep both linked if «the reason someone might».
```

State a recommendation. A list of options with no position is work
handed back, not a decision made easy.

### 4. Apply what the human decides

In the **drafts**, never the store:

- Discards move to `discarded-drafts.json` in the same directory, with
  a `discarded_because` field naming the surviving slug and the
  reason. Never delete.
- Links go in as the batch-local slug forms — `related_slugs`,
  `supersedes_slug`, `drill_down_of_slug` — which the recorder resolves
  to IDs at ingestion.
- Merges are hand-written; both originals go to
  `discarded-drafts.json` pointing at the merged slug.

### 5. Re-run the gate

```bash
python .github/store/similarity.py --drafts <drafts.json>
```

Every cluster should now be `linked`, or gone. A cluster still reading
`duplicate` or `uncertain` is unresolved, and ingesting over it is the
one thing that cannot be undone.

Then handle the other two sections while the drafts are still mutable:

- **`false-cold?`** — confirm or dismiss each flag. A confirmed false
  cold is restreamed in the draft: `prediction_stream` becomes
  `preference-driven` and `rules_cited` names the rule. Dismiss the
  rest; a rule sharing vocabulary is not a rule that drove anything.
- **`artifact_ref` tiers** — enrich every `partial` and `null` where
  the artifact now exists. Never guess a SHA; a partial ref with a real
  repo and path beats a fabricated commit.

## Afterwards

Ingest through the recorder as normal. The records are immutable from
that moment, which is the whole reason this pass exists.

If adjudicating produced a ruling worth remembering — a policy on when
two extractions count as one decision, say — that is a decision like
any other and belongs in a grilling session, not in this pass.
