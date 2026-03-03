from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    x402_balance = Column(Float, default=0.0, nullable=False)
    tier = Column(String(20), default="free", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("X402Transaction", back_populates="user")
    query_logs = relationship("QueryLog", back_populates="user")


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(2), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    tier = Column(String(10), nullable=False)
    weight = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    indices = relationship("CountryIndex", back_populates="country")


class CountryIndex(Base):
    __tablename__ = "country_indices"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Raw inputs
    ship_arrivals = Column(Integer)
    cargo_tonnage = Column(Float)
    container_teu = Column(Float)
    port_efficiency_score = Column(Float)
    dwell_time_days = Column(Float)
    gdp_growth_pct = Column(Float)
    trade_value_usd = Column(Float)

    # Computed sub-scores (0.0 – 100.0)
    shipping_score = Column(Float)
    trade_score = Column(Float)
    infrastructure_score = Column(Float)
    economic_score = Column(Float)
    index_value = Column(Float, nullable=False)

    # Data quality
    confidence = Column(Float, default=1.0)          # 0.0–1.0
    data_quality = Column(String(10), default="high")  # high / medium / low

    data_source = Column(String(50), default="csv_import")
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country", back_populates="indices")

    __table_args__ = (UniqueConstraint("country_id", "period_date"),)


class WASIComposite(Base):
    __tablename__ = "wasi_composites"

    id = Column(Integer, primary_key=True, index=True)
    period_date = Column(Date, nullable=False, unique=True, index=True)
    composite_value = Column(Float, nullable=False)

    # Trend
    mom_change = Column(Float)
    yoy_change = Column(Float)
    trend_direction = Column(String(10), default="flat")

    # Volatility metrics
    std_dev = Column(Float)
    annualized_volatility = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    coefficient_of_variation = Column(Float)

    countries_included = Column(Integer)
    calculation_version = Column(String(10), default="1.0")
    calculated_at = Column(DateTime, default=datetime.utcnow)


class X402Tier(Base):
    __tablename__ = "x402_tiers"

    id = Column(Integer, primary_key=True, index=True)
    tier_name = Column(String(50), unique=True, nullable=False)
    query_cost = Column(Float, nullable=False)
    monthly_limit = Column(Integer, nullable=True)
    description = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class X402Transaction(Base):
    __tablename__ = "x402_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    reference_id = Column(String(100), unique=True, index=True)
    description = Column(String(255))
    status = Column(String(20), default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    query_params = Column(Text)
    credits_used = Column(Float, default=0.0)
    response_status = Column(Integer)
    response_time_ms = Column(Float)
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="query_logs")


class WASIProcurementRecord(Base):
    """
    Government procurement records related to trade/shipping infrastructure.
    Tracks public tender activity as a proxy for economic dynamism.
    """
    __tablename__ = "wasi_procurement_records"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Procurement metrics
    tender_count = Column(Integer, default=0)          # Tenders published
    awarded_count = Column(Integer, default=0)          # Contracts awarded
    total_value_usd = Column(Float, default=0.0)        # Total awarded value (USD)
    avg_contract_usd = Column(Float, default=0.0)       # Average contract size (USD)
    infrastructure_pct = Column(Float, default=0.0)     # % of contracts for trade infrastructure

    # Metadata
    data_source = Column(String(100), default="manual")
    confidence = Column(Float, default=1.0)             # 0.0–1.0 data quality
    data_quality = Column(String(10), default="high")   # high / medium / low
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date"),)


class BilateralTrade(Base):
    """
    Annual bilateral trade flows between a WASI country and an external partner.

    Source: UN Comtrade estimates, World Bank WITS, national statistics offices.
    Values in USD. Export/import from the WASI country's perspective.
    """
    __tablename__ = "bilateral_trade"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    partner_code = Column(String(3), nullable=False, index=True)   # ISO-2 (e.g. "CH")
    partner_name = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False, index=True)

    # Trade flows (WASI country perspective)
    export_value_usd = Column(Float, default=0.0)   # WASI → partner (exports)
    import_value_usd = Column(Float, default=0.0)   # WASI ← partner (imports)
    total_trade_usd  = Column(Float, default=0.0)   # export + import
    trade_balance_usd = Column(Float, default=0.0)  # export - import (+ = surplus)

    # Commodity breakdown (comma-separated or JSON string)
    top_exports = Column(Text, default="")   # main goods exported to partner
    top_imports = Column(Text, default="")   # main goods imported from partner

    data_source = Column(String(100), default="un_comtrade_estimate")
    confidence = Column(Float, default=0.70)         # 0.0–1.0
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "partner_code", "year"),)


