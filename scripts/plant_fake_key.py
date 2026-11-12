"""Exercise 03: put a fake AWS key pair into the app code, so secret detection has something to catch.

The pair is random and never existed in AWS. It is generated on your machine instead of being committed here,
because a public repository should never hold a key-shaped string.

    python3 scripts/plant_fake_key.py
    git commit -am "Exercise 03: credentials committed in code"
    git push -o merge_request.create -o merge_request.target=main gitlab exercise/03-planted-secret
"""

import pathlib
import secrets
import string

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "app/src/shortlinks/config.py"
ANCHOR = "from dataclasses import dataclass\n\n\n@dataclass"

key_id = "AKIA" + "".join(secrets.choice(string.ascii_uppercase + "234567") for _ in range(16))
key = "".join(secrets.choice(string.ascii_letters + string.digits + "+/") for _ in range(40))
block = (
    '# "Temporary" credentials for a quick test (fake key, never valid).\n'
    f'BACKUP_AWS_ACCESS_KEY_ID = "{key_id}"\n'
    f'BACKUP_AWS_SECRET_ACCESS_KEY = "{key}"  # noqa: S105\n\n\n'
)

text = CONFIG.read_text()
if ANCHOR not in text:
    raise SystemExit(f"{CONFIG} already changed; run this on a clean exercise/03-planted-secret branch")
CONFIG.write_text(text.replace(ANCHOR, "from dataclasses import dataclass\n\n" + block + "@dataclass", 1))
print(f"planted a fake key pair in {CONFIG.relative_to(CONFIG.parents[3])}; commit and push it to your GitLab project")
