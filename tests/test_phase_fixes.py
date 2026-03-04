"""
Tests for Phase 1-3 audit fixes.

Covers: index normalization guard, credit error messaging, rate cap,
WACC params alignment, and transport weight validation.
"""
import pytest


# ── Index Calculation: Division-by-zero guard (Phase 2, fix 2.5) ──────────

def test_index_normalize_zero_span():
    """When min==max, normalization returns 50.0 (midpoint) instead of ZeroDivisionError."""
    from src.engines.index_calculation import IndexCalculationEngine
    engine = IndexCalculationEngine()
    # Temporarily inject a zero-span normalization reference
    engine.NORMALIZATION["_test"] = {"min": 50.0, "max": 50.0}
    result = engine._normalize(50.0, "_test")
    assert result == 50.0


def test_index_normalize_normal_span():
    """Normal span normalizes correctly (regression test)."""
    from src.engines.index_calculation import IndexCalculationEngine
    engine = IndexCalculationEngine()
    # cargo_tonnage: min=0, max=5_000_000
    result = engine._normalize(2_500_000, "cargo_tonnage")
    assert 49.0 <= result <= 51.0  # should be ~50%


# ── Credit Error Messaging (Phase 2, fix 2.10) ──────────────────────────

def test_credit_402_error_includes_balance_and_cost():
    """402 error should include structured detail with balance, cost, topup_url."""
    from src.utils.credits import deduct_credits
    from src.database.models import User, X402Tier
    from fastapi import HTTPException

    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()

    # Use pro tier (query_cost=1.0) — free tier has cost=0 and never errors
    tier = db.query(X402Tier).filter(X402Tier.tier_name == "pro").first()
    if not tier:
        tier = X402Tier(tier_name="pro", query_cost=1.0)
        db.add(tier)
        db.commit()

    user = User(
        username="credit_test_user",
        email="credit@test.com",
        hashed_password="fake_hash",
        x402_balance=0.0,  # zero balance
        tier="pro",  # pro tier costs 1.0 per query
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Try to deduct with zero balance — should raise 402 with structured detail
    with pytest.raises(HTTPException) as exc_info:
        deduct_credits(user, db, "/test", cost_multiplier=1.0)

    assert exc_info.value.status_code == 402
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert "balance" in detail
    assert "cost" in detail
    assert "topup_url" in detail
    db.close()


# ── Bank Rate Cap (Phase 3, fix 3.6) ──────────────────────────────────

def test_rate_cap_prevents_predatory_rates():
    """No rating should produce an effective rate > MAX_EFFECTIVE_RATE_BPS."""
    from src.routes.bank import _rate_premium_bps, MAX_EFFECTIVE_RATE_BPS, _RF

    base_bps = int(_RF * 10_000)
    for rating in ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]:
        premium = _rate_premium_bps(rating)
        effective = base_bps + premium
        assert effective <= MAX_EFFECTIVE_RATE_BPS, (
            f"Rating {rating}: effective {effective} bps > cap {MAX_EFFECTIVE_RATE_BPS}"
        )


# ── WACC Params Alignment (Phase 1, fix 1.4) ─────────────────────────

def test_wacc_params_only_ecowas():
    """WACC params should only contain ECOWAS v3.0 country codes."""
    from src.utils.wacc_params import COUNTRY_WACC_PARAMS, VALID_WASI_COUNTRIES, POLITICAL_RISK

    ecowas = {"NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ",
              "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV"}

    # All three dicts should have exactly the ECOWAS set
    assert set(COUNTRY_WACC_PARAMS.keys()) == ecowas
    assert set(VALID_WASI_COUNTRIES) == ecowas
    assert set(POLITICAL_RISK.keys()) == ecowas

    # Non-ECOWAS codes removed in Phase 1
    for removed in ["CM", "AO", "TZ", "KE", "MA", "MZ", "ET", "MG", "MU"]:
        assert removed not in COUNTRY_WACC_PARAMS


# ── Transport Weight Validation (Phase 2, fix 2.6) ───────────────────

def test_transport_profile_weights_sum_to_one():
    """All transport profiles must have weights summing to 1.0."""
    from src.engines.transport_engine import PROFILE_WEIGHTS

    for profile, weights in PROFILE_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-9, (
            f"Profile {profile} weights sum to {total}, not 1.0"
        )


# ── Composite Engine Weights (existing invariant, regression) ─────────

def test_composite_weights_sum_to_one():
    """ECOWAS v3.0 weights must sum to exactly 1.0."""
    from src.engines.composite_engine import CompositeEngine

    engine = CompositeEngine()
    total = sum(engine.COUNTRY_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}"
    assert len(engine.COUNTRY_WEIGHTS) == 16
