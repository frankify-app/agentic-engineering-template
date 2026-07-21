# Extraction Prompt — Draft Decision Records from a Past Conversation

Copy the fenced prompt below into any chat — the conversation you
want to mine, or a chat that has it attached. No tools, code
execution, or repo access are needed there: the output is plain JSON.

Then ferry the output here: save it as `drafts.json` (or copy the
fenced block) and, in a session with repo access, ingest it with the
recorder — `record.py open`, then `record --from drafts.json`, then
`check`, then `submit`. Before ingesting, enrich `artifact_ref` in
the drafts file wherever the referenced commits now exist —
extraction leaves refs null by design (never guess SHAs), and drafts
are plain JSON, editable freely until ingestion. Validation happens
ONLY at ingestion, against this repo's vendored validator; malformed
drafts fail loudly there, where an agent can fix them with you. There
is deliberately no chat-side validator to drift.

This prompt mirrors the record schema in
[conventions.md](conventions.md); both are vendored from the template
repo's store subtemplate — change them together there, in the same
PR.

````text
You are extracting decision records from THIS conversation, for an
append-only decision-memory repository.

TASK: Sweep the ENTIRE conversation and identify every durable ruling
— a question that was resolved by choosing between alternatives, with
reasons: design decisions, scope calls, convention adoptions, tool
choices, process rules. Skip trivial or ephemeral choices that would
not inform future decisions. Then emit one DRAFT RECORD per ruling.

OUTPUT: one JSON array of draft records and nothing else. Prefer a
downloadable drafts.json when your environment supports file output
(large batches are hostile to inline fences); otherwise emit a single
fenced JSON array. Do not validate, do not add commentary inside the
output.

DRAFT RECORD FIELDS (a draft is the record schema MINUS tool-minted
fields — do NOT invent v, type, id, date, or timestamps; the
ingestion tool mints them):

- slug: short kebab-case title for the decision, lowercase, <= 40
  chars, unique within this batch.
- project: short logical project name the ruling belongs to.
- question: the question that was decided.
- context: session-local facts that informed the options, as known
  BEFORE the ruling.
- options: the alternatives actually on the table, as discussed —
  never reconstructed after the fact. Each: {"slot": <int>, "label":
  <text>} plus, where present in the conversation: "role",
  "if_clause", "rules_cited", "reasoning". Exactly ONE option must
  carry a prediction role ("prediction" or
  "prediction+recommendation"); if the conversation had no explicit
  prediction, give the option that was recommended at the time the
  role "prediction+recommendation" with "rules_cited": [].
- prediction_stream: "preference-driven" if the prediction explicitly
  cited active preference rules (then rules_cited must name them),
  else "cold" (then rules_cited must be empty).
- artifact_ref: {"repo", "path", "commit", "anchor"} of the artifact
  the decision was about, when one exists and is identifiable from
  the conversation; otherwise null. Never guess commit SHAs — a
  PARTIAL ref (repo/path/anchor with "commit": null) beats all-null
  and gets enriched at ingestion.
- chosen_slot: the slot that won; use a fresh slot number with
  "chosen" free text when the ruling was none of the listed options.
- chosen: what was chosen, in the decider's words or the option
  label — strip UI decorations such as "(Recommended)"; they are the
  button caption, not the choice.
- operative_reason: the stated reason for the choice, verbatim where
  possible. Required whenever a listed non-prediction option won —
  EXCEPT silent picks: when the decider chose without stating any
  reason, set "operative_reason": null and declare
  "operative_reason_source": "none". There is deliberately no
  inferred tier here — operative means decider-confirmed; put your
  inferred why-chosen in the chosen option's reasoning and in the
  rejections instead.
- correction: true only when the decider corrected the reasoning ("N,
  but actually because..."), else false.
- rejections: one entry per rejected option: {"option", "reason",
  "reason_source", "status", "reason_class": "TBD"}. status
  "operative" = the decider actually stated this reason (record
  verbatim, no inference; "reason_source": "stated" or omitted).
  status "presumed-false" = the most-likely reason the option lost,
  with its provenance DECLARED in reason_source: "if_clause" (ONLY
  when the option literally carries an if_clause field, which did not
  hold — reuse it as the reason; text drawn from its reasoning is
  "inferred"),
  "inferred" (your best inference from context, marked as such), or
  "none" (nothing stated or inferable — ONLY then set "reason": null;
  never a filler string like "none stated", and never "none" as the
  easy way out when context supports an inference).
- outcome: "hit" if chosen_slot equals the prediction option's slot,
  "refined" if the chosen answer CONTAINS the prediction plus an
  extension or qualification (right but incomplete — do not score
  these as misses), "miss" if the prediction was actually wrong,
  "near-tie" when the decider declared it too close to score.
- In-batch references — name OTHER DRAFTS IN THIS BATCH by slug;
  the ingestion tool resolves them to minted IDs. Use these — never
  prose in notes: supersedes_slug (this ruling replaces that one),
  drill_down_of_slug (this ruling answers a follow-up question opened
  by that one), related_slugs (list; informs/refines).
- Optional, only when the conversation supports them: notes,
  closure_of (number of a closed-unmerged PR this ruling explains),
  session (the conversation/session identifier if known). Leave
  related / supersedes / drill_down_of OUT unless you are referencing
  record IDs that already exist in the repository (for in-batch
  references, use the slug fields above).

RULES:
- Input side before output side: report options and reasoning as they
  stood BEFORE the ruling; never back-fill a recommendation after the
  choice is known.
- Verbatim over paraphrase for reasons; paraphrase only to compress,
  never to improve.
- When conversation evidence for a field is missing, prefer omitting
  the optional field or using null over inventing content.
- One record per ruling; split multi-part rulings into separate
  records rather than merging them.
````
