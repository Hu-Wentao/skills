# Local Maintenance

Use `maintenance-audit --target <branch> --all` to obtain one stable snapshot and plan template. Inspect each `review_required` candidate’s commits, diff, target code, requirements, checks, replacements, and review history.

Choose narrowly:

- `merge`: behavior remains valuable and compatible.
- `retain`: work is active, incomplete, protected, unresolved, or unsafe.
- `delete`: behavior is contained, patch-equivalent, demonstrably superseded, or has no remaining value.

Every semantic decision needs a non-empty evidence reason. `maintenance-run` rejects stale snapshots and omitted decisions.

Rescue clean uncontained detached heads with `rescue-detached` and an exact expected head, then re-audit. Retain dirty detached work unless separately authorized. Prune only the exact audited set of missing unlocked registrations with `prune-missing --expect <path>=<head>`.

Do not treat release, repair, or hotfix branch retention as proof that a published fix is integrated. Resolve release governance separately and retain unresolved protected lineages.

Explicit recovery commands include `branch-audit`, exact local `merge`, guarded `remove`, and evidence-classified `branch-delete`. Protected branch deletion needs separate exact authority.
