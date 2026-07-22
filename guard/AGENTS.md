# Decision-Memory Store — Agent Guidelines

> Copier-vendored from the agentic-engineering-template store
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

Private decision store for one principal (a person or a team):
records, preferences, and the CI guards protecting them. Data-only — no writer tooling lives here
(the recorder lives in the agentic-engineering-template repo; its
`--help` is the authoritative behavior doc, design history in that
repo's issue #37).

## Golden rules

Compressed summary — [docs/conventions.md](docs/conventions.md) is the
authoritative contract.

- `decisions/` is append-only: NEVER modify, delete, or rename an
  existing record. CI rejects it; do not try.
- Inject `preferences.md` ONLY into agent context — never
  `decisions/` wholesale.
- Write records through the recorder (`tools/record.py` in
  template-instantiated repos). Hand-written records are allowed;
  they get no help and face the same guards.
- `preferences.md` may only change via counter-line bumps
  (`pref-confirm`) or human promotion (`pref-promote`). Promotion is
  human-only, always.
- Never write this repo's URL into any public artifact. Consumers
  reference it via the `DECISION_MEMORY_URL` env var only.

## Git

- Never push to `main`; PRs only.
- Session branches: `session/<YYYYMMDDTHHMMSSZ>` (created by the
  recorder's `open`).
- One PR per session; one commit per record.
- Commit types are this repo's own and are CI-linted — see
  [docs/conventions.md](docs/conventions.md) (`decision(...)`,
  `pref-proposal`, `pref-promote`, `pref-confirm`, `chore`).
- In managed environments (e.g. Claude Code on the Web), ALWAYS use
  the tooling the environment itself declares for forge operations
  (PR creation etc.) — `gh`/`curl` are typically sabotaged there. The
  recorder's `submit` hands the PR off to you in that case.

## Pointers

- [docs/conventions.md](docs/conventions.md) — the authoritative
  writing contract: record schema, field conventions, commit types,
  PR flow.
- [docs/extraction-prompt.md](docs/extraction-prompt.md) — paste into
  any chat to extract draft records from a past conversation.
- `.github/guards/`, the docs, and this file are vendored from the
  template repo's store subtemplate; update via `copier update`,
  reviewed here as a normal PR diff. Only `preferences.md` (and the
  records) are owned by this store.
