"""Smoke test against a deployed environment: must-pass and must-fail requests.

    python3 scripts/smoke.py https://abc123.execute-api.ap-southeast-1.amazonaws.com --version <commit sha>
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


opener = urllib.request.build_opener(NoRedirect)


def call(method: str, url: str, body: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read().decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--version", required=True, help="commit SHA the environment must report")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    failures = 0

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal failures
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")

    started = time.monotonic()
    status, _, text = call("GET", f"{base}/health")
    elapsed = time.monotonic() - started
    version = json.loads(text).get("version") if status == 200 else None
    check("health", status == 200 and version == args.version, f"{status} version={version} ({elapsed:.2f}s)")

    status, _, text = call("POST", f"{base}/links", {"url": "https://docs.gitlab.com/ci/"})
    code = json.loads(text).get("code", "") if status == 201 else ""
    check("create link", status == 201 and len(code) == 7, f"{status} code={code}")

    status, headers, _ = call("GET", f"{base}/{code}")
    location = headers.get("location") or headers.get("Location")
    check("redirect", status == 307 and location == "https://docs.gitlab.com/ci/", f"{status} -> {location}")

    status, _, text = call("GET", f"{base}/links/{code}")
    hits = json.loads(text).get("hits") if status == 200 else None
    check("stats count the visit", status == 200 and hits == 1, f"{status} hits={hits}")

    # Must-fail requests: the API refuses them.
    status, _, _ = call("GET", f"{base}/ZZZZZZZ")
    check("unknown code is 404", status == 404, str(status))
    status, _, _ = call("POST", f"{base}/links", {"url": "javascript:alert(1)"})
    check("non-http URL is 422", status == 422, str(status))

    print(f"smoke: {'FAILED' if failures else 'passed'} ({failures} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
