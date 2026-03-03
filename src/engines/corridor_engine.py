"""
Trade Corridor Intelligence Engine — synthesis layer for ECOWAS trade routes.

Combines 6 data dimensions into a single corridor score (0-100):
  1. Transport (25%)   — road quality, transit time, border wait
  2. FX Cost (20%)     — currency conversion cost (inverted: 0 cost = 100)
  3. Trade Volume (15%)— formal + informal bilateral trade volume
  4. Logistics (20%)   — port clearance delays, congestion
  5. Risk (10%)        — political risk, news events, legislative acts
  6. Payment (10%)     — digital payment infrastructure (CBDC + mobile money)

Higher composite = better corridor performance.
"""
import logging
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_

from src.database.models import (
    Country, CountryIndex, BilateralTrade, NewsEvent, RoadCorridor,
    TransportComposite,
)
from src.database.corridor_models import TradeCorridor, CorridorAssessment
from src.database.legislative_models import LegislativeAct

logger = logging.getLogger(__name__)

# ── Weights ──────────────────────────────────────────────────────────────

CORRIDOR_WEIGHTS = {
    "transport": 0.25,
    "fx": 0.20,
    "trade_volume": 0.15,
    "logistics": 0.20,
    "risk": 0.10,
    "payment": 0.10,
}

# WASI country weights (for dashboard weighting)
WASI_WEIGHTS = {
    "NG": 0.28, "CI": 0.22, "GH": 0.15, "SN": 0.10,
    "BF": 0.04, "ML": 0.04, "GN": 0.04, "BJ": 0.03, "TG": 0.03,
    "NE": 0.01, "MR": 0.01, "GW": 0.01, "SL": 0.01,
    "LR": 0.01, "GM": 0.01, "CV": 0.01,
}

RECOMMENDATIONS = {
    "transport": "Road infrastructure upgrade needed — consider alternative corridors or rail",
    "fx": "High FX cost — consider CFA-zone alternatives or hedging",
    "trade_volume": "Low trade volume — corridor underutilized, potential growth opportunity",
    "logistics": "Port/customs bottleneck — clearance delays impacting transit times",
    "risk": "Elevated political/security risk — monitor news events closely",
    "payment": "Limited digital payment infrastructure — cash-dominant corridor",
}

