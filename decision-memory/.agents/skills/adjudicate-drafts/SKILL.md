---
name: adjudicate-drafts
description: Resolve the ingestion gate's flagged clusters — in drafts before ingestion, in a branch's records before merge. Use when drafts are flagged duplicate/re-decision/uncertain, or before merging any PR that adds decision records.
---

# Adjudicating flagged records

> Copier-vendored from the agentic-engineering-template decision-memory
> subtemplate — do NOT edit it in the store repo;
> change it in the template and pull via `copier update`.

The gate finds clusters and does not resolve them. This skill turns
each cluster into a decision the human answers in one pass.

Two moments, and every record-adding PR hits at least the second:

1. **Drafts, before ingestion** — sections 1-5. The full remedy set is
   available because nothing is written yet.
2. **A branch's records, before merge** — the pre-merge link pass at
   the end. A session that recorded natively through the recorder
   never had drafts and starts there.

`decisions/` is append-only with no carve-out: after ingestion a
duplicate cannot be withdrawn and a missing link cannot be added.

A duplicate is not just a wasted file. Extraction reads cross-record
repetition as evidence that a pattern is a principle, so one ruling
recorded twice manufactures that evidence, and the replay harness
scores the case twice.

## Rules

- Never edit `decisions/`. Everything here happens in the drafts.
- Never delete a draft. Discards move to `discarded-drafts.json`.
- Never leave a cluster unresolved. "Genuinely independent" is a
  resolution; silence is not.
- Never pick for the human on a judgement call — `uncertain` means the
  tool could not tell. Propose with costs.

## 1. Run the gate

```bash
python .github/store/similarity.py --drafts <drafts.json> --out /tmp/gate.json
python .github/store/similarity.py --drafts <drafts.json>
```

Work clusters in the gate's order: `duplicate`, `re-decision`,
`uncertain`, `linked`. A `linked` cluster is informational — confirm
the edge points the right way and move on.

A pair surfaced by **containment** rather than similarity signals a
**split**: one draft re-extracted as two. Check whether a third draft
covers the rest of the bundle — pairwise comparison will not tell you.

## 2. Read both drafts

The gate's field diff is a pointer, not a summary. Per side:

- **Operative reason and its source.** `stated` is the decider's own
  words, `inferred` is the model's guess. Discarding the side with the
  only stated reason destroys evidence the other side never had.
- **`artifact_ref` completeness.** Complete beats partial beats null,
  and this is the last moment to enrich it.
- **Rejection depth.** More `operative` rejections, more recoverable
  reasoning.
- **Links already written** — `related_slugs`, `supersedes_slug`,
  `drill_down_of_slug`.
- **Scope.** The wider draft may be a refinement, not a restatement.

## 3. Propose a resolution with its cost

| Resolution | When | Cost |
| --- | --- | --- |
| Keep one, discard the other | Same ruling, one side strictly richer | Whatever the discarded side held — check the stated reason first |
| Keep both, add a link | Distinct rulings that inform each other, or a real re-decision | A wrong edge direction is permanent |
| Keep both, no link | Genuinely independent | A permanently missed edge |
| Merge into one draft | Each side carries something the other lacks | Hand-writing a faithful draft; both originals discarded |
| Split is real | One draft covers what two others cover separately | Choosing which granularity is the record — bundle or parts, not both |

Write each cluster so the human can answer without opening the files:

```markdown
### «left-slug» ~ «right-slug» — «verdict» «score»

**Same ruling?** Yes — both rule «what was decided».

**Proposed:** keep «right-slug», discard «left-slug».

**Why:** «right-slug» has a stated operative reason («quote»);
«left-slug» has only inferred rejections. Both `artifact_ref` null.

**Cost:** «left-slug»'s «field» is not represented in «right-slug».

**Irreversible after ingestion:** the discard, and the absent
`related` edge.

**The other way:** keep both linked if «reason».
```

State a recommendation. Options with no position is work handed back.

## 4. Apply the decision

In the **drafts**, never the store:

