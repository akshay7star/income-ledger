from __future__ import annotations

import json
import re
from typing import Any

from .database import get_connection
from .tax import TAX_RULE_OVERRIDES_KEY, tax_slabs_catalog
from .tax_planning import _call_cloud_chat


REGIME_KEYS = {"old", "new"}
FY_RE = re.compile(r"^FY\s+\d{4}-\d{2}$")


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Cloud AI did not return valid JSON.")
        return json.loads(stripped[start : end + 1])


def _clean_slab(slab: dict[str, Any]) -> dict:
    amount = slab.get("amount")
    if amount in ("", "null"):
        amount = None
    if amount is not None:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Each tax slab amount must be positive, except the final unlimited slab.")
    rate = float(slab.get("rate") or 0)
    if rate < 0 or rate > 1:
        raise ValueError("Each tax slab rate must be between 0 and 1.")
    return {"amount": amount, "rate": rate}


def _clean_regime(financial_year: str, regime: str, payload: dict[str, Any]) -> dict:
    slabs = [_clean_slab(item) for item in payload.get("slabs") or []]
    if not slabs:
        raise ValueError(f"{financial_year} {regime} must include at least one slab.")
    if slabs[-1]["amount"] is not None:
        raise ValueError(f"{financial_year} {regime} slabs must end with an unlimited slab using amount null.")
    cess_rate = float(payload.get("cess_rate") or 0)
    if cess_rate < 0 or cess_rate > 1:
        raise ValueError("cess_rate must be between 0 and 1.")
    return {
        "assessment_year": str(payload.get("assessment_year") or ""),
        "slabs": slabs,
        "cess_rate": cess_rate,
        "rebate_threshold": max(0.0, float(payload.get("rebate_threshold") or 0)),
        "rebate_max": max(0.0, float(payload.get("rebate_max") or 0)),
        "salary_standard_deduction": max(0.0, float(payload.get("salary_standard_deduction") or 0)),
        "is_default": bool(payload.get("is_default")),
        "source_note": str(payload.get("source_note") or "User-confirmed tax rule override."),
        "marginal_relief": bool(payload.get("marginal_relief")),
    }


def validate_tax_rule_draft(payload: dict[str, Any]) -> dict:
    financial_year = str(payload.get("financial_year") or "").strip()
    if not FY_RE.match(financial_year):
        raise ValueError("financial_year must look like 'FY 2027-28'.")
    regimes_payload = payload.get("regimes")
    if not isinstance(regimes_payload, dict):
        raise ValueError("Tax rule draft must include a regimes object.")
    regimes = {}
    for regime, regime_payload in regimes_payload.items():
        regime_key = str(regime).strip().lower()
        if regime_key in REGIME_KEYS:
            regimes[regime_key] = _clean_regime(financial_year, regime_key, regime_payload)
    if not regimes:
        raise ValueError("Tax rule draft must include at least one old/new regime.")
    default_regimes = [regime for regime, item in regimes.items() if item["is_default"]]
    if len(default_regimes) != 1:
        default_regime = "new" if "new" in regimes else next(iter(regimes))
        for item in regimes.values():
            item["is_default"] = False
        regimes[default_regime]["is_default"] = True
    return {
        "financial_year": financial_year,
        "regimes": regimes,
        "source_summary": str(payload.get("source_summary") or ""),
        "confidence": str(payload.get("confidence") or "review_required"),
        "warnings": [str(item) for item in payload.get("warnings") or []],
    }


def tax_rule_ai_prompt(financial_year: str) -> list[dict]:
    financial_year = financial_year.strip()
    current_catalog = tax_slabs_catalog()
    return [
        {
            "role": "system",
            "content": (
                "You update Indian individual income-tax slab data for a local finance app. "
                "Return only strict JSON. Do not include markdown. If you are unsure, set confidence to low and add warnings. "
                "Do not update anything outside tax slabs, cess, rebate, standard deduction, default regime, marginal relief, "
                "assessment/tax year label, and source notes."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Check whether Indian individual income-tax rules need an update for {financial_year}. "
                "Use this exact JSON schema:\n"
                "{\n"
                '  "financial_year": "FY YYYY-YY",\n'
                '  "source_summary": "short source/reform summary",\n'
                '  "confidence": "high|medium|low",\n'
                '  "warnings": ["review notes"],\n'
                '  "regimes": {\n'
                '    "new": {\n'
                '      "assessment_year": "AY YYYY-YY or Tax Year YYYY-YY",\n'
                '      "slabs": [{"amount": 400000, "rate": 0.0}, {"amount": null, "rate": 0.3}],\n'
                '      "cess_rate": 0.04,\n'
                '      "rebate_threshold": 1200000,\n'
                '      "rebate_max": 60000,\n'
                '      "salary_standard_deduction": 75000,\n'
                '      "is_default": true,\n'
                '      "marginal_relief": true,\n'
                '      "source_note": "Budget/Finance Act note"\n'
                "    }\n"
                "  }\n"
                "}\n\n"
                "Rules:\n"
                "- slab amount is the width of that slab, not the upper bound; final unlimited slab must use amount null.\n"
                "- rates must be decimals like 0.05 for 5%.\n"
                "- include old and new regimes only if applicable.\n"
                "- preserve old regime if no reform changed it.\n"
                "- this is a draft for human PIN-confirmed review.\n\n"
                f"Current app catalog:\n{json.dumps(current_catalog, indent=2)}"
            ),
        },
    ]


def draft_tax_rule_update(financial_year: str) -> dict:
    response = _call_cloud_chat(tax_rule_ai_prompt(financial_year))
    draft = validate_tax_rule_draft(_extract_json_object(response["message"]))
    return {"draft": draft, "usage": response.get("usage") or {}, "raw_model": response.get("raw_model")}


def apply_tax_rule_update(draft: dict[str, Any]) -> dict:
    cleaned = validate_tax_rule_draft(draft)
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (TAX_RULE_OVERRIDES_KEY,)).fetchone()
        overrides = json.loads(row["value"] or "{}") if row else {}
        overrides[cleaned["financial_year"]] = cleaned["regimes"]
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (TAX_RULE_OVERRIDES_KEY, json.dumps(overrides)),
        )
    return {"ok": True, "financial_year": cleaned["financial_year"], "regimes": sorted(cleaned["regimes"])}
