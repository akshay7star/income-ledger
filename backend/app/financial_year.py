from __future__ import annotations

from datetime import date, datetime


def parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%Y", "%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.date().replace(day=1) if fmt in ("%m/%Y", "%b %Y", "%B %Y") else parsed.date()
        except ValueError:
            continue
    return date.today()


def financial_year_for(value: date | str | None) -> str:
    target = parse_date(value) if isinstance(value, str) or value is None else value
    start_year = target.year if target.month >= 4 else target.year - 1
    return f"FY {start_year}-{str(start_year + 1)[-2:]}"


def month_label(value: date | str | None) -> str:
    target = parse_date(value) if isinstance(value, str) or value is None else value
    return target.strftime("%b %Y")