- Discards move to `discarded-drafts.json` in the same directory, with
  a `discarded_because` naming the surviving slug and the reason.
- Links go in as batch-local slugs — `related_slugs`,
  `supersedes_slug`, `drill_down_of_slug` — which the recorder resolves
  to IDs at ingestion.
- Merges are hand-written; both originals are discarded, pointing at
  the merged slug.

## 5. Re-run the gate

```bash
python .github/store/similarity.py --drafts <drafts.json>
```

Every cluster should now read `linked`, or be gone. Anything still
`duplicate` or `uncertain` is unresolved.

Then, while the drafts are still mutable:

- **`false-cold?`** — confirm or dismiss each flag. A confirmed false
  cold gets `prediction_stream: preference-driven` and `rules_cited`
  naming the rule. Dismiss the rest: a rule sharing vocabulary is not a
  rule that drove anything.
- **`artifact_ref` tiers** — enrich every `partial` and `null` whose
  artifact now exists. Never guess a SHA; a partial ref with a real
  repo and path beats a fabricated commit.

## Afterwards

Ingest through the recorder, then run the pre-merge link pass below
before the PR merges.

A ruling worth remembering from this pass — a policy on when two
extractions count as one decision, say — is a decision like any other
and belongs in a grilling session, not here.

## The pre-merge link pass

Run this on **every** record-adding PR, drafts or not, immediately
before merge. A session that recorded natively through the recorder
never had drafts and so never ran the sections above — this pass is the
part that still applies to it.

**Why immediately before merge.** At record time the corpus is whatever
`main` was then; other PRs land in between. Merge is the last moment
the corpus is complete AND the branch is still mutable. Records are not
immutable until merge — merging is the acceptance, and
`docs/conventions.md` § PR flow already sanctions hand-editing the
branch before it.

```bash
git rebase origin/main
python .github/store/similarity.py --out /tmp/gate.json
```

Rebase first, or the gate checks against a corpus missing everything
merged since the branch was cut.

### What you can do here, and what you cannot

The remedy set is narrower than for drafts. The records exist as
commits, so there is no `discarded-drafts.json` to move anything into.

| Remedy | Available |
| --- | --- |
| Add a link | yes — the point of this pass |
| Drop the record | only by dropping its commit |
| Discard to `discarded-drafts.json` | no — that is a drafts-only remedy |
| Edit the record on the other side | **never** — it is merged and immutable |

Amending a record already committed on this branch is fine: the
append-only guard diffs `base...HEAD`, so a record added and later
amended within one PR still reads as an addition.

### Links only ever point backwards

A link target must already exist in `decisions/` — the validator
rejects a dangling ref, and correctly, since a record must not point at
something that may never merge.

So two PRs open at once cannot reference each other. **The edge is
written by whichever merges second**, pointing back at the first, and
the first can never gain the reverse edge once it is merged.

That is why this pass has to run on every PR rather than only on ones
that looked interesting at record time: applied uniformly, the
second-merging PR always catches the pair, and nothing has to see
across open PRs at all.

### Judging what surfaces

Most pairs will be noise. Containment on a short record fires easily —
most of a five-token record is contained in anything sharing two of its
words — so read the questions, not the score.

The judgement is different from the drafts case. There, the question is
*"are these one ruling?"* Here both records are staying, so the
question is only *"does an edge belong between them, and which way?"*

- **`related`** — two rulings that inform each other.
- **`supersedes`** — the later one replaces the earlier. Only when it
  genuinely overrides; a later ruling that refined or re-confirmed the
  same answer is `related`.
- **nothing** — same subject, independent rulings. A legitimate
  outcome; record that you looked.

Two records sharing a slug are worth reading closely and are **not**
thereby duplicates. Slugs follow the topic, so two rulings on one topic
collide naturally — the deliberation tells you which it is: option
count, rejection depth, and whether the outcome was a plain hit or a
refinement.

Commit the links as `chore:` — they are not new decisions, and no other
commit type fits.
