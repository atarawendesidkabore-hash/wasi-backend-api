"""
Quarter / Trimestre period utilities for the WASI platform.

Accepts both international (Q1-Q4) and French trimestre (T1-T4) notation.
Q1=T1 (Jan-Mar), Q2=T2 (Apr-Jun), Q3=T3 (Jul-Sep), Q4=T4 (Oct-Dec).

Usage:
    from src.utils.periods import parse_quarter, quarter_label

    start, end = parse_quarter("Q1-2026")   # (date(2026,1,1), date(2026,3,31))
    start, end = parse_quarter("T3 2025")   # (date(2025,7,1), date(2025,9,30))
    label = quarter_label(date(2026, 5, 15)) # "Q2-2026"
"""
import calendar
import re
from datetime import date

from fastapi import HTTPException

# Quarter boundaries: quarter_number -> (start_month, end_month)
_QUARTER_MONTHS = {
    1: (1, 3),
    2: (4, 6),
    3: (7, 9),
    4: (10, 12),
}

# Regex: accepts Q1-2026, T3-2025, 2026-Q2, Q1 2026, T2 2025, q1-2026, etc.
_QUARTER_RE = re.compile(
    r"^(?:([QqTt])(\d)\s*[-/]?\s*(\d{4})|(\d{4})\s*[-/]?\s*([QqTt])(\d))$"
)


def parse_quarter(q: str) -> tuple[date, date]:
    """Parse a quarter string into (start_date, end_date) inclusive.

    Accepted formats:
        Q1-2026, T3-2025, 2026-Q2, 2026-T1, Q1 2026, T2 2025,
        q1-2026, t4-2025, Q1/2026, 2026/T3

    Returns:
        Tuple of (first day of quarter, last day of quarter).

    Raises:
        HTTPException 400 on invalid input.
    """
    q = q.strip()
    m = _QUARTER_RE.match(q)
    if not m:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid quarter format: '{q}'. "
                "Use Q1-2026, T3-2025, 2026-Q2, etc. "
                "(Q=quarter, T=trimestre; 1-4)."
            ),
        )

    if m.group(1):
        # Format: Q1-2026 or T3 2025
        qnum = int(m.group(2))
        year = int(m.group(3))
    else:
        # Format: 2026-Q2 or 2026-T1
        year = int(m.group(4))
        qnum = int(m.group(6))

    if qnum < 1 or qnum > 4:
        raise HTTPException(
            status_code=400,
            detail=f"Quarter number must be 1-4, got {qnum}.",
        )

    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=400,
            detail=f"Year must be between 2000 and 2100, got {year}.",
        )

    start_month, end_month = _QUARTER_MONTHS[qnum]
    last_day = calendar.monthrange(year, end_month)[1]

    return date(year, start_month, 1), date(year, end_month, last_day)


def quarter_label(d: date) -> str:
    """Return the quarter label for a date, e.g. 'Q1-2026'."""
    q = (d.month - 1) // 3 + 1
    return f"Q{q}-{d.year}"


def quarter_number(d: date) -> int:
    """Return the quarter number (1-4) for a date."""
    return (d.month - 1) // 3 + 1
