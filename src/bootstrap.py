"""
Bootstrap registry — each step is an independent function with its own error handling.

Steps are executed in order during startup. Each step receives a SQLAlchemy Session
and logs its own results. Failures are non-fatal (logged and skipped) so one broken
bootstrap doesn't block the entire application.
"""
import logging
from sqlalchemy.orm import Session
from src.config import settings

logger = logging.getLogger(__name__)


# ── Step registry ─────────────────────────────────────────────────────────────

def seed_reference_data(db: Session):
    """Seed 16 ECOWAS countries and tier definitions."""
    from src.database.seed import seed_countries
    seed_countries(db)
    logger.info("Database seeded with 16 WASI countries and tier definitions")


def seed_trade_data(db: Session):
    """Seed bilateral trade records (2022 annual estimates)."""
    from src.database.seed import seed_bilateral_trade
    n = seed_bilateral_trade(db)
    if n:
        logger.info("Seeded %d bilateral trade records", n)


def ingest_csv_data(db: Session):
    """Ingest CSV files from data/ directory."""
    from src.tasks.data_ingestion import ingest_all_csv_files
    result = ingest_all_csv_files(db)
    if result:
        logger.info("CSV ingestion complete: %s", result)
    else:
        logger.info("No new CSV data to ingest")


def seed_stock_markets(db: Session):
    """Seed historical stock market data (NGX/GSE/BRVM 2019-2023)."""
    from src.database.seed import seed_stock_market_data
    n = seed_stock_market_data(db)
    if n:
        logger.info("Seeded %d stock market records (NGX/GSE/BRVM)", n)


def ingest_bceao(db: Session):
    """Enrich CI/SN/BJ/TG with BCEAO central-bank data."""
    from src.tasks.data_ingestion import ingest_bceao_data
    result = ingest_bceao_data(db)
    logger.info(
        "BCEAO ingestion: fetched=%d updated=%d inserted=%d skipped=%d",
        result.get("records_fetched", 0),
        result.get("updated", 0),
        result.get("inserted", 0),
        result.get("skipped", 0),
    )


def seed_transport(db: Session):
    """Seed transport data (SITARAIL + primary airport traffic)."""
    from src.database.seed import seed_transport_data
    n = seed_transport_data(db)
    if n:
        logger.info("Seeded %d transport records (air/rail)", n)


def seed_roads(db: Session):
    """Seed road corridor data (ECOWAS 2024 key ground corridors)."""
    from src.database.seed import seed_road_data
    n = seed_road_data(db)
    if n:
        logger.info("Seeded %d road corridor records", n)


def bootstrap_worldbank(db: Session):
    """World Bank data — run scraper if no WB data exists."""
    from src.database.models import CountryIndex
    wb_count = db.query(CountryIndex).filter(
        CountryIndex.data_source == "World Bank Open Data API"
    ).count()
    if wb_count == 0:
        logger.info("No World Bank data found — running initial WB scraper (may take ~90s)...")
        from src.pipelines.scrapers.worldbank_scraper import run_worldbank_scraper
        result = run_worldbank_scraper(db=None)
        logger.info("WB bootstrap complete: updated=%d errors=%d year=%s",
                     result["updated"], result["errors"], result["data_year"])
    else:
        logger.info("World Bank data already present (%d records) — skipping bootstrap", wb_count)


def bootstrap_imf(db: Session):
    """IMF WEO data — run scraper if no IMF data exists."""
    from src.database.models import MacroIndicator
    count = db.query(MacroIndicator).filter(
        MacroIndicator.data_source == "imf_weo"
    ).count()
    if count == 0:
        logger.info("No IMF data found — running initial IMF scraper...")
        from src.pipelines.scrapers.imf_scraper import run_imf_scraper
        result = run_imf_scraper(db=None)
        logger.info("IMF bootstrap complete: updated=%d errors=%d year=%s",
                     result["updated"], result["errors"], result["data_year"])
    else:
        logger.info("IMF data already present (%d records) — skipping bootstrap", count)


def bootstrap_commodities(db: Session):
    """Commodity prices — run Pink Sheet scraper if no prices exist."""
    from src.database.models import CommodityPrice
    count = db.query(CommodityPrice).count()
    if count == 0:
        logger.info("No commodity price data found — running initial Pink Sheet scraper...")
        from src.pipelines.scrapers.commodity_scraper import run_commodity_scraper
        result = run_commodity_scraper(db=None)
        logger.info("Commodity bootstrap complete: updated=%d errors=%d",
                     result["updated"], result["errors"])
    else:
        logger.info("Commodity price data present (%d records) — skipping bootstrap", count)


