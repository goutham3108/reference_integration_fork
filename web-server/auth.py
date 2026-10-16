"""Password hashing helpers for deployment-manager users."""

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 310_000


def make_password_record(email: str, password: str) -> dict[str, str | int]:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "email": email.strip().casefold(),
        "salt": salt.hex(),
        "password_hash": password_hash.hex(),
        "iterations": PBKDF2_ITERATIONS,
    }


def verify_password(password: str, record: dict) -> bool:
    try:
        salt = bytes.fromhex(record["salt"])
        expected = bytes.fromhex(record["password_hash"])
        iterations = int(record["iterations"])
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate, expected)
    except (KeyError, TypeError, ValueError):
        return False