class StockMarketData(Base):
    """
    Daily stock market index data for West African exchanges.

    Exchanges covered:
      NGX  — Nigerian Exchange Group        (covers NG, 28% WASI weight)
      GSE  — Ghana Stock Exchange           (covers GH, 15% WASI weight)
      BRVM — Bourse Régionale des Valeurs   (covers CI/SN/BJ/TG, 34% WASI weight)

    Source: Kwayisi free JSON API (NGX/GSE), brvm.org scraper (BRVM).
    """
    __tablename__ = "stock_market_data"

    id = Column(Integer, primary_key=True, index=True)

    # Exchange + index identification
    exchange_code  = Column(String(10), nullable=False, index=True)  # NGX | GSE | BRVM
    index_name     = Column(String(50), nullable=False, index=True)  # e.g. "NGX All-Share"
    country_codes  = Column(String(20), nullable=False)              # comma-sep ISO-2 codes

    # Date (trade_date stored as 1st of month for monthly seeds; daily for live)
    trade_date     = Column(Date, nullable=False, index=True)

    # Price data
    index_value    = Column(Float, nullable=False)
    open_value     = Column(Float)
    high_value     = Column(Float)
    low_value      = Column(Float)

    # Performance
    change_pct     = Column(Float)          # day-over-day or period-over-period %
    ytd_change_pct = Column(Float)          # year-to-date %
    market_cap_usd = Column(Float)          # total market cap in USD
    volume_usd     = Column(Float)          # trading volume in USD

    # T3: Local currency fields — use for divergence to avoid FX distortion
    market_cap_local = Column(Float)        # market cap in local currency
    local_currency   = Column(String(5))    # NGN | GHS | XOF
    fx_rate_usd      = Column(Float)        # 1 USD = X local_currency at snapshot
    fx_rate_date     = Column(Date)         # date of FX rate used

    # Metadata
    data_source    = Column(String(50), default="kwayisi_api")
    confidence     = Column(Float, default=0.85)
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("exchange_code", "index_name", "trade_date"),)


class AirTraffic(Base):
    """
    Monthly air traffic data per country (primary airport).
    Sources: FAAN (NG), AERIA (CI), GACL (GH), AIBD (SN), ASECNA regional.
    """
    __tablename__ = "air_traffic"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    airport_code = Column(String(4), nullable=False)      # IATA 3-letter or ICAO 4-letter
    airport_name = Column(String(100))
    passengers_total = Column(Integer)                    # monthly passengers (intl + domestic)
    cargo_tonnes = Column(Float)                          # air cargo (tonnes)
    aircraft_movements = Column(Integer)                  # total aircraft movements
    on_time_pct = Column(Float)                           # on-time departure %
    avg_delay_minutes = Column(Float)                     # average delay (minutes)

    # Computed sub-score (0–100)
    air_index = Column(Float)

    data_source = Column(String(50), default="asecna_estimate")
    confidence = Column(Float, default=0.75)
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date", "airport_code"),)


class RailTraffic(Base):
    """
    Monthly rail freight/passenger data.
    Primary West African operational line: SITARAIL (Abidjan–Ouagadougou, 1,260 km).
    """
    __tablename__ = "rail_traffic"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    line_name = Column(String(100), nullable=False)       # e.g. "SITARAIL"
    freight_tonnes = Column(Float)                        # monthly freight (tonnes)
    passenger_count = Column(Integer)                     # monthly passengers
    avg_transit_days = Column(Float)                      # average transit time (days)
    on_time_pct = Column(Float)                           # on-time arrival %
    track_km_operational = Column(Float)                  # km of track in service

    # Computed sub-score (0–100)
    rail_index = Column(Float)

    data_source = Column(String(50), default="sitarail_estimate")
    confidence = Column(Float, default=0.70)
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date", "line_name"),)