def bootstrap_ussd(db: Session):
    """USSD data — scrape real data from public APIs on first startup."""
    import src.database.ussd_models  # noqa: ensure USSD tables are created
    from src.database.ussd_models import USSDMobileMoneyFlow, USSDCommodityReport
    from src.tasks.ussd_real_scrapers import (
        run_wfp_food_price_scraper, run_bceao_mobile_money_scraper,
        run_port_throughput_scraper, run_ecowas_trade_scraper,
        seed_ussd_providers,
    )
    from src.tasks.ussd_aggregation import run_ussd_aggregation

    seed_ussd_providers(db)

    mm_count = db.query(USSDMobileMoneyFlow).count()
    cp_count = db.query(USSDCommodityReport).count()
    if mm_count == 0 and cp_count == 0:
        logger.info("No USSD data found — running real data scrapers...")
        for name, fn in [
            ("WFP food prices", run_wfp_food_price_scraper),
            ("BCEAO mobile money", run_bceao_mobile_money_scraper),
            ("Port throughput", run_port_throughput_scraper),
            ("ECOWAS trade", run_ecowas_trade_scraper),
        ]:
            try:
                result = fn(db)
                logger.info("%s: %d records", name, result.get("records_created", 0))
            except Exception as e:
                logger.warning("%s scraper failed (non-fatal): %s", name, e)
        agg_result = run_ussd_aggregation(db)
        logger.info("USSD aggregation: %s", agg_result.get("status"))
    else:
        logger.info("USSD data already present (money=%d, commodity=%d) — skipping bootstrap",
                     mm_count, cp_count)


def bootstrap_ussd_providers_only(db: Session):
    """Register USSD providers (no network needed)."""
    import src.database.ussd_models  # noqa
    from src.tasks.ussd_real_scrapers import seed_ussd_providers
    seed_ussd_providers(db)


def bootstrap_acled(db: Session):
    """ACLED conflict data — apply fallback signals on first startup."""
    from src.pipelines.scrapers.acled_scraper import run_acled_scraper
    result = run_acled_scraper(db=None)
    logger.info("ACLED bootstrap: events_created=%d api_used=%s",
                result["events_created"], result["api_used"])


def bootstrap_ecfa_cbdc(db: Session):
    """Create BCEAO treasury wallets, FX rates, and default policy rates."""
    from src.database.models import Country
    from src.database.cbdc_models import CbdcWallet, CbdcFxRate, CbdcPolicyRate
    from src.utils.cbdc_crypto import generate_wallet_id
    from datetime import date as _date
    import uuid as _uuid

    waemu_codes = ["CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW"]
    cb_count = 0
    for cc in waemu_codes:
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue
        existing = db.query(CbdcWallet).filter(
            CbdcWallet.wallet_type == "CENTRAL_BANK",
            CbdcWallet.country_id == country.id,
        ).first()
        if not existing:
            db.add(CbdcWallet(
                wallet_id=generate_wallet_id(),
                country_id=country.id,
                wallet_type="CENTRAL_BANK",
                institution_code="BCEAO",
                institution_name=f"BCEAO Treasury — {cc}",
                kyc_tier=3,
                daily_limit_ecfa=999_999_999_999.0,
                balance_limit_ecfa=999_999_999_999.0,
                status="active",
            ))
            cb_count += 1

    fx_pairs = {
        "NGN": 2.54, "GHS": 0.041, "GNF": 14.10,
        "SLE": 0.036, "LRD": 0.315, "GMD": 0.115,
        "MRU": 0.066, "CVE": 0.167,
    }
    for currency, rate in fx_pairs.items():
        existing = db.query(CbdcFxRate).filter(
            CbdcFxRate.target_currency == currency,
            CbdcFxRate.effective_date == _date.today(),
        ).first()
        if not existing:
            db.add(CbdcFxRate(
                base_currency="XOF",
                target_currency=currency,
                rate=rate,
                inverse_rate=round(1.0 / rate, 4) if rate else 0,
                effective_date=_date.today(),
                source="BCEAO_SEED",
            ))

    existing_td = db.query(CbdcPolicyRate).filter(
        CbdcPolicyRate.rate_type == "TAUX_DIRECTEUR",
        CbdcPolicyRate.is_current == True,
    ).first()
    if not existing_td:
        _today = _date.today()
        for rtype, rval in [
            ("TAUX_DIRECTEUR", 3.50), ("TAUX_PRET_MARGINAL", 5.50),
            ("TAUX_DEPOT", 1.50), ("TAUX_RESERVE", 3.00),
        ]:
            db.add(CbdcPolicyRate(
                rate_id=str(_uuid.uuid4()),
                rate_type=rtype,
                rate_percent=rval,
                decided_by="BCEAO_SEED",
                rationale="Default BCEAO rates as of December 2024",
                effective_date=_today,
                announced_date=_today,
                is_current=True,
            ))
        logger.info("eCFA bootstrap: seeded 4 default BCEAO policy rates")

    db.commit()
    if cb_count > 0:
        logger.info("eCFA bootstrap: created %d BCEAO treasury wallets + FX rates", cb_count)
    else:
        logger.info("eCFA CBDC tables ready (treasury wallets already exist)")