# 10 ECOWAS corridor definitions for bootstrap
CORRIDOR_SEEDS = [
    {
        "corridor_code": "LAGOS-ABIDJAN",
        "name": "Lagos to Abidjan Coastal Corridor",
        "from_country_code": "NG", "to_country_code": "CI",
        "corridor_type": "COASTAL", "distance_km": 992,
        "transit_countries": "BJ,TG",
        "key_border_posts": "Seme-Krake, Hillacondji, Noepe",
        "key_ports": "Apapa, Port Autonome d'Abidjan",
    },
    {
        "corridor_code": "TEMA-OUAGA",
        "name": "Tema to Ouagadougou Transit Corridor",
        "from_country_code": "GH", "to_country_code": "BF",
        "corridor_type": "TRANSIT", "distance_km": 1057,
        "transit_countries": None,
        "key_border_posts": "Paga",
        "key_ports": "Tema",
    },
    {
        "corridor_code": "DAKAR-BAMAKO",
        "name": "Dakar to Bamako Transit Corridor",
        "from_country_code": "SN", "to_country_code": "ML",
        "corridor_type": "TRANSIT", "distance_km": 1250,
        "transit_countries": None,
        "key_border_posts": "Kidira-Diboli",
        "key_ports": "Port Autonome de Dakar",
    },
    {
        "corridor_code": "ABIDJAN-BAMAKO",
        "name": "Abidjan to Bamako Transit Corridor",
        "from_country_code": "CI", "to_country_code": "ML",
        "corridor_type": "TRANSIT", "distance_km": 1146,
        "transit_countries": None,
        "key_border_posts": "Pogo-Zegoua",
        "key_ports": "Port Autonome d'Abidjan",
    },
    {
        "corridor_code": "LOME-NIAMEY",
        "name": "Lome to Niamey Transit Corridor",
        "from_country_code": "TG", "to_country_code": "NE",
        "corridor_type": "TRANSIT", "distance_km": 1150,
        "transit_countries": "BF",
        "key_border_posts": "Cinkasse, Bitou",
        "key_ports": "Port Autonome de Lome",
    },
    {
        "corridor_code": "COTONOU-NIAMEY",
        "name": "Cotonou to Niamey Transit Corridor",
        "from_country_code": "BJ", "to_country_code": "NE",
        "corridor_type": "TRANSIT", "distance_km": 1036,
        "transit_countries": None,
        "key_border_posts": "Malanville-Gaya",
        "key_ports": "Port Autonome de Cotonou",
    },
    {
        "corridor_code": "CONAKRY-FREETOWN",
        "name": "Conakry to Freetown Mining Corridor",
        "from_country_code": "GN", "to_country_code": "SL",
        "corridor_type": "MINING", "distance_km": 305,
        "transit_countries": None,
        "key_border_posts": "Pamelap",
        "key_ports": "Port Autonome de Conakry",
    },
    {
        "corridor_code": "ABIDJAN-ACCRA",
        "name": "Abidjan to Accra Coastal Corridor",
        "from_country_code": "CI", "to_country_code": "GH",
        "corridor_type": "COASTAL", "distance_km": 568,
        "transit_countries": None,
        "key_border_posts": "Noe-Elubo",
        "key_ports": "Port Autonome d'Abidjan, Tema",
    },
    {
        "corridor_code": "LAGOS-COTONOU",
        "name": "Lagos to Cotonou Transit Corridor",
        "from_country_code": "NG", "to_country_code": "BJ",
        "corridor_type": "TRANSIT", "distance_km": 120,
        "transit_countries": None,
        "key_border_posts": "Seme-Krake",
        "key_ports": "Apapa, Port Autonome de Cotonou",
    },
    {
        "corridor_code": "DAKAR-BANJUL",
        "name": "Dakar to Banjul Short Corridor",
        "from_country_code": "SN", "to_country_code": "GM",
        "corridor_type": "SHORT", "distance_km": 395,
        "transit_countries": None,
        "key_border_posts": "Karang",
        "key_ports": "Port Autonome de Dakar",
    },
]


def seed_corridors(db: Session) -> int:
    """Seed corridor definitions if table is empty. Returns count seeded."""
    existing = db.query(TradeCorridor).count()
    if existing > 0:
        return 0
    for seed in CORRIDOR_SEEDS:
        db.add(TradeCorridor(**seed))
    db.commit()
    return len(CORRIDOR_SEEDS)


