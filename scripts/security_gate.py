"""Fail the pipeline on findings in GitLab security reports.

GitLab Free runs the SAST and secret detection analyzers but only shows their findings in a downloadable report;
the merge request widget is an Ultimate feature. This gate reads those reports:
  - any secret detection finding fails the job;
  - a SAST finding fails it at --fail-on severity or above.

    python3 scripts/security_gate.py --fail-on High gl-sast-report.json gl-secret-detection-report.json
"""

import argparse
import json
import sys
from pathlib import Path

ORDER = ["Info", "Unknown", "Low", "Medium", "High", "Critical"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on", choices=ORDER, default="High")
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    floor = ORDER.index(args.fail_on)

    blocking = 0
    for path in args.reports:
        if not path.exists():
            print(f"{path}: not produced (scanner did not run in this pipeline)")
            continue
        report = json.loads(path.read_text())
        scan_type = report.get("scan", {}).get("type", "unknown")
        findings = report.get("vulnerabilities", [])
        print(f"{path}: {scan_type}, {len(findings)} finding(s)")
        for finding in findings:
            severity = finding.get("severity", "Unknown")
            location = finding.get("location", {})
            where = f"{location.get('file', '?')}:{location.get('start_line', '?')}"
            blocks = scan_type == "secret_detection" or ORDER.index(severity) >= floor
            blocking += blocks
            mark = "BLOCK" if blocks else "note "
            print(f"  {mark} {severity:<8} {where}  {finding.get('name') or finding.get('message', '')}")

    if blocking:
        print(f"security gate: FAILED, {blocking} blocking finding(s)")
        return 1
    print("security gate: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
