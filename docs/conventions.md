# Agentic Engineering Template — Project Conventions

Repo-specific rules referenced from [AGENTS.md](../AGENTS.md). This file is
seeded once by the agentic template and never overwritten by `copier update` —
edit it freely.

## Template-First Changes (Self-Application)

This repo is the template AND uses itself as a template: root artifacts that
have a counterpart under `template/` (`AGENTS.md`, `skills-lock.json`,
`scripts/doctor.sh`, `scripts/agent-shims/`, …) are template *output*, never
hand-edited. Editing both places duplicates work; editing only the root drifts
from the template.

For any change touching a templated file, always follow this route:

1. Edit only the source under `template/` (plus `copier.yml`, `extensions/`,
   tests).
2. Commit the template-only change(s).
3. Self-apply: render the template from the current branch and adopt the
   rendered output for the affected root files verbatim:

   ```bash
   uv run copier copy --trust --defaults --skip-tasks --vcs-ref HEAD \
     --data agentic_project_name="Agentic Engineering Template" \
     --data agentic_project_description="Copier template for agentic engineering scaffolding" \
     --data agentic_project_slug=agentic-engineering-template \
     --data agentic_repo_owner=frankify-app \
     . <tmp-render-dir>
   ```

4. Copy the affected files from the render into the repo root and commit them
   as a separate `chore: reapply template to self` commit.

This doubles as a proving ground: the self-applied root files are the rendered
template output, reviewed in the same PR as the template change.

Exception: root files that intentionally diverge from the template for
template-development needs (currently `.pre-commit-config.yaml`, which carries
jinja lint hooks) are NOT overwritten by self-application — keep maintaining
them by hand and list them here when adding new ones.
