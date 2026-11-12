"""Short codes: random, URL-safe, hard to guess."""

import re
import secrets
import string

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
_CODE = re.compile(rf"^[{re.escape(ALPHABET)}]{{{CODE_LENGTH}}}$")


def new_code() -> str:
    # secrets, not random: codes must not be predictable from earlier ones.
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def is_valid_code(code: str) -> bool:
    return bool(_CODE.match(code))
