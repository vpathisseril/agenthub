"""Password hashing, secret encryption and CSRF helpers."""

from __future__ import annotations

import hmac
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    """Minimal ASVS L1-style password policy."""
    problems = []
    if len(password) < 12:
        problems.append("Use at least 12 characters.")
    if password.lower() == password or password.upper() == password:
        problems.append("Mix upper- and lower-case letters.")
    if not any(c.isdigit() for c in password):
        problems.append("Include at least one number.")
    return problems


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        if get_settings().is_production:
            raise RuntimeError("FERNET_KEY must be set in production")
        key = Fernet.generate_key().decode()
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)
