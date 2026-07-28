# Evidence Memory

> Copier-vendored from the agentic-engineering-template evidence
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

A private, data-only store of immutable **detection records**: bugs and
features found while working, kept so the next person to hit the same
thing finds it instead of filing it again.

## What lives here, and what does not

| Here | Not here |
| --- | --- |
| Detection facts — symptom, environment, expected vs observed | Status. Progress lives on the forge. |
| Capsules that cannot be made public (tier 2) | Capsules that can (tier 1 — those go in the ticket) |
| Links between records about one symptom | Rulings and their reasoning — those are decision records |

The store is **memory, not a tracker**. Every record names its forge
ticket; work happens there. Two backlogs would mean one stale backlog.

Raw evidence lives in files rather than ticket bodies for two reasons:
a tracker mangles the text (angle brackets vanish, formatting is
rewritten), and a directory of records can be indexed and grepped
offline, which is what makes "have we seen this?" answerable before
touching a rate-limited API.

## Filing

Records are written by `tools/capture.py`, which mints the ID, applies
the field order, validates against this store's own vendored validator,
and refuses to overwrite an existing record:

```bash
python tools/capture.py --draft draft.json
```

The contract every record satisfies is
[docs/conventions.md](docs/conventions.md). The guard in
`.github/guards/` enforces it in CI, and evidence PRs auto-merge on
green — so the guard *is* the review.

## Privacy

This repo is private and stays private: tier-2 capsules exist precisely
because they could not be sanitized. Never write this repo's URL into a
public artifact; consumers reach it through an environment variable, in
the same way the decision store is reached.

A public ticket linked from a tier-2 record carries a leak-free summary
only. Sanitize by **synthesis, not redaction** wherever it is possible
at all — a synthetic fixture is both leak-free and runnable, where a
redacted one is neither.
