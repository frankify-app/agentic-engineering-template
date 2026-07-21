# Decision-Memory Store

> Copier-vendored from the agentic-engineering-template store
> subtemplate — do NOT edit in the store repo; change it in the
> template and pull via `copier update`.

Private decision store: memory of decisions and preference signals
written by agentic grilling sessions across projects, scoped to one
principal — a person or a team (one store per principal, so personal
and team preferences never mix). **Knowledge base, not code:** the only executable content is the CI guard
protecting the data's integrity.

## Layout

```text
«store-repo»/
├── README.md               # this overview, human-facing
├── CLAUDE.md               # thin Claude Code shim → AGENTS.md
├── AGENTS.md               # agent entry point: golden rules, git rules
├── docs/
│   ├── conventions.md      # authoritative writing conventions — the
│   │                       # contract any writer must satisfy
│   └── extraction-prompt.md  # copy-paste prompt: extract draft
│                           # records from past conversations
├── preferences.md          # active preference set — the ONLY file
│                           # injected into agent context
├── proposals/              # agent-proposed preference rules awaiting
│                           # human promotion (merge != promotion)
├── decisions/              # full history, append-only, flat —
│                           # one immutable JSON file per decision
└── .github/
    ├── workflows/guards.yml  # CI guards
    └── guards/             # copier-vendored guard scripts
```

(`proposals/` and `decisions/` materialize with their first files.)

## How it works

(Summary — the authoritative contract is
[docs/conventions.md](docs/conventions.md).)

- **Records:** one immutable JSON file per decision in `decisions/`,
  append-only. Integrity is CI-enforced rather than permission-based:
  guards reject any PR that modifies, deletes, or renames existing
  records.
- **Preferences:** `preferences.md` is the active preference set — the
  only file injected into agent sessions, kept under a hard ~2k-token
  budget. Confirmation counters on each rule are the one sanctioned
  edit.
- **Proposals:** agents write candidate rules to `proposals/` (one
  rule per file); only a human `pref-promote` commit moves content
  into `preferences.md`.
- **Write flow:** one PR per session, one commit per record. Merging a
  PR accepts the records. Closing a PR without merging is itself
  signal: the next session records why (`closure_of`).
- **Consumers** reference this repo only through the
  `DECISION_MEMORY_URL` environment variable (full git URL, never
  committed anywhere public) and inject `preferences.md` only — never
  `decisions/` wholesale.

## Writing to this repo

The contract lives in [docs/conventions.md](docs/conventions.md). The
writer tool (`record.py`) lives with its consumers in the
agentic-engineering-template repo; its `--help` (the module
docstring) is the authoritative behavior doc, and design history
lives in that repo's issue #37. This repo stays ignorant of which
tools write to it. Hand-written records are allowed — they get no
help and face the same guards.

To extract decisions from a past conversation (no repo access needed
there), use
[docs/extraction-prompt.md](docs/extraction-prompt.md).

## Guards

`.github/guards/` — like this file and everything under `docs/` — is
copier-vendored from the template repo's store subtemplate; the guard
uses the same validator the writer tool imports, so writer and CI
validation cannot drift. Update via `copier update` (the diff is
reviewed here like any PR — the human gate on guard changes).
Every guard update re-validates the entire existing corpus. The
vendored copy keeps this repo self-contained: if the template repo
disappears, the guard keeps working; only updates stop.
