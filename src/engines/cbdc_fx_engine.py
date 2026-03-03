"""
eCFA CBDC FX Conversion Engine.

Handles currency conversion between XOF (eCFA) and the 8 non-XOF
ECOWAS currencies. All rates are quoted as XOF per 1 unit of target:
  e.g., NGN rate=2.54 means 1 NGN = 2.54 XOF

Spread model (per currency volatility tier):
  - Stable:   XOF↔CVE (pegged to EUR)              → 0.15%
  - Medium:   XOF↔GHS, XOF↔GMD, XOF↔MRU            → 0.25%
  - Volatile: XOF↔NGN, XOF↔GNF, XOF↔SLE, XOF↔LRD   → 0.35%
"""
import uuid
import logging
from datetime import timezone, datetime, timedelta, date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.cbdc_models import CbdcFxRate
from src.database.cbdc_payment_models import CbdcRateLock, CbdcFxPosition

logger = logging.getLogger(__name__)

# ── Zone Classification ───────────────────────────────────────────────

WAEMU_COUNTRIES = {"CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW"}

COUNTRY_CURRENCY = {
    "CI": "XOF", "SN": "XOF", "ML": "XOF", "BF": "XOF",
    "BJ": "XOF", "TG": "XOF", "NE": "XOF", "GW": "XOF",
    "NG": "NGN", "GH": "GHS", "GN": "GNF", "SL": "SLE",
    "LR": "LRD", "GM": "GMD", "MR": "MRU", "CV": "CVE",
}

# ── Spread Tiers ──────────────────────────────────────────────────────

SPREAD_TIERS = {
    "CVE": 0.0015,                                          # 0.15% stable
    "GHS": 0.0025, "GMD": 0.0025, "MRU": 0.0025,          # 0.25% medium
    "NGN": 0.0035, "GNF": 0.0035, "SLE": 0.0035, "LRD": 0.0035,  # 0.35% volatile
}

# ── Rate Configuration ────────────────────────────────────────────────

RATE_STALE_HOURS = 24
RATE_LOCK_DEFAULT_SECONDS = 30
RATE_LOCK_MAX_SECONDS = 120


