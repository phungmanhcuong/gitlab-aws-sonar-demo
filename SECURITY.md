# Security

This is a teaching repository. The `exercise/*` branches contain defects on purpose (untested code, a weak random
generator, a dependency with known CVEs, a broken release); they are not vulnerabilities to report.

To report a real problem in `main` (for example a pipeline or IAM policy that grants more than the guide says),
use GitHub's private vulnerability reporting: **Security > Report a vulnerability**. Please do not open a public
issue for it.

Never commit real credentials, account IDs or endpoints to a fork of this repository; the pipeline reads them from
GitLab CI/CD variables.