class RoadCorridor(Base):
    """
    Monthly road corridor performance (cross-border truck flows).
    Key corridors: Abidjan–Bamako, Lagos–Niamey, Dakar–Bamako, Lomé–Ouagadougou.
    """
    __tablename__ = "road_corridors"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    corridor_name = Column(String(100), nullable=False)   # e.g. "ABIDJAN-BAMAKO"
    truck_count = Column(Integer)                         # monthly trucks crossing
    avg_transit_days = Column(Float)                      # average cross-border transit (days)
    border_wait_hours = Column(Float)                     # average border wait (hours)
    road_quality_score = Column(Float)                    # 0–100 pavement/infrastructure score

    # Computed sub-score (0–100)
    road_index = Column(Float)

    data_source = Column(String(50), default="corridor_estimate")
    confidence = Column(Float, default=0.65)
    created_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date", "corridor_name"),)


class TransportComposite(Base):
    """
    Monthly multi-modal transport composite per country.
    Weights vary by country profile (coastal vs landlocked vs island).
    """
    __tablename__ = "transport_composites"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    country_profile = Column(String(30))      # coastal_major_port | landlocked_rail | etc.

    # Component indices (0–100, None if mode not applicable)
    maritime_index = Column(Float)            # from CountryIndex (shipping_score proxy)
    air_index = Column(Float)
    rail_index = Column(Float)
    road_index = Column(Float)

    # Effective weights used (may differ from profile defaults if data missing)
    w_maritime = Column(Float)
    w_air = Column(Float)
    w_rail = Column(Float)
    w_road = Column(Float)

    transport_composite = Column(Float, nullable=False)   # weighted composite (0–100)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date"),)


class DivergenceSnapshot(Base):
    """
    W6: Daily persisted divergence scores — enables trend queries like
    'has NGX been consistently overvalued for 6+ months?'

    Written by the daily scheduler after stock market data is fetched.
    """
    __tablename__ = "divergence_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    exchange_code            = Column(String(10), nullable=False, index=True)
    index_name               = Column(String(50), nullable=False, index=True)
    snapshot_date            = Column(Date, nullable=False, index=True)

    stock_index_value        = Column(Float, nullable=False)
    stock_change_pct         = Column(Float)
    avg_wasi_score           = Column(Float)
    fundamentals_change_pct  = Column(Float)
    divergence_pct           = Column(Float)
    signal                   = Column(String(30), nullable=False)
    liquidity_flag           = Column(Boolean, default=False)
    volume_usd               = Column(Float)

    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("exchange_code", "index_name", "snapshot_date"),)


class NewsEvent(Base):
    """
    Detected news event that may affect a country's shipping/trade index.
    Events expire after a defined lifetime (PORT_DISRUPTION=72h, POLITICAL_RISK=7d,
    COMMODITY_SURGE=14d). Live adjustment capped at ±25 points.
    """
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    event_type = Column(String(30), nullable=False, index=True)
    # PORT_DISRUPTION | POLITICAL_RISK | COMMODITY_SURGE | STRIKE | POLICY_CHANGE

    headline = Column(String(500), nullable=False)
    source_url = Column(String(500))
    source_name = Column(String(100))

    # Impact: negative = bad for shipping, positive = good
    magnitude = Column(Float, nullable=False, default=0.0)   # -25 to +25

    detected_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)

    country = relationship("Country")


class LiveSignal(Base):
    """
    Hourly computed live signal per country.
    base_index = latest official CountryIndex.index_value
    live_adjustment = sum of active NewsEvent magnitudes (capped ±25)
    adjusted_index = base_index + live_adjustment (clamped 0–100)
    """
    __tablename__ = "wasi_live_signals"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    base_index = Column(Float, nullable=False)
    live_adjustment = Column(Float, default=0.0)
    adjusted_index = Column(Float, nullable=False)
    active_event_ids = Column(Text, default="[]")    # JSON list of NewsEvent.id
    computed_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date"),)


