# ADR 0001: SonarQube Community Build gates main, before any deploy

**Status:** accepted, 2026-11-12

**Context.** We self-host SonarQube to keep code and results in-house. The free Community Build analyses one
branch only and cannot comment on merge requests. Branch and merge request analysis need Developer Edition or
SonarQube Cloud.

**Decision.** Run the SonarQube analysis on `main` only and make its quality gate a hard dependency of the
staging deploy. Merge requests get fast checks with the same intent (ruff, mypy, 80 % coverage floor in pytest,
GitLab SAST, secret detection, Trivy).

**Consequences.** A change that fails the gate is already merged but never deployed; the fix is a follow-up
merge request or a revert. Upgrading to Developer Edition moves the gate into the merge request without
changing the pipeline shape.