class CbdcFxEngine:
    """FX conversion engine for eCFA cross-border payments."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_rate(self, target_currency: str) -> dict:
        """Look up the latest rate for XOF→target_currency."""
        target_currency = target_currency.upper()

        if target_currency == "XOF":
            return {
                "base": "XOF", "target": "XOF", "rate": 1.0,
                "inverse_rate": 1.0, "spread_percent": 0.0,
                "effective_date": str(date.today()),
                "staleness_hours": 0.0, "is_stale": False,
                "source": "IDENTITY",
            }

        fx = self.db.query(CbdcFxRate).filter(
            CbdcFxRate.target_currency == target_currency,
        ).order_by(desc(CbdcFxRate.effective_date)).first()

        if not fx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No FX rate found for XOF→{target_currency}",
            )

        staleness = (datetime.now(timezone.utc) - datetime.combine(
            fx.effective_date, datetime.min.time(), tzinfo=timezone.utc
        )).total_seconds() / 3600.0

        spread = SPREAD_TIERS.get(target_currency, 0.0035)

        return {
            "base": "XOF",
            "target": target_currency,
            "rate": fx.rate,
            "inverse_rate": round(1.0 / fx.rate, 6) if fx.rate else 0,
            "spread_percent": spread * 100,
            "effective_date": str(fx.effective_date),
            "staleness_hours": round(staleness, 1),
            "is_stale": staleness > RATE_STALE_HOURS,
            "source": fx.source or "BCEAO_SEED",
        }

    def get_all_rates(self) -> list[dict]:
        """Return rates for all 8 non-XOF currencies with staleness info."""
        rates = []
        for currency in sorted(SPREAD_TIERS.keys()):
            try:
                rates.append(self.get_rate(currency))
            except HTTPException:
                pass
        return rates

    def convert(self, amount: float, from_currency: str,
                to_currency: str) -> dict:
        """Convert amount between any two ECOWAS currencies.

        Routes through XOF for non-XOF↔non-XOF pairs.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "amount_source": amount,
                "amount_target": amount,
                "rate_used": 1.0,
                "spread_percent": 0.0,
                "spread_cost_ecfa": 0.0,
                "is_rate_stale": False,
            }

        if from_currency == "XOF":
            return self._convert_xof_to_foreign(amount, to_currency)
        elif to_currency == "XOF":
            return self._convert_foreign_to_xof(amount, from_currency)
        else:
            # Chain: from → XOF → to
            leg1 = self._convert_foreign_to_xof(amount, from_currency)
            leg2 = self._convert_xof_to_foreign(
                leg1["amount_target"], to_currency
            )
            return {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "amount_source": amount,
                "amount_target": leg2["amount_target"],
                "rate_used": leg1["rate_used"] / leg2["rate_used"],
                "spread_percent": leg1["spread_percent"] + leg2["spread_percent"],
                "spread_cost_ecfa": leg1["spread_cost_ecfa"] + leg2["spread_cost_ecfa"],
                "is_rate_stale": leg1["is_rate_stale"] or leg2["is_rate_stale"],
            }

    def lock_rate(self, target_currency: str, amount_ecfa: float,
                  duration_sec: int = RATE_LOCK_DEFAULT_SECONDS) -> dict:
        """Lock a rate for a pending payment. Creates CbdcRateLock row."""
        target_currency = target_currency.upper()
        duration_sec = min(duration_sec, RATE_LOCK_MAX_SECONDS)

        rate_info = self.get_rate(target_currency)
        lock_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration_sec)

        lock = CbdcRateLock(
            lock_id=lock_id,
            base_currency="XOF",
            target_currency=target_currency,
            rate=rate_info["rate"],
            inverse_rate=rate_info["inverse_rate"],
            spread_percent=rate_info["spread_percent"],
            locked_amount_ecfa=amount_ecfa,
            expires_at=expires_at,
        )
        self.db.add(lock)
        self.db.flush()

        return {
            "lock_id": lock_id,
            "rate": rate_info["rate"],
            "spread_percent": rate_info["spread_percent"],
            "expires_at": expires_at,
        }

    def consume_rate_lock(self, lock_id: str, payment_id: str) -> dict:
        """Mark a rate lock as consumed by a payment."""
        lock = self.db.query(CbdcRateLock).filter(
            CbdcRateLock.lock_id == lock_id,
        ).first()

        if not lock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Rate lock {lock_id} not found",
            )
        if lock.consumed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rate lock already consumed",
            )
        expires = lock.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rate lock has expired",
            )

        lock.consumed = True
        lock.consumed_at = datetime.now(timezone.utc)
        lock.payment_id = payment_id

        return {
            "lock_id": lock.lock_id,
            "rate": lock.rate,
            "inverse_rate": lock.inverse_rate,
            "spread_percent": lock.spread_percent,
            "target_currency": lock.target_currency,
        }

    def update_rate(self, target_currency: str, new_rate: float,
                    source: str = "ADMIN") -> dict:
        """Insert or update today's rate for a currency."""
        target_currency = target_currency.upper()
        today = date.today()

        existing = self.db.query(CbdcFxRate).filter(
            CbdcFxRate.target_currency == target_currency,
            CbdcFxRate.effective_date == today,
        ).first()

        inverse = round(1.0 / new_rate, 6) if new_rate else 0

        if existing:
            existing.rate = new_rate
            existing.inverse_rate = inverse
            existing.source = source
        else:
            self.db.add(CbdcFxRate(
                base_currency="XOF",
                target_currency=target_currency,
                rate=new_rate,
                inverse_rate=inverse,
                effective_date=today,
                source=source,
            ))

        self.db.flush()

        return self.get_rate(target_currency)

    def update_position(self, currency: str, amount_ecfa: float,
                        direction: str) -> None:
        """Update net FX position after a conversion.

        direction: BUY (we bought foreign currency) or SELL (we sold it)
        """
        currency = currency.upper()
        position = self.db.query(CbdcFxPosition).filter(
            CbdcFxPosition.currency == currency,
        ).first()

        if not position:
            position = CbdcFxPosition(currency=currency)
            self.db.add(position)
            self.db.flush()

        if direction == "BUY":
            position.net_position_ecfa += amount_ecfa
            position.total_bought_ecfa += amount_ecfa
        elif direction == "SELL":
            position.net_position_ecfa -= amount_ecfa
            position.total_sold_ecfa += amount_ecfa

        if abs(position.net_position_ecfa) > position.position_limit_ecfa * 0.8:
            logger.warning(
                "FX position warning: %s at %.0f / %.0f XOF (%.0f%%)",
                currency, position.net_position_ecfa,
                position.position_limit_ecfa,
                abs(position.net_position_ecfa) / position.position_limit_ecfa * 100,
            )

    def is_same_currency_zone(self, country_a: str, country_b: str) -> bool:
        """Check if two countries share the same currency (both WAEMU)."""
        return country_a in WAEMU_COUNTRIES and country_b in WAEMU_COUNTRIES

    def get_currency_for_country(self, country_code: str) -> str:
        """Get currency code for a country."""
        return COUNTRY_CURRENCY.get(country_code.upper(), "XOF")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _convert_xof_to_foreign(self, amount_xof: float,
                                target_currency: str) -> dict:
        """Convert XOF to a foreign currency."""
        rate_info = self.get_rate(target_currency)
        rate = rate_info["rate"]
        spread = SPREAD_TIERS.get(target_currency, 0.0035)

        # Apply spread: effective rate is higher (more XOF per foreign unit)
        effective_rate = rate * (1.0 + spread)
        amount_foreign = amount_xof / effective_rate
        spread_cost = amount_xof * spread

        return {
            "from_currency": "XOF",
            "to_currency": target_currency,
            "amount_source": amount_xof,
            "amount_target": round(amount_foreign, 2),
            "rate_used": effective_rate,
            "spread_percent": spread * 100,
            "spread_cost_ecfa": round(spread_cost, 2),
            "is_rate_stale": rate_info["is_stale"],
        }

    def _convert_foreign_to_xof(self, amount_foreign: float,
                                source_currency: str) -> dict:
        """Convert a foreign currency to XOF."""
        rate_info = self.get_rate(source_currency)
        rate = rate_info["rate"]
        spread = SPREAD_TIERS.get(source_currency, 0.0035)

        # Apply spread: effective rate is lower (less XOF per foreign unit)
        effective_rate = rate * (1.0 - spread)
        amount_xof = amount_foreign * effective_rate
        spread_cost = amount_foreign * rate * spread

        return {
            "from_currency": source_currency,
            "to_currency": "XOF",
            "amount_source": amount_foreign,
            "amount_target": round(amount_xof, 2),
            "rate_used": effective_rate,
            "spread_percent": spread * 100,
            "spread_cost_ecfa": round(spread_cost, 2),
            "is_rate_stale": rate_info["is_stale"],
        }
