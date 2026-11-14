"""Local password hashing for the lock screen."""
import hashlib
import hmac
import secrets

ITERATIONS = 240_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password, salt, expected):
    if not salt or not expected:
        return False
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected)