def bootstrap_tokenization(db: Session):
    """Seed tokenization demo data if tables are empty."""
    from src.database.tokenization_models import DailyActivityDeclaration
    count = db.query(DailyActivityDeclaration).count()
    if count == 0:
        logger.info("No tokenization data found — seeding demo data...")
        from src.tasks.tokenization_aggregation import (
            seed_tokenization_demo_data, run_tokenization_aggregation,
        )
        n = seed_tokenization_demo_data(db)
        if n:
            logger.info("Seeded %d tokenization demo records", n)
            agg = run_tokenization_aggregation(db)
            logger.info("Tokenization aggregation: %s", agg.get("status"))
    else:
        logger.info("Tokenization data present (%d records) — skipping", count)


def bootstrap_legislative(db: Session):
    """Seed fallback legislation if table is empty."""
    import src.database.legislative_models  # noqa
    from src.database.legislative_models import LegislativeAct
    count = db.query(LegislativeAct).count()
    if count == 0:
        logger.info("No legislative data found — seeding fallback legislation...")
        from src.pipelines.scrapers.legislative_scraper import (
            FALLBACK_LEGISLATION, _upsert_act, _generate_external_id,
        )
        from src.engines.legislative_engine import LegislativeImpactEngine
        from src.database.models import Country
        cmap = {c.code: c for c in db.query(Country).filter(Country.is_active == True).all()}
        summary = {"acts_found": 0, "sessions_found": 0, "errors": 0,
                    "countries_covered": [], "sources_used": ["fallback_seed"]}
        for item in FALLBACK_LEGISLATION:
            _upsert_act(db, cmap, {
                **item,
                "external_id": _generate_external_id("fallback", item["iso2"], item["act_number"]),
                "source": "fallback_seed", "source_url": "",
            }, summary)
        engine = LegislativeImpactEngine(db)
        unscored = db.query(LegislativeAct).filter(LegislativeAct.estimated_magnitude == 0.0).all()
        for act in unscored:
            engine.score_and_update_act(act)
            if abs(act.estimated_magnitude) > 5.0:
                engine.emit_news_event(act)
        logger.info("Legislative bootstrap: seeded %d acts, scored %d",
                    summary["acts_found"], len(unscored))
    else:
        logger.info("Legislative data present (%d acts) — skipping bootstrap", count)


def bootstrap_fx_analytics(db: Session):
    """Seed initial FX rates if no data exists."""
    from src.database.fx_models import FxDailyRate
    count = db.query(FxDailyRate).count()
    if count == 0:
        logger.info("No FX rate data found — seeding fallback rates...")
        from src.pipelines.scrapers.fx_scraper import _seed_fallback_rates
        _seed_fallback_rates(db)
        logger.info("FX bootstrap complete: fallback rates seeded")
    else:
        logger.info("FX daily rate data present (%d records) — skipping bootstrap", count)


def bootstrap_corridors(db: Session):
    """Seed trade corridor assessments."""
    from src.engines.corridor_engine import seed_corridors
    seeded = seed_corridors(db)
    if seeded > 0:
        logger.info("Corridor bootstrap complete: %d corridors seeded", seeded)
    else:
        logger.info("Corridor data present — skipping bootstrap")


def bootstrap_data_integrity(db: Session):
    """Seed data source health records."""
    from src.engines.reconciliation_engine import seed_source_health
    seed_source_health(db)


# ── Ordered step lists ────────────────────────────────────────────────────────

# Core steps that always run (no network required)
CORE_STEPS = [
    seed_reference_data,
    seed_trade_data,
    ingest_csv_data,
    seed_stock_markets,
    ingest_bceao,
    seed_transport,
    seed_roads,
]

# External data scrapers (skipped when SKIP_SCRAPERS=True)
SCRAPER_STEPS = [
    bootstrap_worldbank,
    bootstrap_imf,
    bootstrap_commodities,
    bootstrap_ussd,
    bootstrap_acled,
]

# Module bootstraps (always run after core + scrapers)
MODULE_STEPS = [
    bootstrap_ecfa_cbdc,
    bootstrap_tokenization,
    bootstrap_legislative,
    bootstrap_fx_analytics,
    bootstrap_corridors,
    bootstrap_data_integrity,
]


def run_bootstrap(db: Session):
    """Execute all bootstrap steps in order. Each step has independent error handling."""
    # Core steps
    for step in CORE_STEPS:
        try:
            step(db)
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", step.__name__, exc, exc_info=True)

    # Scrapers
    if settings.SKIP_SCRAPERS:
        logger.info("SKIP_SCRAPERS=True — skipping external API scrapers")
        try:
            bootstrap_ussd_providers_only(db)
        except Exception:
            pass
    else:
        for step in SCRAPER_STEPS:
            try:
                step(db)
            except Exception as exc:
                logger.warning("%s failed (non-fatal): %s", step.__name__, exc, exc_info=True)

    # Module bootstraps
    for step in MODULE_STEPS:
        try:
            step(db)
        except Exception as exc:
            logger.warning("%s failed (non-fatal): %s", step.__name__, exc, exc_info=True)
