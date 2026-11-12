# ADR 0003: AWS access through GitLab OIDC, one role per stage

**Status:** accepted, 2026-11-12

**Context.** Long-lived AWS keys in CI variables leak through logs, forks and former team members, and give
every job the same power.

**Decision.** Each job exchanges GitLab's signed OIDC token for a short-lived session of one of three roles.
The trust policy of each role names this project's id, the GitLab-hosted runners and the refs allowed:
any branch for `ci-readonly` (plan), protected `main` for `ci-staging`, protected tags `v*` for `ci-production`.
Roles the pipeline creates must carry a permissions boundary.

**Consequences.** No AWS secret exists in GitLab. A feature branch cannot deploy, `main` cannot touch
production, and the self-hosted SonarQube runner cannot assume any role. The `trust-guard` job proves the first
two on every pipeline.
