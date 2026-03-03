"""
USSD Integration Models for WASI Backend.

Captures data flowing through USSD channels across West Africa:
  - Mobile money transaction aggregates (Orange Money, MTN MoMo, Moov)
  - Commodity price reports from rural markets
  - Cross-border trade declarations
  - Port clearance notifications
  - Agricultural production surveys

USSD is the dominant data channel in West Africa where smartphone
penetration remains low. Over 70% of financial transactions in ECOWAS
flow through USSD, making it the richest real-time economic signal.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime
from src.database.models import Base


class USSDProvider(Base):
    """
    Mobile network operator providing USSD gateway access.
    Each operator covers specific countries in the ECOWAS zone.
    """
    __tablename__ = "ussd_providers"

    id = Column(Integer, primary_key=True, index=True)
    provider_code = Column(String(20), unique=True, nullable=False, index=True)
    # ORANGE_MONEY | MTN_MOMO | MOOV_MONEY | AIRTEL_MONEY | FREE_MONEY | WAVE
    provider_name = Column(String(100), nullable=False)
    gateway_url = Column(String(500))          # Callback URL for USSD gateway
    api_key_hash = Column(String(255))         # Hashed API key for authentication
    country_codes = Column(String(100))        # Comma-separated ISO-2 codes covered
    ussd_shortcode = Column(String(20))        # e.g. *144# (Orange), *170# (MTN)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sessions = relationship("USSDSession", back_populates="provider")


class USSDSession(Base):
    """
    Individual USSD session record.
    Each dial of *XXX# creates a session with a unique session_id from the MNO.
    Sessions are stateless — each callback contains full menu state.
    """
    __tablename__ = "ussd_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("ussd_providers.id"), nullable=False, index=True)
    phone_hash = Column(String(64), nullable=False, index=True)  # SHA-256 of MSISDN (privacy)
    country_code = Column(String(2), nullable=False, index=True)

    # Session flow
    service_code = Column(String(20), nullable=False)  # e.g. *384*123#
    session_type = Column(String(30), nullable=False)
    # MOBILE_MONEY | COMMODITY_PRICE | TRADE_DECLARATION | PORT_CLEARANCE | MARKET_SURVEY
    menu_level = Column(Integer, default=0)
    user_input = Column(Text)                          # Full input chain: "1*2*500000"
    response_text = Column(Text)                       # Menu text sent back to user

    # Status
    status = Column(String(20), default="active")      # active | completed | timeout | error
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ended_at = Column(DateTime)

    provider = relationship("USSDProvider", back_populates="sessions")


class USSDMobileMoneyFlow(Base):
    """
    Aggregated mobile money transaction volumes per country per day.

    USSD-based mobile money is the lifeblood of West African commerce:
      - Orange Money: CI, SN, ML, GN, BF (dominant in francophone ECOWAS)
      - MTN MoMo: GH, NG, BJ, CI, GN (dominant in anglophone + expanding)
      - Moov Money: BJ, TG, CI, BF, NE
      - Wave: SN, CI, ML, BF (fastest growth, lowest fees)
      - Airtel Money: GH, NG, NE
      - Free Money: SN (Tigo-Free merger)

    Daily aggregation avoids storing individual transactions (privacy + volume).
    """
    __tablename__ = "ussd_mobile_money_flows"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    provider_code = Column(String(20), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Transaction volumes (daily aggregates)
    transaction_count = Column(Integer, default=0)       # Number of transactions
    total_value_local = Column(Numeric(18, 2, asdecimal=False), default=0.0)       # Total value (local currency)
    total_value_usd = Column(Numeric(18, 2, asdecimal=False), default=0.0)         # Total value (USD equivalent)
    avg_transaction_local = Column(Numeric(18, 2, asdecimal=False), default=0.0)   # Avg transaction (local currency)
    avg_transaction_usd = Column(Numeric(18, 2, asdecimal=False), default=0.0)     # Avg transaction (USD)

    # Flow breakdown
    p2p_count = Column(Integer, default=0)               # Person-to-person transfers
    merchant_count = Column(Integer, default=0)           # Merchant payments
    bill_pay_count = Column(Integer, default=0)           # Bill payments (utilities, etc.)
    cash_in_count = Column(Integer, default=0)            # Cash-in (deposit)
    cash_out_count = Column(Integer, default=0)           # Cash-out (withdrawal)
    cross_border_count = Column(Integer, default=0)       # Cross-border remittances

    # Currency
    local_currency = Column(String(5))                   # XOF | NGN | GHS | GNF | GMD | CVE
    fx_rate_usd = Column(Numeric(12, 6, asdecimal=False))                          # 1 USD = X local

    # Data quality
    confidence = Column(Float, default=0.80)
    data_source = Column(String(50), default="ussd_gateway")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "provider_code", "period_date"),)


class USSDCommodityReport(Base):
    """
    Commodity price reports from rural/urban markets via USSD.

    Market agents across ECOWAS dial *XXX# to report local prices for
    key commodities (rice, maize, millet, onions, livestock, etc.).
    This creates a grassroots price index that complements World Bank data.
    """
    __tablename__ = "ussd_commodity_reports"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Market identification
    market_name = Column(String(100), nullable=False)    # e.g. "Dantokpa (Cotonou)"
    market_type = Column(String(30))                     # URBAN | RURAL | BORDER | PORT
    region = Column(String(100))                         # Admin region / state

    # Price data (local currency per kg unless specified)
    commodity_code = Column(String(30), nullable=False, index=True)
    # LOCAL_RICE | IMPORTED_RICE | MAIZE | MILLET | SORGHUM | ONION | TOMATO
    # CATTLE | GOAT | FISH | PALM_OIL | SHEA_BUTTER | CASHEW | COCOA_LOCAL
    commodity_name = Column(String(100), nullable=False)
    unit = Column(String(30), default="local/kg")
    price_local = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    price_usd = Column(Numeric(18, 2, asdecimal=False))
    local_currency = Column(String(5))

    # Comparison
    pct_change_week = Column(Float)                      # Week-over-week %
    pct_change_month = Column(Float)                     # Month-over-month %

    # Reporter
    reporter_phone_hash = Column(String(64))             # SHA-256 MSISDN
    report_count = Column(Integer, default=1)            # # of reports aggregated

    confidence = Column(Float, default=0.65)             # Lower — grassroots data
    data_source = Column(String(50), default="ussd_market_report")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint("country_id", "period_date", "market_name", "commodity_code"),
    )


class USSDTradeDeclaration(Base):
    """
    Informal cross-border trade declarations via USSD.

    Informal trade accounts for 40-60% of real trade in ECOWAS.
    Traders at border crossings dial *XXX# to declare goods, value, and
    destination. This captures the massive informal economy that GDP misses.

    Key corridors: Nigeria–Benin, Ghana–Togo, Senegal–Mali,
                   CI–Burkina, Niger–Nigeria.
    """
    __tablename__ = "ussd_trade_declarations"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Border crossing
    border_post = Column(String(100), nullable=False)    # e.g. "Seme-Krake (NG-BJ)"
    origin_country = Column(String(2), nullable=False)   # ISO-2
    destination_country = Column(String(2), nullable=False)
    direction = Column(String(10), nullable=False)       # EXPORT | IMPORT | TRANSIT

    # Goods
    commodity_category = Column(String(50), nullable=False)
    # FOOD_GRAINS | LIVESTOCK | TEXTILES | ELECTRONICS | FUEL | CONSTRUCTION | VEHICLES | OTHER
    commodity_description = Column(String(200))
    quantity_kg = Column(Float)
    declared_value_local = Column(Numeric(18, 2, asdecimal=False))
    declared_value_usd = Column(Numeric(18, 2, asdecimal=False))
    local_currency = Column(String(5))

    # Transport
    transport_mode = Column(String(20))                  # TRUCK | BUS | MOTORCYCLE | FOOT | BOAT
    vehicle_count = Column(Integer, default=1)

    # Reporter
    trader_phone_hash = Column(String(64))
    declaration_count = Column(Integer, default=1)       # Daily aggregate count

    confidence = Column(Float, default=0.55)             # Low — self-reported informal trade
    data_source = Column(String(50), default="ussd_trade_declaration")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint(
            "country_id", "period_date", "border_post",
            "commodity_category", "direction",
        ),
    )


class USSDPortClearance(Base):
    """
    Port clearance notifications via USSD.

    Customs brokers and freight agents use USSD to report:
      - Container release status
      - Customs delays
      - Port congestion levels
      - Clearance times

    Key ports: Lagos/Apapa (NG), Abidjan (CI), Tema (GH),
               Dakar (SN), Lomé (TG), Cotonou (BJ).
    """
    __tablename__ = "ussd_port_clearances"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Port
    port_name = Column(String(100), nullable=False)      # e.g. "Port Autonome d'Abidjan"
    port_code = Column(String(10))                       # UN/LOCODE

    # Clearance data (daily aggregates)
    containers_cleared = Column(Integer, default=0)
    containers_pending = Column(Integer, default=0)
    avg_clearance_hours = Column(Float)                  # Average time to clear
    max_clearance_hours = Column(Float)                  # Worst case
    congestion_level = Column(String(10))                # LOW | MEDIUM | HIGH | CRITICAL

    # Delays
    customs_delay_hours = Column(Float, default=0.0)
    inspection_delay_hours = Column(Float, default=0.0)
    documentation_delay_hours = Column(Float, default=0.0)

    # Reporter count (how many agents reported today)
    reporter_count = Column(Integer, default=1)

    confidence = Column(Float, default=0.70)
    data_source = Column(String(50), default="ussd_port_report")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date", "port_name"),)


class USSDDailyAggregate(Base):
    """
    Daily country-level USSD aggregate for WASI index enrichment.

    Combines all USSD data sources into a single daily signal per country:
      - Mobile money velocity (transaction growth rate)
      - Market price stability (commodity price volatility)
      - Trade flow intensity (informal trade volume)
      - Port efficiency (clearance speed)

    This becomes a sub-signal that feeds into the WASI index calculation
    with configurable weight (default: 15% of Economic sub-component).
    """
    __tablename__ = "ussd_daily_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Sub-signals (each 0–100)
    mobile_money_score = Column(Float)         # Transaction velocity signal
    commodity_price_score = Column(Float)      # Market stability signal
    informal_trade_score = Column(Float)       # Trade flow intensity
    port_efficiency_score = Column(Float)      # Clearance speed signal

    # Aggregate
    ussd_composite_score = Column(Float)       # Weighted composite (0–100)

    # Metadata
    data_points_count = Column(Integer, default=0)   # Total USSD data points for the day
    providers_reporting = Column(Integer, default=0)  # How many MNOs reported
    confidence = Column(Float, default=0.60)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (UniqueConstraint("country_id", "period_date"),)
