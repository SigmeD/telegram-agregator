<!--
Thanks for the PR. Please fill the checklist below — the CI will enforce most
of it. Rule of thumb: if a box truly does not apply, strike it through with
~~text~~ and leave a one-line reason.
-->

## Summary

<!-- 1-3 sentences: what and why. -->

## Linked item

Closes FEATURE-XX / BUG-YY / TASK-ZZ

## Type of change

- [ ] feat (new user-facing capability)
- [ ] fix (bug fix)
- [ ] refactor (no behaviour change)
- [ ] chore / infra / deps
- [ ] docs only
- [ ] architecture (ADR required)

## Checklist

- [ ] Tests added or updated (unit / integration / e2e as relevant)
- [ ] `pnpm lint && pnpm typecheck` (frontend) / `uv run ruff check && uv run mypy src` (backend) pass locally
- [ ] `CHANGELOG.md` updated (required for PRs into `main`)
- [ ] Docs updated (`README`, `docs/`, or inline) where behaviour changed
- [ ] ADR added under `docs/adr/` if this PR is labelled `architecture`
- [ ] No secrets in code, configs, fixtures, or logs
- [ ] Migration file committed and runnable against a fresh DB
- [ ] Backwards-compatible migration (or downtime deploy explicitly agreed)
- [ ] Telemetry / metrics updated where a new critical path was introduced

## Definition of Done

- [ ] Acceptance criteria in the linked task are fully satisfied
- [ ] Manually verified on dev (screenshot / log excerpt attached if visible change)
- [ ] Rollback plan documented in PR description if this change is risky

## Notes for reviewers

<!-- Anything the diff does not show: assumptions, follow-ups, trade-offs. -->
