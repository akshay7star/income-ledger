from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .database import get_connection, row_to_dict
from .financial_year import financial_year_for, parse_date_strict
from .settings import get_secret_setting, get_settings


SYNC_SOURCE = "google_sheet"
DEFAULT_TIMEOUT_SECONDS = 20
_sync_lock = threading.Lock()


class MobileSyncError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured_connection() -> tuple[str, str]:
    settings = get_settings()
    if settings.get("google_sheet_sync_enabled") != "true":
        raise MobileSyncError("Google Sheet mobile sync is disabled.")
    url = settings.get("google_apps_script_url", "").strip()
    secret = get_secret_setting("google_sheet_sync_secret").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"script.google.com", "script.googleusercontent.com"}:
        raise MobileSyncError("Enter a valid deployed Google Apps Script web app URL.")
    if not secret:
        raise MobileSyncError("Enter the Google Apps Script sync key.")
    return url, secret


def _call_apps_script(url: str, secret: str, action: str, payload: dict[str, Any] | None = None) -> dict:
    body = json.dumps({"action": action, "secret": secret, **(payload or {})}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": "Income-Ledger/0.4"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MobileSyncError(f"Could not reach the Google Sheet mobile app: {exc}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MobileSyncError("Google Apps Script returned an invalid response.") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        message = result.get("error") if isinstance(result, dict) else None
        raise MobileSyncError(message or "Google Apps Script rejected the sync request.")
    return result


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry.get("entry_id") or "").strip()
    if not entry_id or len(entry_id) > 128:
        raise ValueError("entry_id is missing or invalid")
    try:
        user_id = int(entry.get("user_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id is invalid") from exc
    expense_date = parse_date_strict(entry.get("expense_date"))
    category = str(entry.get("category") or "").strip()
    if not category:
        raise ValueError("category is required")
    try:
        amount = round(float(entry.get("amount")), 2)
        gst_amount = round(float(entry.get("gst_amount") or 0), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("amount or GST amount is invalid") from exc
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    if gst_amount < 0 or gst_amount > amount:
        raise ValueError("GST amount must be between zero and the total amount")
    return {
        "entry_id": entry_id,
        "user_id": user_id,
        "expense_date": expense_date.isoformat(),
        "financial_year": financial_year_for(expense_date),
        "category": category[:200],
        "amount": amount,
        "gst_amount": gst_amount,
        "payment_method": str(entry.get("payment_method") or "").strip()[:100],
        "notes": str(entry.get("notes") or "").strip()[:2000],
    }


def import_mobile_expense(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_entry(entry)
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT entry_id, expense_id, synced_at FROM mobile_expense_sync WHERE entry_id = ?",
            (normalized["entry_id"],),
        ).fetchone()
        if existing:
            return {"entry_id": normalized["entry_id"], "expense_id": existing["expense_id"], "duplicate": True}

        user = conn.execute("SELECT id FROM users WHERE id = ?", (normalized["user_id"],)).fetchone()
        if not user:
            raise ValueError(f"user_id {normalized['user_id']} does not exist in Income Ledger")

        cursor = conn.execute(
            """
            INSERT INTO freelance_expenses
                (user_id, financial_year, expense_date, category, amount, gst_amount, payment_method, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["user_id"],
                normalized["financial_year"],
                normalized["expense_date"],
                normalized["category"],
                normalized["amount"],
                normalized["gst_amount"],
                normalized["payment_method"],
                normalized["notes"],
            ),
        )
        expense_id = int(cursor.lastrowid)
        raw_payload_json = json.dumps(entry, default=str, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO mobile_expense_sync (entry_id, source, expense_id, raw_payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (normalized["entry_id"], SYNC_SOURCE, expense_id, raw_payload_json),
        )
        conn.execute(
            """
            INSERT INTO audit_events (document_id, user_id, event_type, before_json, after_json)
            VALUES (NULL, ?, 'sync_mobile_expense', '{}', ?)
            """,
            (
                normalized["user_id"],
                json.dumps({**normalized, "expense_id": expense_id, "source": SYNC_SOURCE}, ensure_ascii=False),
            ),
        )
        row = conn.execute("SELECT * FROM freelance_expenses WHERE id = ?", (expense_id,)).fetchone()
    return {"entry_id": normalized["entry_id"], "expense_id": expense_id, "duplicate": False, "expense": row_to_dict(row)}


def _record_run(summary: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO mobile_sync_runs
                (started_at, completed_at, status, received_count, imported_count, duplicate_count, error_count, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["started_at"],
                summary["completed_at"],
                summary["status"],
                int(summary.get("received_count", 0)),
                int(summary.get("imported_count", 0)),
                int(summary.get("duplicate_count", 0)),
                int(summary.get("error_count", 0)),
                str(summary.get("message", ""))[:2000],
            ),
        )


def get_mobile_sync_status() -> dict[str, Any]:
    settings = get_settings()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM mobile_sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        tracked = conn.execute("SELECT COUNT(*) AS count FROM mobile_expense_sync").fetchone()["count"]
    return {
        "enabled": settings.get("google_sheet_sync_enabled") == "true",
        "configured": bool(settings.get("google_apps_script_url") and settings.get("google_sheet_sync_secret_set") == "true"),
        "mobile_app_url": settings.get("google_apps_script_url", ""),
        "tracked_entries": tracked,
        "last_run": row_to_dict(row),
    }


def sync_google_sheet_expenses() -> dict[str, Any]:
    started_at = _utc_now()
    summary: dict[str, Any] = {
        "started_at": started_at,
        "completed_at": started_at,
        "status": "running",
        "received_count": 0,
        "imported_count": 0,
        "duplicate_count": 0,
        "error_count": 0,
        "message": "",
    }
    if not _sync_lock.acquire(blocking=False):
        raise MobileSyncError("A mobile expense sync is already running.")
    try:
        url, secret = _configured_connection()
        with get_connection() as conn:
            users = [dict(row) for row in conn.execute("SELECT id, name FROM users ORDER BY name, id").fetchall()]
        _call_apps_script(url, secret, "sync_users", {"users": users})
        response = _call_apps_script(url, secret, "list_pending")
        entries = response.get("entries") or []
        if not isinstance(entries, list):
            raise MobileSyncError("Google Apps Script returned an invalid pending-entry list.")
        summary["received_count"] = len(entries)
        results = []
        for raw_entry in entries:
            entry_id = str(raw_entry.get("entry_id") or "").strip() if isinstance(raw_entry, dict) else ""
            try:
                imported = import_mobile_expense(raw_entry)
                if imported["duplicate"]:
                    summary["duplicate_count"] += 1
                else:
                    summary["imported_count"] += 1
                results.append({
                    "entry_id": imported["entry_id"],
                    "status": "SYNCED",
                    "sql_expense_id": imported["expense_id"] or "",
                    "sync_error": "",
                })
            except Exception as exc:
                summary["error_count"] += 1
                results.append({
                    "entry_id": entry_id,
                    "status": "ERROR",
                    "sql_expense_id": "",
                    "sync_error": str(exc)[:500],
                })
        if results:
            _call_apps_script(url, secret, "mark_results", {"results": results})
        summary["status"] = "partial" if summary["error_count"] else "success"
        summary["message"] = (
            f"Imported {summary['imported_count']} expense(s); "
            f"{summary['duplicate_count']} already imported; {summary['error_count']} error(s)."
        )
    except MobileSyncError as exc:
        summary["status"] = "failed"
        summary["error_count"] = max(1, summary["error_count"])
        summary["message"] = str(exc)
    except Exception as exc:
        summary["status"] = "failed"
        summary["error_count"] = max(1, summary["error_count"])
        summary["message"] = f"Unexpected mobile sync error: {exc}"
    finally:
        summary["completed_at"] = _utc_now()
        _record_run(summary)
        _sync_lock.release()
    return summary
