# ADR 0002: Build the image once on main, promote the same digest

**Status:** accepted, 2026-11-12

**Context.** Rebuilding for each environment produces different bytes (base image updates, dependency
resolution), so production would run something staging never tested.

**Decision.** `main` builds, scans and pushes one image tagged with the commit SHA to an ECR repository with
immutable tags. Staging and production deploy that tag; Terraform resolves it to a digest and pins the Lambda
function to the digest. A release tag `vX.Y.Z` only deploys; it never builds.

**Consequences.** A tag on a commit that main never built fails at deploy (the image tag does not exist).
Rollback is a re-deploy of an older commit's deploy job.
