"""Short codes: random, URL-safe, hard to guess."""

import random
import re
import string

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
_CODE = re.compile(rf"^[{re.escape(ALPHABET)}]{{{CODE_LENGTH}}}$")


def new_code() -> str:
    return "".join(random.choice(ALPHABET) for _ in range(CODE_LENGTH))  # noqa: S311


def is_valid_code(code: str) -> bool:
    return bool(_CODE.match(code))
