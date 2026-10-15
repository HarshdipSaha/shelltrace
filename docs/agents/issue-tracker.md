# Issue tracker: GitHub

Project issues and specs live in this repository's GitHub Issues. Use the `gh` CLI for issue operations.

## Conventions

- Create and read issues with `gh issue create` and `gh issue view <number> --comments`.
- Publish specs and implementation tickets as GitHub issues.
- Apply the configured triage labels from `docs/agents/triage-labels.md` when triaging.
- Link implementation pull requests to their issue with `Fixes #<number>` when the PR completes that issue.

## Pull requests as a triage surface

No. External pull requests are not treated as incoming feature requests by triage. Normal implementation pull requests remain part of the development workflow.
