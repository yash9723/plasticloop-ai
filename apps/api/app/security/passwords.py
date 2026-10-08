"""Argon2id password hashing (argon2-cffi defaults follow RFC 9106)."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import AppError

_ph = PasswordHasher()  # argon2id

# Verified against when the account does not exist, so response time doesn't reveal which emails are registered.
DUMMY_HASH = _ph.hash("plasticloop-timing-equaliser")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def validate_password_strength(password: str, email: str | None = None) -> None:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        problems.append("both letters and numbers")
    if email and password.lower() == email.lower():
        problems.append("must differ from the email address")
    if problems:
        raise AppError(422, "WEAK_PASSWORD", "Password needs " + ", ".join(problems), {"rules": problems})
