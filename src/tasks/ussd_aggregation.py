"""
USSD Data Aggregation Task.

Runs every 4 hours (configurable) to:
  1. Aggregate raw USSD data → daily country-level signals
  2. Compute USSD composite score per country
  3. Feed USSD signals into the WASI index calculation

Schedule: Every 4 hours (06:00, 10:00, 14:00, 18:00, 22:00, 02:00 UTC)
This is more frequent than the 6h composite update because USSD data
arrives in real-time and captures intra-day economic activity.
"""
from __future__ import annotations

import logging
from datetime import timezone, date, datetime

from src.database.connection import SessionLocal
from src.engines.ussd_engine import USSDDataAggregator

logger = logging.getLogger(__name__)


def run_ussd_aggregation(db=None) -> dict:
    """
    Aggregate USSD data across all 16 WASI countries for every date that has data.

    Discovers all distinct period_dates in the four USSD tables and runs
    aggregation for each date.  This ensures historical data (e.g. 2025 monthly
    records from scrapers) is properly scored — not just today's date.

    Can be called:
      - By APScheduler every 4 hours
      - Manually via POST /api/v2/ussd/aggregate/calculate
      - At startup after real data scrapers run

    Returns summary dict.
    """
    from sqlalchemy import union_all, select
    from src.database.ussd_models import (
        USSDMobileMoneyFlow, USSDCommodityReport,
        USSDTradeDeclaration, USSDPortClearance,
        USSDRouteReport,
    )

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        aggregator = USSDDataAggregator(db)

        # Collect every distinct period_date across all four USSD tables
        q = union_all(
            select(USSDMobileMoneyFlow.period_date),
            select(USSDCommodityReport.period_date),
            select(USSDTradeDeclaration.period_date),
            select(USSDPortClearance.period_date),
            select(USSDRouteReport.period_date),
        )
        all_dates = sorted(
            {row[0] for row in db.execute(q).fetchall() if row[0] is not None}
        )

        if not all_dates:
            logger.info("USSD aggregation: no data found in any table — skipping")
            return {
                "status": "completed",
                "period_dates": 0,
                "countries_processed": 0,
                "countries_with_data": 0,
                "total_data_points": 0,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

        total_countries_with_data = 0
        total_data_points = 0
        total_countries_processed = 0

        for target_date in all_dates:
            results = aggregator.aggregate_all(target_date)
            total_countries_processed += len(results)
            total_countries_with_data += sum(
                1 for r in results if r.get("ussd_composite_score") is not None
            )
            total_data_points += sum(r.get("data_points", 0) for r in results)

        logger.info(
            "USSD aggregation complete: %d dates, %d/%d country-date pairs with data, %d total data points",
            len(all_dates), total_countries_with_data, total_countries_processed,
            total_data_points,
        )

        return {
            "status": "completed",
            "period_dates": len(all_dates),
            "date_range": f"{all_dates[0]} to {all_dates[-1]}",
            "countries_processed": total_countries_processed,
            "countries_with_data": total_countries_with_data,
            "total_data_points": total_data_points,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("USSD aggregation failed: %s", exc)
        db.rollback()
        return {
            "status": "error",
            "error": str(exc),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if own_session:
            db.close()


def bridge_route_to_road_corridors(db=None) -> dict:
    """
    Bridge crowdsourced USSDRouteReport data into the RoadCorridor model.

    For each corridor with USSD reports today:
      - road_quality_score = weighted avg of condition_score reports
      - border_wait_hours = avg of border wait reports
      - avg_transit_days = avg of transit_time reports / 24
      - Confidence blended: existing * 0.6 + ussd * 0.4
    """
    from collections import defaultdict
    from src.database.ussd_models import USSDRouteReport
    from src.database.models import RoadCorridor, Country

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        today = date.today()
        period = today.replace(day=1)  # RoadCorridor uses monthly periods

        reports = (
            db.query(USSDRouteReport)
            .filter(USSDRouteReport.period_date == today)
            .all()
        )

        if not reports:
            return {"status": "no_data", "corridors_updated": 0}

        grouped = defaultdict(list)
        for r in reports:
            grouped[(r.country_id, r.corridor_code)].append(r)

        updated = 0
        for (country_id, corridor_code), group in grouped.items():
            condition_scores = [
                r.condition_score for r in group
                if r.report_type == "ROAD_CONDITION" and r.condition_score is not None
            ]
            wait_hours_list = [
                r.wait_hours for r in group
                if r.report_type == "BORDER_WAIT" and r.wait_hours is not None
            ]
            transit_hours_list = [
                r.transit_hours for r in group
                if r.report_type == "TRANSIT_TIME" and r.transit_hours is not None
            ]
            total_reporters = sum(r.reporter_count for r in group)

            existing = (
                db.query(RoadCorridor)
                .filter(
                    RoadCorridor.country_id == country_id,
                    RoadCorridor.period_date == period,
                    RoadCorridor.corridor_name == corridor_code,
                )
                .first()
            )

            if existing:
                if condition_scores:
                    ussd_quality = sum(condition_scores) / len(condition_scores)
                    if existing.road_quality_score is not None:
                        existing.road_quality_score = existing.road_quality_score * 0.6 + ussd_quality * 0.4
                    else:
                        existing.road_quality_score = ussd_quality
                if wait_hours_list:
                    ussd_wait = sum(wait_hours_list) / len(wait_hours_list)
                    if existing.border_wait_hours is not None:
                        existing.border_wait_hours = existing.border_wait_hours * 0.6 + ussd_wait * 0.4
                    else:
                        existing.border_wait_hours = ussd_wait
                if transit_hours_list:
                    ussd_transit_days = (sum(transit_hours_list) / len(transit_hours_list)) / 24.0
                    if existing.avg_transit_days is not None:
                        existing.avg_transit_days = existing.avg_transit_days * 0.6 + ussd_transit_days * 0.4
                    else:
                        existing.avg_transit_days = ussd_transit_days
                existing.confidence = min(0.85, (existing.confidence or 0.65) + 0.02 * total_reporters)
                existing.data_source = "corridor_estimate+ussd"
            else:
                corridor_name = group[0].corridor_name if group else corridor_code
                avg_quality = sum(condition_scores) / len(condition_scores) if condition_scores else None
                avg_wait = sum(wait_hours_list) / len(wait_hours_list) if wait_hours_list else None
                avg_transit = (sum(transit_hours_list) / len(transit_hours_list) / 24.0) if transit_hours_list else None

                road = RoadCorridor(
                    country_id=country_id,
                    period_date=period,
                    corridor_name=corridor_code,
                    road_quality_score=avg_quality,
                    border_wait_hours=avg_wait,
                    avg_transit_days=avg_transit,
                    truck_count=total_reporters,
                    data_source="ussd_crowdsource",
                    confidence=min(0.70, 0.35 + 0.05 * total_reporters),
                )
                db.add(road)

            updated += 1

        db.commit()
        return {
            "status": "completed",
            "corridors_updated": updated,
            "total_reporters": sum(r.reporter_count for r in reports),
        }

    except Exception as exc:
        logger.error("Route-to-corridor bridge failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


def seed_ussd_demo_data(db=None) -> int:
    """
    Seed demo USSD data for development/testing.

    Creates realistic mobile money flows, commodity reports, trade declarations,
    and port clearance data for the 4 primary WASI countries (NG, CI, GH, SN).

    Returns number of records created.
    """
    from src.database.models import Country
    from src.database.ussd_models import (
        USSDProvider, USSDMobileMoneyFlow, USSDCommodityReport,
        USSDTradeDeclaration, USSDPortClearance,
    )
    from datetime import timedelta
    import random

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # Check if demo data already exists
        existing = db.query(USSDMobileMoneyFlow).count()
        if existing > 0:
            logger.info("USSD demo data already exists (%d records) — skipping", existing)
            return 0

        count = 0

        # Register demo providers
        providers_data = [
            ("ORANGE_MONEY", "Orange Money", "CI,SN,ML,GN,BF", "*144#"),
            ("MTN_MOMO", "MTN Mobile Money", "GH,NG,BJ,CI", "*170#"),
            ("WAVE", "Wave Digital Finance", "SN,CI,ML,BF", "*770#"),
            ("MOOV_MONEY", "Moov Africa Money", "BJ,TG,CI,BF,NE", "*155#"),
        ]

        for code, name, countries, shortcode in providers_data:
            existing_p = db.query(USSDProvider).filter(USSDProvider.provider_code == code).first()
            if not existing_p:
                import hashlib
                demo_key = f"demo_{code.lower()}_key"
                p = USSDProvider(
                    provider_code=code,
                    provider_name=name,
                    country_codes=countries,
                    ussd_shortcode=shortcode,
                    api_key_hash=hashlib.sha256(demo_key.encode()).hexdigest(),
                )
                db.add(p)
                count += 1

        db.flush()

        # Demo mobile money flows (30 days, 4 primary countries)
        today = date.today()
        primary_countries = {
            "NG": {"currency": "NGN", "fx": 1550.0, "providers": ["MTN_MOMO"], "base_txns": 500000},
            "CI": {"currency": "XOF", "fx": 610.0, "providers": ["ORANGE_MONEY", "WAVE"], "base_txns": 300000},
            "GH": {"currency": "GHS", "fx": 15.0, "providers": ["MTN_MOMO"], "base_txns": 200000},
            "SN": {"currency": "XOF", "fx": 610.0, "providers": ["ORANGE_MONEY", "WAVE"], "base_txns": 150000},
        }

        for cc, params in primary_countries.items():
            country = db.query(Country).filter(Country.code == cc).first()
            if not country:
                continue

            for day_offset in range(30):
                d = today - timedelta(days=day_offset)
                for prov in params["providers"]:
                    # Random variation ±20%
                    txns = int(params["base_txns"] * random.uniform(0.80, 1.20))
                    avg_local = random.uniform(5000, 50000) if params["currency"] == "XOF" else random.uniform(2000, 20000)
                    total_local = txns * avg_local

                    flow = USSDMobileMoneyFlow(
                        country_id=country.id,
                        provider_code=prov,
                        period_date=d,
                        transaction_count=txns,
                        total_value_local=total_local,
                        total_value_usd=total_local / params["fx"],
                        avg_transaction_local=avg_local,
                        avg_transaction_usd=avg_local / params["fx"],
                        p2p_count=int(txns * 0.45),
                        merchant_count=int(txns * 0.25),
                        bill_pay_count=int(txns * 0.10),
                        cash_in_count=int(txns * 0.10),
                        cash_out_count=int(txns * 0.08),
                        cross_border_count=int(txns * 0.02),
                        local_currency=params["currency"],
                        fx_rate_usd=params["fx"],
                        confidence=0.85,
                    )
                    db.add(flow)
                    count += 1

        # Demo commodity reports (7 days, primary countries)
        commodities = [
            ("LOCAL_RICE", "Riz local", 350, 600),    # XOF/kg range
            ("IMPORTED_RICE", "Riz importé", 400, 700),
            ("MAIZE", "Maïs", 150, 300),
            ("ONION", "Oignon", 200, 500),
        ]

        for cc in ["CI", "SN", "BF", "NG"]:
            country = db.query(Country).filter(Country.code == cc).first()
            if not country:
                continue
            currency = "XOF" if cc != "NG" else "NGN"
            fx = 610.0 if cc != "NG" else 1550.0

            for day_offset in range(7):
                d = today - timedelta(days=day_offset)
                for code, name, lo, hi in commodities:
                    price = random.uniform(lo, hi)
                    if cc == "NG":
                        price *= 2.5  # Naira prices higher numerically

                    report = USSDCommodityReport(
                        country_id=country.id,
                        period_date=d,
                        market_name="USSD_AGGREGATE",
                        market_type="MIXED",
                        commodity_code=code,
                        commodity_name=name,
                        price_local=price,
                        price_usd=price / fx,
                        local_currency=currency,
                        report_count=random.randint(3, 25),
                        confidence=0.60,
                    )
                    db.add(report)
                    count += 1

        # Demo trade declarations (7 days)
        borders = [
            ("SEME-KRAKE", "NG", "BJ"),
            ("AFLAO-LOME", "GH", "TG"),
            ("NIANGOLOKO", "BF", "CI"),
            ("KIDIRA", "SN", "ML"),
        ]

        for post, origin, dest in borders:
            country = db.query(Country).filter(Country.code == origin).first()
            if not country:
                continue
            currency = "XOF" if origin in ("CI", "SN", "ML", "BF", "BJ", "TG") else ("NGN" if origin == "NG" else "GHS")
            fx = {"XOF": 610.0, "NGN": 1550.0, "GHS": 15.0}.get(currency, 610.0)

            for day_offset in range(7):
                d = today - timedelta(days=day_offset)
                for direction in ["EXPORT", "IMPORT"]:
                    value_local = random.uniform(1_000_000, 50_000_000)
                    decl = USSDTradeDeclaration(
                        country_id=country.id,
                        period_date=d,
                        border_post=post,
                        origin_country=origin,
                        destination_country=dest,
                        direction=direction,
                        commodity_category=random.choice(["FOOD_GRAINS", "LIVESTOCK", "TEXTILES", "FUEL"]),
                        declared_value_local=value_local,
                        declared_value_usd=value_local / fx,
                        local_currency=currency,
                        declaration_count=random.randint(5, 50),
                        confidence=0.50,
                    )
                    db.add(decl)
                    count += 1

        # Demo port clearance reports (7 days)
        ports = [
            ("NGAPP", "NG", "Port Apapa, Lagos"),
            ("CIABJ", "CI", "Port Autonome d'Abidjan"),
            ("GHTEM", "GH", "Port de Tema"),
            ("SNDKR", "SN", "Port Autonome de Dakar"),
        ]

        for code, cc, name in ports:
            country = db.query(Country).filter(Country.code == cc).first()
            if not country:
                continue

            for day_offset in range(7):
                d = today - timedelta(days=day_offset)
                congestion = random.choice(["LOW", "MEDIUM", "HIGH"])
                delay = {"LOW": 24, "MEDIUM": 72, "HIGH": 168}[congestion]

                clearance = USSDPortClearance(
                    country_id=country.id,
                    period_date=d,
                    port_name=name,
                    port_code=code,
                    containers_cleared=random.randint(50, 500),
                    containers_pending=random.randint(10, 200),
                    avg_clearance_hours=delay * random.uniform(0.5, 1.5),
                    congestion_level=congestion,
                    customs_delay_hours=delay * random.uniform(0.3, 0.8),
                    reporter_count=random.randint(3, 20),
                    confidence=0.65,
                )
                db.add(clearance)
                count += 1

        # Demo route reports (7 days, 6 key corridors)
        from src.database.ussd_models import USSDRouteReport

        corridors_demo = [
            ("ABIDJAN-OUAGADOUGOU", "CI", "Abidjan - Ouagadougou"),
            ("TEMA-OUAGADOUGOU", "GH", "Tema - Ouagadougou"),
            ("DAKAR-BAMAKO", "SN", "Dakar - Bamako"),
            ("LAGOS-COTONOU", "NG", "Lagos - Cotonou"),
            ("ABIDJAN-BAMAKO", "CI", "Abidjan - Bamako"),
            ("LOME-NIAMEY", "TG", "Lomé - Niamey"),
        ]
        surfaces = ["PAVED", "PAVED", "PAVED", "GRAVEL", "DIRT"]
        surface_scores_map = {"PAVED": 85, "GRAVEL": 55, "DIRT": 30, "FLOODED": 10}

        for corridor_code, cc, corridor_name in corridors_demo:
            country = db.query(Country).filter(Country.code == cc).first()
            if not country:
                continue
            currency = "XOF" if cc != "NG" else "NGN"

            for day_offset in range(7):
                d = today - timedelta(days=day_offset)
                surface = random.choice(surfaces)
                # Road condition report
                db.add(USSDRouteReport(
                    country_id=country.id,
                    period_date=d,
                    corridor_code=corridor_code,
                    corridor_name=corridor_name,
                    report_type="ROAD_CONDITION",
                    road_surface=surface,
                    condition_score=float(surface_scores_map.get(surface, 50)),
                    reporter_phone_hash="demo_hash",
                    reporter_type=random.choice(["TRUCKER", "TRADER", "TRAVELER"]),
                    reporter_count=random.randint(3, 15),
                    local_currency=currency,
                    confidence=0.55,
                ))
                count += 1
                # Border wait report
                db.add(USSDRouteReport(
                    country_id=country.id,
                    period_date=d,
                    corridor_code=corridor_code,
                    corridor_name=corridor_name,
                    report_type="BORDER_WAIT",
                    wait_hours=random.uniform(2, 24),
                    queue_vehicles=random.randint(5, 80),
                    reporter_phone_hash="demo_hash",
                    reporter_type="TRUCKER",
                    reporter_count=random.randint(2, 10),
                    local_currency=currency,
                    confidence=0.50,
                ))
                count += 1
                # Transit time report
                db.add(USSDRouteReport(
                    country_id=country.id,
                    period_date=d,
                    corridor_code=corridor_code,
                    corridor_name=corridor_name,
                    report_type="TRANSIT_TIME",
                    transit_hours=random.uniform(8, 48),
                    reporter_phone_hash="demo_hash",
                    reporter_type="TRUCKER",
                    reporter_count=random.randint(2, 8),
                    local_currency=currency,
                    confidence=0.50,
                ))
                count += 1

        db.commit()
        logger.info("Seeded %d USSD demo records", count)
        return count

    except Exception as exc:
        logger.error("USSD demo seed failed: %s", exc)
        db.rollback()
        return 0
    finally:
        if own_session:
            db.close()
