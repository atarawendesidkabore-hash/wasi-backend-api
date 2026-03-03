"""Tests for the quarter/trimestre period utilities."""
import pytest
from datetime import date
from fastapi import HTTPException

from src.utils.periods import parse_quarter, quarter_label, quarter_number


# ── parse_quarter ────────────────────────────────────────────────────


class TestParseQuarter:
    """Test parse_quarter with various valid and invalid formats."""

    # Q notation
    def test_q1_dash_year(self):
        start, end = parse_quarter("Q1-2026")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_q2_dash_year(self):
        start, end = parse_quarter("Q2-2026")
        assert start == date(2026, 4, 1)
        assert end == date(2026, 6, 30)

    def test_q3_dash_year(self):
        start, end = parse_quarter("Q3-2025")
        assert start == date(2025, 7, 1)
        assert end == date(2025, 9, 30)

    def test_q4_dash_year(self):
        start, end = parse_quarter("Q4-2025")
        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)

    # T (trimestre) notation
    def test_t1_dash_year(self):
        start, end = parse_quarter("T1-2026")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_t2_dash_year(self):
        start, end = parse_quarter("T2-2025")
        assert start == date(2025, 4, 1)
        assert end == date(2025, 6, 30)

    def test_t3_dash_year(self):
        start, end = parse_quarter("T3-2026")
        assert start == date(2026, 7, 1)
        assert end == date(2026, 9, 30)

    def test_t4_dash_year(self):
        start, end = parse_quarter("T4-2025")
        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)

    # Year-first notation
    def test_year_dash_q(self):
        start, end = parse_quarter("2026-Q1")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_year_dash_t(self):
        start, end = parse_quarter("2025-T3")
        assert start == date(2025, 7, 1)
        assert end == date(2025, 9, 30)

    # Space separator
    def test_q_space_year(self):
        start, end = parse_quarter("Q1 2026")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 3, 31)

    def test_t_space_year(self):
        start, end = parse_quarter("T2 2025")
        assert start == date(2025, 4, 1)
        assert end == date(2025, 6, 30)

    # Slash separator
    def test_q_slash_year(self):
        start, end = parse_quarter("Q3/2026")
        assert start == date(2026, 7, 1)
        assert end == date(2026, 9, 30)

    def test_year_slash_t(self):
        start, end = parse_quarter("2025/T4")
        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)

    # Case insensitive
    def test_lowercase_q(self):
        start, end = parse_quarter("q2-2026")
        assert start == date(2026, 4, 1)

    def test_lowercase_t(self):
        start, end = parse_quarter("t1-2026")
        assert start == date(2026, 1, 1)

    # Leap year — Q1 end (Feb 29)
    def test_leap_year_q1(self):
        start, end = parse_quarter("Q1-2024")
        assert end == date(2024, 3, 31)

    # Q/T equivalence
    def test_q_equals_t(self):
        q_start, q_end = parse_quarter("Q2-2026")
        t_start, t_end = parse_quarter("T2-2026")
        assert q_start == t_start
        assert q_end == t_end

    # Invalid inputs
    def test_invalid_format(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_quarter("January 2026")
        assert exc_info.value.status_code == 400

    def test_invalid_quarter_number(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_quarter("Q5-2026")
        assert exc_info.value.status_code == 400

    def test_invalid_quarter_zero(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_quarter("Q0-2026")
        assert exc_info.value.status_code == 400

    def test_empty_string(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_quarter("")
        assert exc_info.value.status_code == 400

    def test_year_out_of_range(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_quarter("Q1-1999")
        assert exc_info.value.status_code == 400


# ── quarter_label ────────────────────────────────────────────────────


class TestQuarterLabel:
    def test_january(self):
        assert quarter_label(date(2026, 1, 15)) == "Q1-2026"

    def test_march(self):
        assert quarter_label(date(2026, 3, 31)) == "Q1-2026"

    def test_april(self):
        assert quarter_label(date(2026, 4, 1)) == "Q2-2026"

    def test_june(self):
        assert quarter_label(date(2025, 6, 30)) == "Q2-2025"

    def test_july(self):
        assert quarter_label(date(2026, 7, 1)) == "Q3-2026"

    def test_september(self):
        assert quarter_label(date(2025, 9, 15)) == "Q3-2025"

    def test_october(self):
        assert quarter_label(date(2026, 10, 1)) == "Q4-2026"

    def test_december(self):
        assert quarter_label(date(2025, 12, 31)) == "Q4-2025"


# ── quarter_number ───────────────────────────────────────────────────


class TestQuarterNumber:
    def test_q1(self):
        assert quarter_number(date(2026, 2, 15)) == 1

    def test_q2(self):
        assert quarter_number(date(2026, 5, 1)) == 2

    def test_q3(self):
        assert quarter_number(date(2026, 8, 20)) == 3

    def test_q4(self):
        assert quarter_number(date(2026, 11, 30)) == 4
