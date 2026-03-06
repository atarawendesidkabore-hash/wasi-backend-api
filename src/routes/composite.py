from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import numpy as np
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.engines.composite_engine import CompositeEngine
from src.schemas.composite import CompositeResponse, CompositeReport
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter
from datetime import timezone, datetime
from typing import Optional

router = APIRouter(prefix="/api/composite", tags=["Composite"])
limiter = Limiter(key_func=get_remote_address)

# Cached CompositeEngine (weights are constant)
_cached_engine: CompositeEngine | None = None

def _get_engine() -> CompositeEngine:
    global _cached_engine
    if _cached_engine is None:
        _cached_engine = CompositeEngine()
    return _cached_engine


def _get_latest_country_indices(db: Session):
    """Fetch the most recent index value per country using a subquery."""
    subq = (
        db.query(
            CountryIndex.country_id,
            func.max(CountryIndex.period_date).label("max_date"),
        )
        .group_by(CountryIndex.country_id)
        .subquery()
    )
    return (
        db.query(CountryIndex, Country)
        .join(
            subq,
            and_(
                CountryIndex.country_id == subq.c.country_id,
                CountryIndex.period_date == subq.c.max_date,
            ),
        )
        .join(Country, Country.id == CountryIndex.country_id)
        .all()
    )


@router.post("/calculate", response_model=CompositeResponse)
@limiter.limit("10/minute")
async def calculate_composite(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a live WASI composite recalculation from the latest country indices.
    Result is upserted into the database.
    Costs 5 credits.
    """
    deduct_credits(current_user, db, "/api/composite/calculate", cost_multiplier=5.0)

    rows = _get_latest_country_indices(db)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No country index data available. Ingest CSV data first.",
        )

    country_indices = {row.Country.code: row.CountryIndex.index_value for row in rows}
    period_date = max(row.CountryIndex.period_date for row in rows)

    history_records = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.asc())
        .limit(120)
        .all()
    )
    history_values = [r.composite_value for r in history_records]

    engine = _get_engine()
    result = engine.calculate_composite(country_indices, period_date, history_values)

    exclude_keys = {"period_date", "country_contributions"}
    existing = db.query(WASIComposite).filter(
        WASIComposite.period_date == period_date
    ).first()

    if existing:
        for k, v in result.items():
            if k not in exclude_keys:
                setattr(existing, k, v)
        existing.calculated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    composite = WASIComposite(
        period_date=period_date,
        **{k: v for k, v in result.items() if k not in exclude_keys},
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(composite)
    db.commit()
    db.refresh(composite)
    return composite


@router.get("/report", response_model=CompositeReport)
@limiter.limit("20/minute")
async def get_composite_report(
    request: Request,
    quarter: Optional[str] = Query(default=None, description="Filter history by quarter: Q1-2026, T3-2025, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full composite report: latest value + 12-month history + country contributions.
    Costs 3 credits.
    """
    deduct_credits(current_user, db, "/api/composite/report", cost_multiplier=3.0)

    latest = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )
    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No composite data available. Call POST /api/composite/calculate first.",
        )

    history_query = db.query(WASIComposite)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        history_query = history_query.filter(WASIComposite.period_date.between(q_start, q_end))
    history = (
        history_query
        .order_by(WASIComposite.period_date.desc())
        .limit(12)
        .all()
    )

    # Re-derive contributions from latest country indices
    rows = _get_latest_country_indices(db)
    engine = _get_engine()
    country_indices = {row.Country.code: row.CountryIndex.index_value for row in rows}
    available = {
        code: val for code, val in country_indices.items()
        if code in engine.COUNTRY_WEIGHTS
    }
    total_w = sum(engine.COUNTRY_WEIGHTS[c] for c in available)
    contributions = {
        code: round(val * (engine.COUNTRY_WEIGHTS[code] / total_w), 4)
        for code, val in available.items()
    }

    # T6: concentration_warning — flag when any country's effective weight > 25%
    # AND its current index_value is > 2 SD from its own 12-month historical mean.
    concentration_warning: Optional[str] = None
    high_weight = [
        row for row in rows
        if row.Country.code in available
        and engine.COUNTRY_WEIGHTS[row.Country.code] / total_w > 0.25
    ]
    if high_weight:
        # Batch-fetch last 13 months for all high-weight countries in one query
        hw_ids = [row.Country.id for row in high_weight]
        from sqlalchemy import case
        all_hist = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id.in_(hw_ids))
            .order_by(CountryIndex.country_id, CountryIndex.period_date.desc())
            .all()
        )
        # Group by country_id, keep only first 13 per country
        hist_by_country: dict[int, list] = {}
        for r in all_hist:
            lst = hist_by_country.setdefault(r.country_id, [])
            if len(lst) < 13:
                lst.append(r.index_value)
        for row in high_weight:
            code = row.Country.code
            eff_weight = engine.COUNTRY_WEIGHTS[code] / total_w
            hist_vals = [v for v in hist_by_country.get(row.Country.id, []) if v is not None]
            if len(hist_vals) < 3:
                continue
            current_val = hist_vals[0]
            hist_arr = np.array(hist_vals[1:], dtype=float)
            mean = float(np.mean(hist_arr))
            std = float(np.std(hist_arr, ddof=1)) if len(hist_arr) > 1 else 0.0
            if std > 0 and abs(current_val - mean) > 2 * std:
                sd_dist = abs(current_val - mean) / std
                direction = "above" if current_val > mean else "below"
                concentration_warning = (
                    f"{code} carries {eff_weight * 100:.1f}% of composite weight and "
                    f"its index ({current_val:.1f}) is {sd_dist:.1f}σ {direction} its "
                    f"12-month mean ({mean:.1f}). Composite may be distorted by "
                    f"single-country movement."
                )
                break

    return CompositeReport(
        latest=latest,
        history_12m=history,
        country_contributions=contributions,
        generated_at=datetime.now(timezone.utc),
        concentration_warning=concentration_warning,
    )