class GovernmentDocument(Base):
    """
    Government/regulatory document relevant to trade & shipping.
    Sources: port authority notices, ministry circulars, ECOWAS communiqués.
    """
    __tablename__ = "government_documents"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=True, index=True)

    doc_type = Column(String(50), nullable=False)   # PORT_NOTICE | MINISTRY_CIRCULAR | ECOWAS_COMMUNIQUE
    title = Column(String(500), nullable=False)
    url = Column(String(500))
    published_date = Column(Date)
    keywords_matched = Column(Text, default="[]")   # JSON list of matched keywords
    relevance_score = Column(Float, default=0.0)    # 0.0–1.0
    processed_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")


class BankDossierScore(Base):
    """
    Bank credit dossier scoring result for a country/sector combination.
    Rule-based scoring using WASI indices, trade balance, procurement, volatility.
    Always flagged for human review.
    """
    __tablename__ = "bank_dossier_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False)

    # Input parameters
    sector = Column(String(100), nullable=False)
    loan_amount_usd = Column(Float, nullable=False)
    loan_term_months = Column(Integer, nullable=False)
    collateral_type = Column(String(50))

    # Scoring output
    overall_score = Column(Float, nullable=False)           # 0–100
    risk_rating = Column(String(5), nullable=False)         # AAA / AA / A / BBB / BB / B / CCC
    max_recommended_usd = Column(Float)
    rate_premium_bps = Column(Integer)                      # basis points above base rate

    # Component scores (JSON) — wasi_component, trade_component, procurement_component, volatility_penalty, political_risk
    component_scores = Column(Text, default="{}")

    narrative = Column(Text)                                # human-readable explanation
    bank_review_required = Column(Boolean, default=True)    # always True (human-in-the-loop)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    country = relationship("Country")


class MacroIndicator(Base):
    """
    Macroeconomic indicators per country and year.
    Sources: IMF WEO DataMapper API (primary), World Bank (fallback).
    Used by AI agent for government advisory and bank credit scoring.
    """
    __tablename__ = "macro_indicators"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)

    # IMF WEO indicators
    gdp_growth_pct = Column(Float)            # NGDP_RPCH — Real GDP growth (%)
    inflation_pct = Column(Float)             # PCPIPCH — CPI inflation (%)
    debt_gdp_pct = Column(Float)              # GGXWDG_NGDP — Gross gov't debt (% GDP)
    current_account_gdp_pct = Column(Float)   # BCA_NGDPD — CA balance (% GDP)
    unemployment_pct = Column(Float)          # LUR — Unemployment rate (%)
    gdp_usd_billions = Column(Float)          # NGDPD — Nominal GDP (USD billions)

    data_source = Column(String(50), default="imf_weo")
    is_projection = Column(Boolean, default=False)   # True = IMF estimate/projection
    confidence = Column(Float, default=0.85)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "year", "data_source"),)


class CommodityPrice(Base):
    """
    Global commodity spot prices (World Bank Pink Sheet).
    Covers key commodities affecting WASI country export revenues.
    Prices are world-level (not per-country).
    """
    __tablename__ = "commodity_prices"

    id = Column(Integer, primary_key=True, index=True)
    commodity_code = Column(String(20), nullable=False, index=True)  # COCOA | BRENT | GOLD | COTTON | COFFEE
    commodity_name = Column(String(100), nullable=False)
    unit = Column(String(50))           # USD/mt | USD/bbl | USD/troy oz | USD/kg

    period_date = Column(Date, nullable=False, index=True)   # 1st of month for monthly
    price_usd = Column(Float, nullable=False)

    pct_change_mom = Column(Float)      # month-over-month %
    pct_change_yoy = Column(Float)      # year-over-year %

    data_source = Column(String(50), default="wb_pinksheet")
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("commodity_code", "period_date"),)
