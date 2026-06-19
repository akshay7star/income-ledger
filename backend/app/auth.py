from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from .database import get_connection


PIN_HASH_KEY = "app_pin_hash"
PBKDF2_ITERATIONS = 260_000
SESSION_TTL_HOURS = 12

_sessions: dict[str, datetime] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_pin(pin: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def _verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _get_setting(key: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def is_pin_configured() -> bool:
    return bool(_get_setting(PIN_HASH_KEY))


def setup_pin(pin: str) -> None:
    if is_pin_configured():
        raise ValueError("App PIN is already configured.")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (PIN_HASH_KEY, _hash_pin(pin)),
        )


def change_pin(current_pin: str, new_pin: str) -> None:
    stored_hash = _get_setting(PIN_HASH_KEY)
    if not stored_hash or not _verify_pin(current_pin, stored_hash):
        raise ValueError("Current App PIN is incorrect.")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE app_settings
            SET value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE key = ?
            """,
            (_hash_pin(new_pin), PIN_HASH_KEY),
        )
    _sessions.clear()


def login(pin: str) -> str:
    stored_hash = _get_setting(PIN_HASH_KEY)
    if not stored_hash or not _verify_pin(pin, stored_hash):
        raise ValueError("Invalid app PIN.")
    token = secrets.token_urlsafe(32)
    _sessions[token] = _now() + timedelta(hours=SESSION_TTL_HOURS)
    return token


def verify_app_pin(pin: str) -> bool:
    stored_hash = _get_setting(PIN_HASH_KEY)
    return bool(stored_hash and _verify_pin(pin, stored_hash))


def logout(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def is_token_valid(token: str | None) -> bool:
    if not token:
        return False
    expires_at = _sessions.get(token)
    if not expires_at:
        return False
    if expires_at <= _now():
        _sessions.pop(token, None)
        return False
    return True
