from __future__ import annotations

import os
from typing import Any

from .database import get_connection


SETTING_DEFAULTS: dict[str, str] = {
    "default_user_id": "all",
    "default_financial_year": "",
    "local_ai_base_url": os.getenv("LOCAL_AI_BASE_URL", "http://127.0.0.1:1234/v1"),
    "local_ai_model": os.getenv("LOCAL_AI_MODEL", "google/gemma-4-e4b"),
    "local_ai_timeout_seconds": os.getenv("LOCAL_AI_TIMEOUT_SECONDS", "120"),
    "local_ai_rendered_pages": os.getenv("LOCAL_AI_RENDERED_PAGES", "1"),
    "cloud_ai_base_url": os.getenv("CLOUD_AI_BASE_URL", "https://api.openai.com/v1"),
    "cloud_ai_model": os.getenv("CLOUD_AI_MODEL", ""),
}

PUBLIC_SETTING_KEYS = set(SETTING_DEFAULTS)
SECRET_SETTING_KEYS = {"cloud_ai_api_key"}
CONTROL_SETTING_KEYS = {"clear_cloud_ai_api_key"}
UPDATE_SETTING_KEYS = PUBLIC_SETTING_KEYS | SECRET_SETTING_KEYS | CONTROL_SETTING_KEYS


def _clean_value(key: str, value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if key in {"local_ai_timeout_seconds", "local_ai_rendered_pages"}:
        try:
            number = int(text)
        except ValueError as exc:
            raise ValueError(f"{key} must be a positive integer.") from exc
        if number <= 0:
            raise ValueError(f"{key} must be a positive integer.")
        return str(number)
    if key == "default_user_id":
        return text or "all"
    return text


def get_secret_setting(key: str) -> str:
    if key not in SECRET_SETTING_KEYS:
        raise ValueError(f"Unsupported secret setting: {key}")
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def get_settings() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN ({})".format(
                ",".join("?" for _ in PUBLIC_SETTING_KEYS)
            ),
            tuple(PUBLIC_SETTING_KEYS),
        ).fetchall()
    values = dict(SETTING_DEFAULTS)
    values.update({row["key"]: row["value"] for row in rows})
    values["cloud_ai_api_key_set"] = "true" if get_secret_setting("cloud_ai_api_key") else "false"
    return values


def update_settings(payload: dict[str, Any]) -> dict[str, str]:
    unknown = set(payload) - UPDATE_SETTING_KEYS
    if unknown:
        raise ValueError(f"Unsupported setting: {sorted(unknown)[0]}")
    cleaned = {key: _clean_value(key, value) for key, value in payload.items() if key in PUBLIC_SETTING_KEYS}
    secret_updates = {key: str(value).strip() for key, value in payload.items() if key in SECRET_SETTING_KEYS and str(value).strip()}
    clear_cloud_ai_api_key = bool(payload.get("clear_cloud_ai_api_key"))
    with get_connection() as conn:
        for key, value in cleaned.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
        if clear_cloud_ai_api_key:
            conn.execute("DELETE FROM app_settings WHERE key = ?", ("cloud_ai_api_key",))
        for key, value in secret_updates.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )
    return get_settings()