class CorridorIntelligenceEngine:
    """Trade corridor intelligence — synthesizes 6 data dimensions."""

    def __init__(self, db: Session):
        self.db = db
        self._country_cache: dict[str, int] = {}

    # ── Helpers ────────────────────────────────────────────────────────

    def _country_id(self, code: str) -> Optional[int]:
        if code not in self._country_cache:
            c = self.db.query(Country).filter(Country.code == code).first()
            self._country_cache[code] = c.id if c else None
        return self._country_cache[code]

    # ── Sub-score: Transport (25%) ────────────────────────────────────

    def _transport_score(self, from_cc: str, to_cc: str,
                         corridor_code: str) -> Optional[float]:
        """Road quality + transit time + border wait → 0-100."""
        # Try RoadCorridor data (best source)
        from_id = self._country_id(from_cc)
        to_id = self._country_id(to_cc)

        road_rows = []
        for cid in [from_id, to_id]:
            if cid is None:
                continue
            row = (
                self.db.query(RoadCorridor)
                .filter(RoadCorridor.country_id == cid)
                .order_by(desc(RoadCorridor.period_date))
                .first()
            )
            if row:
                road_rows.append(row)

        if road_rows:
            avg_transit = sum(r.avg_transit_days or 7 for r in road_rows) / len(road_rows)
            avg_border = sum(r.border_wait_hours or 24 for r in road_rows) / len(road_rows)
            avg_quality = sum(r.road_quality_score or 50 for r in road_rows) / len(road_rows)

            transit_score = max(0, (14 - avg_transit) / 11 * 100)
            border_score = max(0, (72 - avg_border) / 68 * 100)

            return round(0.35 * transit_score + 0.35 * border_score + 0.30 * avg_quality, 2)

        # Fallback: TransportComposite for both endpoints
        composites = []
        for cid in [from_id, to_id]:
            if cid is None:
                continue
            tc = (
                self.db.query(TransportComposite)
                .filter(TransportComposite.country_id == cid)
                .order_by(desc(TransportComposite.period_date))
                .first()
            )
            if tc and tc.transport_composite is not None:
                composites.append(tc.transport_composite)

        if composites:
            return round(sum(composites) / len(composites), 2)

        return None

    # ── Sub-score: FX Cost (20%) ──────────────────────────────────────

    def _fx_score(self, from_cc: str, to_cc: str) -> Optional[float]:
        """FX conversion cost inverted → 0-100 (100 = zero cost)."""
        try:
            from src.engines.fx_analytics_engine import FxAnalyticsEngine
            engine = FxAnalyticsEngine(self.db)
            result = engine.compute_trade_cost(from_cc, to_cc, 100_000)
            fx_cost_pct = result.get("fx_cost_pct", 0.0)
            # Invert: 0% cost → 100, 1% cost → 0
            return round(max(0, 100 - fx_cost_pct * 100), 2)
        except Exception as exc:
            logger.debug("fx_score failed for %s→%s: %s", from_cc, to_cc, exc)
            return None

    # ── Sub-score: Trade Volume (15%) ─────────────────────────────────

    def _trade_volume_score(self, from_cc: str, to_cc: str) -> Optional[float]:
        """Normalized bilateral trade volume → 0-100."""
        from_id = self._country_id(from_cc)
        to_id = self._country_id(to_cc)

        formal_vol = 0.0

        # Formal trade: BilateralTrade where partner_code matches to_cc
        if from_id is not None:
            bt = (
                self.db.query(BilateralTrade)
                .filter(
                    BilateralTrade.country_id == from_id,
                    BilateralTrade.partner_code == to_cc,
                )
                .order_by(desc(BilateralTrade.year))
                .first()
            )
            if bt:
                formal_vol = bt.total_trade_usd or 0.0

        # Also check reverse direction
        if to_id is not None and formal_vol == 0.0:
            bt_rev = (
                self.db.query(BilateralTrade)
                .filter(
                    BilateralTrade.country_id == to_id,
                    BilateralTrade.partner_code == from_cc,
                )
                .order_by(desc(BilateralTrade.year))
                .first()
            )
            if bt_rev:
                formal_vol = bt_rev.total_trade_usd or 0.0

        # Informal trade: USSDTradeDeclaration (last 30 days)
        informal_vol = 0.0
        try:
            from src.database.ussd_models import USSDTradeDeclaration
            cutoff = date.today() - timedelta(days=30)
            ussd_sum = (
                self.db.query(func.sum(USSDTradeDeclaration.declared_value_usd))
                .filter(
                    USSDTradeDeclaration.origin_country == from_cc,
                    USSDTradeDeclaration.destination_country == to_cc,
                    USSDTradeDeclaration.period_date >= cutoff,
                )
                .scalar()
            )
            if ussd_sum:
                informal_vol = float(ussd_sum) * 12  # Annualize from 30-day window
        except Exception:
            pass

        total = formal_vol + informal_vol
        if total == 0:
            return None

        # Normalize: $2B = 100
        return round(min(100, total / 2_000_000_000 * 100), 2)

    # ── Sub-score: Logistics (20%) ────────────────────────────────────

    def _logistics_score(self, from_cc: str, to_cc: str) -> Optional[float]:
        """Port clearance + congestion + dwell time → 0-100."""
        from_id = self._country_id(from_cc)
        to_id = self._country_id(to_cc)

        # Try USSD port clearance data
        port_data = []
        try:
            from src.database.ussd_models import USSDPortClearance
            cutoff = date.today() - timedelta(days=7)
            for cid in [from_id, to_id]:
                if cid is None:
                    continue
                pc = (
                    self.db.query(USSDPortClearance)
                    .filter(
                        USSDPortClearance.country_id == cid,
                        USSDPortClearance.period_date >= cutoff,
                    )
                    .order_by(desc(USSDPortClearance.period_date))
                    .first()
                )
                if pc:
                    port_data.append(pc)
        except Exception:
            pass

        if port_data:
            total_delay = sum(
                (p.customs_delay_hours or 0) + (p.inspection_delay_hours or 0)
                for p in port_data
            ) / len(port_data)
            delay_score = max(0, (72 - total_delay) / 68 * 100)

            # Congestion penalty
            congestion_map = {"CRITICAL": -30, "HIGH": -15, "MEDIUM": -5, "LOW": 0}
            worst_congestion = min(
                congestion_map.get(p.congestion_level or "LOW", 0) for p in port_data
            )
            congestion_score = max(0, 100 + worst_congestion)

            # Dwell time from CountryIndex
            dwell_score = self._dwell_score(from_id, to_id)

            return round(
                0.50 * delay_score + 0.30 * (dwell_score or 70) + 0.20 * congestion_score,
                2,
            )

        # Fallback: just dwell time from CountryIndex
        dwell = self._dwell_score(from_id, to_id)
        return round(dwell, 2) if dwell is not None else None

    def _dwell_score(self, from_id: Optional[int],
                     to_id: Optional[int]) -> Optional[float]:
        """Dwell time from CountryIndex → 0-100 (lower dwell = higher score)."""
        dwells = []
        for cid in [from_id, to_id]:
            if cid is None:
                continue
            ci = (
                self.db.query(CountryIndex)
                .filter(CountryIndex.country_id == cid)
                .order_by(desc(CountryIndex.period_date))
                .first()
            )
            if ci and ci.dwell_time_days is not None:
                dwells.append(ci.dwell_time_days)

        if not dwells:
            return None

        avg_dwell = sum(dwells) / len(dwells)
        return max(0, (14 - avg_dwell) / 11 * 100)

    # ── Sub-score: Risk (10%) ─────────────────────────────────────────

    def _risk_score(self, from_cc: str, to_cc: str) -> float:
        """Political + legislative risk inverted → 0-100 (100 = safe)."""
        from_id = self._country_id(from_cc)
        to_id = self._country_id(to_cc)

        score = 80.0  # Baseline: moderately safe

        # Active negative news events for both countries
        for cid in [from_id, to_id]:
            if cid is None:
                continue
            events = (
                self.db.query(NewsEvent)
                .filter(
                    NewsEvent.country_id == cid,
                    NewsEvent.is_active == True,
                    NewsEvent.event_type.in_(["PORT_DISRUPTION", "POLITICAL_RISK", "STRIKE"]),
                )
                .all()
            )
            for ev in events:
                if ev.magnitude is not None and ev.magnitude < 0:
                    score -= 8

        # Restrictive legislative acts (TARIFF/CUSTOMS/TRADE with negative impact)
        for cid in [from_id, to_id]:
            if cid is None:
                continue
            cutoff = date.today() - timedelta(days=30)
            acts = (
                self.db.query(LegislativeAct)
                .filter(
                    LegislativeAct.country_id == cid,
                    LegislativeAct.category.in_(["TARIFF", "CUSTOMS", "TRADE"]),
                    LegislativeAct.act_date >= cutoff,
                    LegislativeAct.estimated_magnitude < 0,
                )
                .all()
            )
            score -= len(acts) * 5

        return round(max(0, min(100, score)), 2)

    # ── Sub-score: Payment (10%) ──────────────────────────────────────

    def _payment_score(self, from_cc: str, to_cc: str) -> Optional[float]:
        """Digital payment activity → 0-100."""
        digital_tx = 0

        # CBDC cross-border payments
        try:
            from src.database.cbdc_payment_models import CbdcCrossBorderPayment
            cutoff = date.today() - timedelta(days=30)
            cbdc_count = (
                self.db.query(func.count(CbdcCrossBorderPayment.id))
                .filter(
                    CbdcCrossBorderPayment.sender_country == from_cc,
                    CbdcCrossBorderPayment.receiver_country == to_cc,
                    CbdcCrossBorderPayment.created_at >= cutoff,
                )
                .scalar()
            ) or 0
            digital_tx += cbdc_count
        except Exception:
            pass

        # Also count reverse direction
        try:
            from src.database.cbdc_payment_models import CbdcCrossBorderPayment
            cutoff = date.today() - timedelta(days=30)
            cbdc_rev = (
                self.db.query(func.count(CbdcCrossBorderPayment.id))
                .filter(
                    CbdcCrossBorderPayment.sender_country == to_cc,
                    CbdcCrossBorderPayment.receiver_country == from_cc,
                    CbdcCrossBorderPayment.created_at >= cutoff,
                )
                .scalar()
            ) or 0
            digital_tx += cbdc_rev
        except Exception:
            pass

        # Mobile money cross-border flows
        try:
            from src.database.ussd_models import USSDMobileMoneyFlow
            from_id = self._country_id(from_cc)
            to_id = self._country_id(to_cc)
            cutoff = date.today() - timedelta(days=7)
            for cid in [from_id, to_id]:
                if cid is None:
                    continue
                mm_sum = (
                    self.db.query(func.sum(USSDMobileMoneyFlow.cross_border_count))
                    .filter(
                        USSDMobileMoneyFlow.country_id == cid,
                        USSDMobileMoneyFlow.period_date >= cutoff,
                    )
                    .scalar()
                )
                if mm_sum:
                    digital_tx += int(mm_sum)
        except Exception:
            pass

        if digital_tx == 0:
            return None

        # 100+ transactions in 30 days = perfect score
        return round(min(100, digital_tx / 100 * 100), 2)

    # ── Main assessment ───────────────────────────────────────────────

    def assess_corridor(self, corridor_code: str) -> Optional[dict]:
        """Full corridor assessment with all 6 sub-scores."""
        corridor = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.corridor_code == corridor_code)
            .first()
        )
        if not corridor:
            return None

        from_cc = corridor.from_country_code
        to_cc = corridor.to_country_code

        # Compute all sub-scores
        scores = {
            "transport": self._transport_score(from_cc, to_cc, corridor_code),
            "fx": self._fx_score(from_cc, to_cc),
            "trade_volume": self._trade_volume_score(from_cc, to_cc),
            "logistics": self._logistics_score(from_cc, to_cc),
            "risk": self._risk_score(from_cc, to_cc),
            "payment": self._payment_score(from_cc, to_cc),
        }

        # Re-normalize weights for available scores (exclude None)
        available = {k: v for k, v in scores.items() if v is not None}
        data_sources_used = len(available)

        if not available:
            composite = None
        else:
            total_weight = sum(CORRIDOR_WEIGHTS[k] for k in available)
            composite = sum(
                v * (CORRIDOR_WEIGHTS[k] / total_weight) for k, v in available.items()
            )
            composite = round(composite, 2)

        # Determine trend (compare with previous assessment)
        trend = "STABLE"
        prev = (
            self.db.query(CorridorAssessment)
            .filter(
                CorridorAssessment.corridor_id == corridor.id,
                CorridorAssessment.assessment_date < date.today(),
            )
            .order_by(desc(CorridorAssessment.assessment_date))
            .first()
        )
        if prev and prev.corridor_composite is not None and composite is not None:
            delta = composite - prev.corridor_composite
            if delta > 5:
                trend = "IMPROVING"
            elif delta < -5:
                trend = "DETERIORATING"

        # Identify bottleneck (lowest available sub-score)
        bottleneck = None
        if available:
            bottleneck = min(available, key=available.get)

        confidence = round(data_sources_used / 6, 2)

        # Upsert CorridorAssessment
        today = date.today()
        existing = (
            self.db.query(CorridorAssessment)
            .filter(
                CorridorAssessment.corridor_id == corridor.id,
                CorridorAssessment.assessment_date == today,
            )
            .first()
        )
        if existing:
            assessment = existing
        else:
            assessment = CorridorAssessment(
                corridor_id=corridor.id,
                assessment_date=today,
            )
            self.db.add(assessment)

        assessment.transport_score = scores["transport"]
        assessment.fx_score = scores["fx"]
        assessment.trade_volume_score = scores["trade_volume"]
        assessment.logistics_score = scores["logistics"]
        assessment.risk_score = scores["risk"]
        assessment.payment_score = scores["payment"]
        assessment.corridor_composite = composite
        assessment.trend = trend
        assessment.bottleneck = bottleneck
        assessment.confidence = confidence
        assessment.data_sources_used = data_sources_used

        return {
            "corridor_code": corridor.corridor_code,
            "name": corridor.name,
            "from_country_code": from_cc,
            "to_country_code": to_cc,
            "corridor_type": corridor.corridor_type,
            "distance_km": corridor.distance_km,
            "transit_countries": corridor.transit_countries,
            "key_border_posts": corridor.key_border_posts,
            "key_ports": corridor.key_ports,
            "assessment_date": str(today),
            "transport_score": scores["transport"],
            "fx_score": scores["fx"],
            "trade_volume_score": scores["trade_volume"],
            "logistics_score": scores["logistics"],
            "risk_score": scores["risk"],
            "payment_score": scores["payment"],
            "corridor_composite": composite,
            "trend": trend,
            "bottleneck": bottleneck,
            "confidence": confidence,
            "data_sources_used": data_sources_used,
        }

    def assess_all_corridors(self) -> dict:
        """Assess all active corridors."""
        corridors = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.is_active == True)
            .all()
        )
        results = []
        for c in corridors:
            result = self.assess_corridor(c.corridor_code)
            if result:
                results.append(result)
        return {
            "corridors_assessed": len(results),
            "results": results,
        }

    def get_corridor_ranking(self) -> list[dict]:
        """All corridors ranked by composite score (descending)."""
        corridors = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.is_active == True)
            .all()
        )
        ranked = []
        for c in corridors:
            latest = (
                self.db.query(CorridorAssessment)
                .filter(CorridorAssessment.corridor_id == c.id)
                .order_by(desc(CorridorAssessment.assessment_date))
                .first()
            )
            ranked.append({
                "corridor_code": c.corridor_code,
                "name": c.name,
                "from_country_code": c.from_country_code,
                "to_country_code": c.to_country_code,
                "corridor_type": c.corridor_type,
                "corridor_composite": latest.corridor_composite if latest else None,
                "trend": latest.trend if latest else None,
                "bottleneck": latest.bottleneck if latest else None,
                "confidence": latest.confidence if latest else 0.0,
            })

        # Sort by composite (None last)
        ranked.sort(key=lambda x: x["corridor_composite"] or -1, reverse=True)
        for i, r in enumerate(ranked, 1):
            r["rank"] = i

        return ranked

    def get_corridor_comparison(self, corridor_codes: list[str]) -> dict:
        """Side-by-side comparison of requested corridors."""
        results = []
        for code in corridor_codes:
            assessment = self.assess_corridor(code)
            if assessment:
                results.append(assessment)

        # Determine which corridor is best on each dimension
        dimensions = ["transport", "fx", "trade_volume", "logistics", "risk", "payment"]
        best_on = {}
        for dim in dimensions:
            key = f"{dim}_score"
            best = max(
                (r for r in results if r.get(key) is not None),
                key=lambda r: r[key],
                default=None,
            )
            if best:
                best_on[dim] = best["corridor_code"]

        return {
            "corridors": results,
            "best_on": best_on,
            "count": len(results),
        }

    def get_bottleneck_analysis(self, corridor_code: str) -> Optional[dict]:
        """Identify weakest dimensions with recommendations."""
        corridor = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.corridor_code == corridor_code)
            .first()
        )
        if not corridor:
            return None

        latest = (
            self.db.query(CorridorAssessment)
            .filter(CorridorAssessment.corridor_id == corridor.id)
            .order_by(desc(CorridorAssessment.assessment_date))
            .first()
        )

        scores = {}
        if latest:
            score_map = {
                "transport": latest.transport_score,
                "fx": latest.fx_score,
                "trade_volume": latest.trade_volume_score,
                "logistics": latest.logistics_score,
                "risk": latest.risk_score,
                "payment": latest.payment_score,
            }
            scores = {k: v for k, v in score_map.items() if v is not None}

        # Sort ascending (weakest first)
        sorted_scores = sorted(scores.items(), key=lambda x: x[1])

        bottlenecks = [
            {
                "dimension": dim,
                "score": score,
                "weight_pct": round(CORRIDOR_WEIGHTS[dim] * 100, 1),
                "recommendation": RECOMMENDATIONS.get(dim, ""),
            }
            for dim, score in sorted_scores
        ]

        # Overall assessment
        if not scores:
            overall = "Insufficient data for bottleneck analysis"
        elif sorted_scores[0][1] < 30:
            overall = f"Critical bottleneck: {sorted_scores[0][0]} ({sorted_scores[0][1]:.1f}/100)"
        elif sorted_scores[0][1] < 50:
            overall = f"Moderate bottleneck: {sorted_scores[0][0]} ({sorted_scores[0][1]:.1f}/100)"
        else:
            overall = "No critical bottlenecks — corridor performing adequately"

        return {
            "corridor_code": corridor_code,
            "name": corridor.name,
            "bottlenecks": bottlenecks,
            "overall_assessment": overall,
            "corridor_composite": latest.corridor_composite if latest else None,
        }

    def get_corridor_history(self, corridor_code: str,
                             days: int = 30) -> Optional[dict]:
        """Assessment history for a corridor."""
        corridor = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.corridor_code == corridor_code)
            .first()
        )
        if not corridor:
            return None

        cutoff = date.today() - timedelta(days=days)
        assessments = (
            self.db.query(CorridorAssessment)
            .filter(
                CorridorAssessment.corridor_id == corridor.id,
                CorridorAssessment.assessment_date >= cutoff,
            )
            .order_by(CorridorAssessment.assessment_date)
            .all()
        )

        return {
            "corridor_code": corridor_code,
            "name": corridor.name,
            "days": days,
            "history": [
                {
                    "assessment_date": str(a.assessment_date),
                    "corridor_composite": a.corridor_composite,
                    "transport_score": a.transport_score,
                    "fx_score": a.fx_score,
                    "trade_volume_score": a.trade_volume_score,
                    "logistics_score": a.logistics_score,
                    "risk_score": a.risk_score,
                    "payment_score": a.payment_score,
                    "trend": a.trend,
                    "bottleneck": a.bottleneck,
                }
                for a in assessments
            ],
        }

    def get_ecowas_corridor_dashboard(self) -> dict:
        """Aggregate ECOWAS corridor dashboard."""
        corridors = (
            self.db.query(TradeCorridor)
            .filter(TradeCorridor.is_active == True)
            .all()
        )

        items = []
        composites = []
        bottleneck_counter = Counter()

        for c in corridors:
            latest = (
                self.db.query(CorridorAssessment)
                .filter(CorridorAssessment.corridor_id == c.id)
                .order_by(desc(CorridorAssessment.assessment_date))
                .first()
            )
            item = {
                "corridor_code": c.corridor_code,
                "name": c.name,
                "from_country_code": c.from_country_code,
                "to_country_code": c.to_country_code,
                "corridor_type": c.corridor_type,
                "corridor_composite": latest.corridor_composite if latest else None,
                "trend": latest.trend if latest else None,
                "bottleneck": latest.bottleneck if latest else None,
            }
            items.append(item)
            if latest and latest.corridor_composite is not None:
                composites.append(latest.corridor_composite)
                # WASI-weighted contribution
                from_w = WASI_WEIGHTS.get(c.from_country_code, 0.01)
                to_w = WASI_WEIGHTS.get(c.to_country_code, 0.01)
                item["_wasi_weight"] = (from_w + to_w) / 2
            if latest and latest.bottleneck:
                bottleneck_counter[latest.bottleneck] += 1

        avg_score = round(sum(composites) / len(composites), 2) if composites else None

        # WASI-weighted corridor health
        weighted_sum = sum(
            (i.get("corridor_composite") or 0) * i.get("_wasi_weight", 0.01)
            for i in items
            if i.get("corridor_composite") is not None
        )
        weight_total = sum(
            i.get("_wasi_weight", 0.01) for i in items
            if i.get("corridor_composite") is not None
        )
        weighted_health = round(weighted_sum / weight_total, 2) if weight_total > 0 else None

        best = max(items, key=lambda x: x.get("corridor_composite") or -1, default=None)
        worst = min(
            (i for i in items if i.get("corridor_composite") is not None),
            key=lambda x: x["corridor_composite"],
            default=None,
        )

        # Clean up internal weight field
        for i in items:
            i.pop("_wasi_weight", None)

        return {
            "as_of": str(date.today()),
            "total_corridors": len(corridors),
            "avg_corridor_score": avg_score,
            "weighted_corridor_health": weighted_health,
            "best_corridor": best["corridor_code"] if best else None,
            "worst_corridor": worst["corridor_code"] if worst else None,
            "most_common_bottleneck": (
                bottleneck_counter.most_common(1)[0][0] if bottleneck_counter else None
            ),
            "corridors": items,
        }
