# Shared glossary terms ship with the scaffold

Vocabulary referenced by more than one repo needs one canonical definition.
It lives in `template/docs/glossary/` and reaches consumers through the
ordinary scaffold render, so a definition change rides the same review path
as any other template change.

## Considered Options

- **Per-repo hand-sync** — every repo keeps its own copy, aligned by hand.
  Rejected: silent drift, and no signal that copies exist.
- **URL links to one canonical repo** — consumers link out instead of holding
  a copy. Rejected: `disambiguate` resolves a per-repo term graph, so an
  external URL is not a cross-reference — the term is unreachable locally and
  the graph breaks.
- **A separate `glossary` subtemplate applied alongside the scaffold** —
  implemented first, then withdrawn. It bought one thing: a non-scaffold repo
  (e.g. a `decision-memory`-stamped store) could consume the terms from a
  single copy. It cost a second answers file and a second `copier update` per
  consumer forever, a normal update that silently did *not* carry glossary
  changes, a source directory that was not lintable, a name colliding with
  `disambiguate`'s auto-discovery, and an update path that could not be
  verified. The future rework it avoided is a second copy *inside this repo*,
  guarded by a test — an hour of work, in one repo, on the day a non-scaffold
  consumer actually appears.
- **Ship with the scaffold (chosen)** — one delivery path, one copy, no extra
  update to remember.

## Consequences

- Shared terms must be **repo-neutral, link-closed within the set, and
  acyclic**: a link to a repo-owned term would dangle in every other consumer,
  and `disambiguate --lint` fails on both dangling refs and cycles. Promotion
  therefore forces rewording — `template` dropped its link to the meta-owned
  `factory`.
- Nothing under `template/` is ever a glossary root, because `disambiguate`
  walks up and finds the repo-root `docs/glossary/` first. The canonical files
  are therefore structurally unprunable, while every stamped copy carries
  `<!-- d10e: auto-prune -->` and can be removed by a repo that never links it.
- Copier copies plain `.md` verbatim, so the marker must be present in the
  source file — there is no render-time injection.
- The terms are only lintable *as terms* after being stamped into this repo's
  own `docs/glossary/`. A stale stamp means the glossary being linted is not
  the glossary being shipped, so self-application is enforced by a test rather
  than left to convention.
- Only repos rendering the `template` subtemplate receive the terms. A
  `decision-memory`-stamped store would need a
  `decision-memory/docs/glossary/` copy and an
  equality guard, added if and when that consumer exists.
