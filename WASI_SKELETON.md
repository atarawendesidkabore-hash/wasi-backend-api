# WASI Backend API — Full Code Skeleton

> West African Shipping & Economic Intelligence Platform
> FastAPI + SQLAlchemy + APScheduler | Python 3.14 | SQLite (dev) / PostgreSQL (prod)
> 215 Python files | 80+ DB models | 100+ API endpoints | 24+ engines

---

## 1. ENTRY POINT & CONFIGURATION

### src/main.py
```
class SecurityHeadersMiddleware(BaseHTTPMiddleware)
    async def dispatch(request, call_next) -> Response

async def lifespan(app: FastAPI)          # init_db → seed → ingest CSV → start scheduler
def root() -> dict                         # GET / → welcome message
def admin_seed() -> dict                   # POST /admin/seed → re-seed DB

# Includes 40+ routers covering /api, /api/v2, /api/v3, /api/v4, /api/public
```

### src/config.py
```
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: list[str]
    SCHEDULER_ENABLED: bool = True
    ANTHROPIC_API_KEY: str | None
    ACLED_API_KEY: str | None
    SKIP_SCRAPERS: bool = False
    LIGHT_STARTUP: bool = False
    FORECAST_ENGINE_VERSION: int = 1
```

### src/bootstrap.py
```
# Orchestrates all startup seeding in order:
CORE_STEPS = [seed_reference_data, seed_trade_data, ingest_csv_data, seed_stock_markets]
SCRAPER_STEPS = [bootstrap_worldbank, bootstrap_imf, bootstrap_commodities, bootstrap_acled]
MODULE_STEPS = [
    bootstrap_ussd, bootstrap_ecfa_cbdc, bootstrap_tokenization,
    bootstrap_legislative, bootstrap_fx_analytics, bootstrap_corridors,
    bootstrap_data_integrity, bootstrap_engagement, bootstrap_royalties,
    bootstrap_etf_catalog
]

def run_bootstrap(db: Session) -> None     # runs all steps with error isolation
def seed_reference_data(db)                # 16 ECOWAS countries
def seed_trade_data(db)                    # bilateral trade estimates
def ingest_csv_data(db)                    # scan data/*.csv → CountryIndex
def seed_stock_markets(db)                 # NGX/GSE/BRVM 2019-2024
def ingest_bceao(db)                       # BCEAO macro data
def seed_transport(db)                     # SITARAIL + airport data
def seed_roads(db)                         # ECOWAS road corridors
def bootstrap_worldbank(db)                # World Bank API if 0 rows
def bootstrap_imf(db)                      # IMF WEO if 0 rows
def bootstrap_commodities(db)              # Pink Sheet if 0 rows
def bootstrap_ussd(db)                     # USSD demo data
def bootstrap_acled(db)                    # ACLED conflict data
def bootstrap_ecfa_cbdc(db)                # eCFA wallets + BCEAO rates
def bootstrap_tokenization(db)             # tokenization demo data
def bootstrap_legislative(db)              # legislation seeds
def bootstrap_fx_analytics(db)             # FX rate seeds
def bootstrap_corridors(db)                # trade corridor seeds
def bootstrap_data_integrity(db)           # data source health
def bootstrap_engagement(db)               # badges + challenges
def bootstrap_royalties(db)                # royalty accounts
def bootstrap_etf_catalog(db)              # 42 ETF products
```

---

## 2. DATABASE LAYER

### src/database/connection.py
```
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db() -> Generator[Session]         # FastAPI dependency
def init_db() -> None                      # create_all + register metadata
```

### src/database/models.py — Core Models (21+)
```
class User(Base):                          # id, username, email, hashed_password, x402_balance, tier, is_active, is_admin
class RefreshToken(Base):                  # token_hash, jti, expires_at, is_revoked
class Country(Base):                       # code, name, tier, weight, is_active
class CountryIndex(Base):                  # country_id, period_date, ship_arrivals, cargo_tonnage, container_teu,
                                           # port_efficiency_score, dwell_time_days, gdp_growth_pct, trade_value_usd,
                                           # shipping_score, trade_score, infrastructure_score, economic_score,
                                           # index_value, confidence, data_quality
class WASIComposite(Base):                 # period_date, composite_value, mom_change, yoy_change, trend_direction,
                                           # std_dev, annualized_volatility, sharpe_ratio, max_drawdown
class X402Tier(Base):                      # tier name, daily limit, cost per query
class X402Transaction(Base):               # user_id, amount, description, timestamp
class QueryLog(Base):                      # user_id, endpoint, cost, timestamp
class WASIProcurementRecord(Base):         # country_id, contract_value, sector, date
class BilateralTrade(Base):                # country_id, partner_code, year, export_value_usd, import_value_usd, trade_balance_usd
class StockMarketData(Base):               # exchange_code, index_name, trade_date, index_value, market_cap_usd, volume_usd, fx_rate_usd
class AirTraffic(Base):                    # country_id, airport_code, period_date, passengers, cargo_tonnes, movements
class RailTraffic(Base):                   # country_id, corridor_name, period_date, freight_tonnes, passengers
class RoadCorridor(Base):                  # country_id, corridor_name, period_date, truck_count, avg_transit_hours, congestion_score
class TransportComposite(Base):            # country_id, period_date, air_score, rail_score, road_score, port_score, composite_score
class DivergenceSnapshot(Base):            # exchange_code, snapshot_date, stock_value, wasi_fundamental, divergence_pct
class NewsEvent(Base):                     # country_id, event_type, headline, magnitude, detected_at
class LiveSignal(Base):                    # country_id, timestamp, base_value, adjustment, signal_value
class GovernmentDocument(Base):            # country_id, doc_type, title, published_date
class BankDossierScore(Base):              # country_id, user_id, wasi_score, trade_score, procurement_score, risk_rating
class MacroIndicator(Base):                # country_id, year, gdp_growth, inflation, debt_gdp, current_account, unemployment
class CommodityPrice(Base):                # commodity_code, period_date, price_usd, mom_change, yoy_change
```

### src/database/ussd_models.py — USSD (7 models)
```
class USSDProvider(Base):                  # name, short_code, country_id, api_endpoint, status
class USSDSession(Base):                   # session_id, phone_hash, provider_id, menu_level, input_text, status
class USSDMobileMoneyFlow(Base):           # country_id, provider_id, report_date, transaction_count, total_value_local,
                                           # p2p_count, merchant_count, bill_pay_count, cross_border_count
class USSDCommodityReport(Base):           # country_id, commodity_code, price_local, market_name, region, reported_at
class USSDTradeDeclaration(Base):          # origin_country, destination_country, product_code, quantity, value_usd
class USSDPortClearance(Base):             # port_code, average_dwell_days, vessel_queue_count, cargo_tonnes_backlog
class USSDDailyAggregate(Base):            # country_id, report_date, money_score, commodity_score, trade_score, port_score
```

### src/database/cbdc_models.py — eCFA CBDC (17 models)
```
class CbdcWallet(Base):                    # wallet_id, user_id, country_id, wallet_type(CENTRAL_BANK|COMMERCIAL_BANK|AGENT|MERCHANT|RETAIL),
                                           # balance_ecfa, available_balance_ecfa, kyc_tier, daily_limit_ecfa, pin_hash, status
class CbdcLedgerEntry(Base):               # entry_id, transaction_id, wallet_id, entry_type(DEBIT|CREDIT), amount_ecfa,
                                           # balance_after_ecfa, tx_type, entry_hash, prev_entry_hash
class CbdcTransaction(Base):               # transaction_id, sender_wallet_id, receiver_wallet_id, amount_ecfa, fee_ecfa,
                                           # tx_type, status(pending|completed|failed|reversed)
class CbdcCompliance(Base):                # transaction_id, rule_triggered, alert_level, aml_score
class CbdcPolicy(Base):                    # policy_type, country_id, spending_restriction_type, expiry_date
class CbdcSettlementBatch(Base):           # batch_id, gross_value_ecfa, net_value_ecfa, settlement_date, status
class CbdcMerchantAccount(Base):           # merchant registration
class CbdcOfflineVoucher(Base):            # offline transaction vouchers for rural areas
class CbdcMonetaryAggregate(Base):         # m0, m1, m2, calculation_date
class CbdcFxRate(Base):                    # base_currency, target_currency, rate, effective_date
class CbdcPolicyRate(Base):                # rate_name, rate_value, effective_date (taux_directeur=3.50%, pret_marginal=5.50%, depot=1.50%)
class CbdcReserveRequirement(Base):        # bank_type, reserve_ratio, effective_date (default 3.0%)
class CbdcStandingFacility(Base):          # facility_type(lending|deposit), bank_wallet_id, amount_ecfa, rate, maturity_date
class CbdcMonetaryPolicyDecision(Base):    # decision_date, committee_vote, rationale, new_rates_json
class CbdcEligibleCollateral(Base):        # collateral_type, issuer, haircut_pct, max_amount_ecfa
class CbdcAuditLog(Base):                  # action, actor_id, details, timestamp
class CbdcAlert(Base):                     # alert_type, severity, wallet_id, details
```

### src/database/cbdc_payment_models.py — Cross-Border Payments (5 models)
```
class CbdcCrossBorderTransaction(Base):    # ECOWAS cross-border settlement
class CbdcInterbankSettlement(Base):       # bilateral netting
class CbdcRemittance(Base):               # diaspora remittance tracking
class CbdcPaymentRouter(Base):            # routing rules per corridor
class CbdcPaymentStatus(Base):            # settlement status tracking
```

### src/database/forecast_models.py
```
class ForecastResult(Base):                # country_id, forecast_horizon, method_name, values_json,
                                           # confidence_band_lower, confidence_band_upper, calculated_at
```

### src/database/forecast_v2_models.py — Adaptive Ensemble (4 models)
```
class ForecastV2Result(Base):              # v2 ensemble with fan charts + regime detection
class BacktestMetric(Base):               # backtesting accuracy per method
class ScenarioForecast(Base):             # scenario analysis (base/bull/bear)
class ModelZoo(Base):                      # registry of forecast models
```

### src/database/tokenization_models.py — Data Tokenization (10 models)
```
class DataToken(Base):                     # issued token record
class DailyActivityDeclaration(Base):      # Pillar 1: Citizen UBDI (payments 50-200 CFA)
class BusinessDataSubmission(Base):        # Pillar 2: Business CITD (tax credits 5-15%)
class TaxCreditLedger(Base):               # tax credit accounting per business
class ContractMilestone(Base):             # Pillar 3: Faso Meabo milestones
class MilestoneVerification(Base):         # citizen verification votes (CITIZEN=1.0, INSPECTOR=3.0, CONTRACTOR=0.5)
class FasoMeaboWorker(Base):               # worker profiles
class WorkerCheckIn(Base):                 # daily worker check-ins
class PaymentDisbursement(Base):           # eCFA wallet or mobile money payment
class TokenizationDailyAggregate(Base):    # daily pillar composites
```

### src/database/valuation_models.py
```
class DcfValuation(Base):                  # fcf_projections, wacc, terminal_growth, enterprise_value
class TransactionComparable(Base):         # transaction multiples (acquisitions, IPOs)
class SectorBenchmark(Base):               # peer benchmarks
```

### src/database/legislative_models.py
```
class LegislativeAct(Base):                # iso2, act_number, title, estimated_magnitude, impact_area, confidence
class LegislativeSession(Base):            # parliament/assembly sessions
class LegislativeImpactScore(Base):        # scored impact on WASI
```

### src/database/fx_models.py
```
class FxDailyRate(Base):                   # base_currency, target_currency, rate, bid, ask, fx_date
class FxVolatility(Base):                  # rolling volatility metrics
```

### src/database/corridor_models.py
```
class TradeCorridorAssessment(Base):        # origin_country, destination_country, avg_transit_days, congestion_score, trade_volume_usd
```

### src/database/alert_models.py
```
class Alert(Base):                         # alert_type, severity, triggered_at, status
class AlertRule(Base):                     # alert rule configuration
class Webhook(Base):                       # webhook subscription
```

### src/database/reconciliation_models.py
```
class DataSourceHealth(Base):              # source_name, last_update, error_count, availability_pct
class ReconciliationLog(Base):             # cross-source validation logs
```

### src/database/world_news_models.py
```
class WorldNewsEvent(Base):                # headline, category, impact_vector, fetched_date
class NewsCategory(Base):                  # news taxonomy
class NewsSentiment(Base):                 # sentiment analysis per event
```

### src/database/engagement_models.py — Gamification (11 models)
```
class Badge(Base):                         # achievement badges
class UserBadge(Base):                     # user achievements
class Reward(Base):                        # point/prize rewards
class UserReward(Base):                    # user reward history
class LeaderboardEntry(Base):              # monthly leaderboards
class DailyChallenge(Base):                # daily challenges
class UserChallenge(Base):                 # user challenge participation
class StreakTracker(Base):                  # activity streaks
class AchievementMilestone(Base):          # milestone tracking
class RewardPool(Base):                    # prize pool management
class EngagementMetric(Base):              # aggregated engagement metrics
```

### src/database/royalty_models.py
```
class RoyaltyAttribution(Base):            # query → endpoint → country attribution
class RoyaltyPayment(Base):               # payment to data providers
class RoyaltyAccount(Base):               # provider account ledger
```

### src/database/microloan_models.py — Microloans (14 models)
```
class MicroLoanProduct(Base):              # productId, tenor_months, rate_pct, max_amount_xof
class MicroLoanApplication(Base):          # applicantId, amount_xof, purpose_code, status
class MicroLoanOffer(Base):                # approved_amount_xof, offered_rate_pct, valid_until
class MicroLoanAgreement(Base):            # signed agreement + amortization
class MicroLoanDisbursement(Base):         # disbursement tranches
class MicroLoanRepayment(Base):            # payment_date, amount_paid_xof, principal_paid, interest_paid
class MicroLoanDefault(Base):              # days_overdue, default_amount_xof, status_action
class MicroLoanGuarantee(Base):            # guarantor_id, guarantee_amount_xof, guarantee_type
class MicroLoanCollateral(Base):           # collateral_type, value_xof, lien_date
class MicroLoanCovenantBreach(Base):       # covenant_text, breach_date, remediation_plan
class MicroLoanRestructure(Base):          # original_tenor, restructured_tenor, new_rate_pct
class MicroLoanInsurance(Base):            # credit insurance policy
class MicroLoanPool(Base):                 # loan pool securitization
class MicroLoanAnalytics(Base):            # aggregated KPIs
```

### src/database/sovereign_models.py
```
class SovereignCreditRating(Base):         # rating_agency, rating_symbol, outlook, assigned_date
class DebtSustainability(Base):            # dsc_ratio, pb_ratio, debt_gdp, assessment_date
class ExternalDebt(Base):                  # creditor_type, maturity_date, interest_rate, principal_amount_usd
class SovereignCDS(Base):                  # spread_bps, bid_ask, quoted_date
class SovereignVeto(Base):                 # country_id, veto_reason, effective_date, approved_endpoints_list
```

### src/database/investment_models.py
```
class EquityHolding(Base):                 # investor_id, country_id, shares, acquisition_price_usd, market_value_usd
class BondHolding(Base):                   # investor_id, issuer_country_id, coupon_pct, maturity_date, face_value_usd
class DerivativePosition(Base):            # derivatives tracking
class InvestmentTransaction(Base):         # buy/sell transactions
```

### src/database/etf_models.py
```
class EtfProduct(Base):                    # ticker, isin, name, asset_class, geography_focus, rebalance_frequency
class EtfNav(Base):                        # nav_date, nav_xof, nav_usd, units_outstanding
class EtfHolding(Base):                    # etf_id, asset_id, weight_pct
```

### src/database/seed.py
```
def seed_countries(db) -> None             # 16 ECOWAS countries: NG(28%), CI(22%), GH(15%), SN(10%), BF(4%), ML(4%), GN(4%), BJ(3%), TG(3%), NE(1%), MR(1%), GW(1%), SL(1%), LR(1%), GM(1%), CV(1%)
def seed_bilateral_trade(db) -> None       # annual trade estimates
def seed_stock_market_data(db) -> None     # NGX/GSE/BRVM 2019-2023
def seed_transport_data(db) -> None        # SITARAIL + airports
def seed_road_data(db) -> None             # ECOWAS road corridors
def seed_wasi_indices(db) -> None          # sample country index data
```

---

## 3. ENGINES (Business Logic)

### src/engines/composite_engine.py
```
class CompositeEngine:
    COUNTRY_WEIGHTS = {NG:0.28, CI:0.22, GH:0.15, SN:0.10, BF:0.04, ML:0.04, GN:0.04, BJ:0.03, TG:0.03, NE:0.01, MR:0.01, GW:0.01, SL:0.01, LR:0.01, GM:0.01, CV:0.01}

    def calculate_composite(db: Session, period_date: date) -> WASIComposite
    def _calculate_volatility(history: list[float]) -> dict
    def _calculate_trend(current: float, history: list[float]) -> dict
```

### src/engines/index_calculation.py
```
# 4 sub-components: Shipping(40%) + Trade(30%) + Infrastructure(20%) + Economic(10%)
def calculate_country_index(ship_arrivals, cargo_tonnage, ...) -> float
```

### src/engines/forecast_engine.py
```
class ForecastEngine:
    WEIGHTS = {"linear": 0.25, "ses": 0.35, "holt": 0.40}

    def _forecast_linear(data: list[float], horizon: int) -> list[float]       # np.polyfit degree 1
    def _forecast_ses(data: list[float], horizon: int, alpha=0.3) -> list       # simple exponential smoothing
    def _forecast_holt(data: list[float], horizon: int, alpha=0.3, beta=0.1)    # double exponential
    def forecast_ensemble(data: list[float], horizon: int) -> dict              # weighted average
    def get_confidence_interval(data, forecast, confidence) -> tuple            # residual_std * sqrt(h)
```

### src/engines/transport_engine.py
```
class TransportEngine:
    COUNTRY_PROFILES = {  # coastal_major_port, coastal_transit_hub, landlocked_rail, landlocked_no_rail, coastal_mining, small_island }

    def calculate_transport_composite(db, country_code, period_date) -> TransportComposite
    def get_country_profile(country_code) -> str
```

### src/engines/bank_engine.py
```
# Rule-based credit scoring:
# WASI(40%) + Trade(20%) + Procurement(15%) - Volatility(15%) - PoliticalRisk(10%)
# Ratings: AAA/AA/A/BBB/BB/B/CCC
# bank_review_required = True always (human-in-the-loop)
# COBOL-compatible output: SCORE_9V2, RATING_X5, MAX_LOAN_15V2
```

### src/engines/cbdc_ledger_engine.py
```
class CbdcLedgerEngine:
    def __init__(self, db: Session)
    def mint(central_bank_wallet_id, amount_ecfa, memo) -> CbdcTransaction
    def burn(central_bank_wallet_id, amount_ecfa, memo) -> CbdcTransaction
    def transfer(sender_wallet_id, receiver_wallet_id, amount_ecfa, tx_type, memo) -> CbdcTransaction
    def _execute_double_entry(tx_id, debit_wallet, credit_wallet, amount, tx_type) -> tuple[CbdcLedgerEntry, CbdcLedgerEntry]
    def _get_wallet(wallet_id, for_update=True) -> CbdcWallet
    def _check_balance_limit(wallet, amount) -> None
    def _check_daily_limit(wallet, amount) -> None
    def _check_sar_threshold(amount) -> bool    # 15M XOF SAR threshold
```

### src/engines/cbdc_monetary_policy_engine.py
```
class CbdcMonetaryPolicyEngine:
    def set_policy_rate(rate_name, rate_value, decision_id) -> CbdcPolicyRate
    def set_reserve_requirement(bank_type, ratio, decision_id) -> CbdcReserveRequirement
    def open_standing_facility(facility_type, bank_wallet_id, amount, rate, maturity_date) -> CbdcStandingFacility
    def calculate_interest(wallet_id, rate, days) -> float
    def assess_eligible_collateral(collateral_type, amount) -> dict   # haircut schedule
```

### src/engines/cbdc_compliance_engine.py
```
class CbdcComplianceEngine:
    ALERT_TYPES = [velocity, structuring, sanctions, pep, cross_border, high_value, dormant]

    def screen_transaction(tx: CbdcTransaction) -> CbdcCompliance
    def compute_aml_score(tx) -> float
    def file_sar(tx_id, reason) -> None
    def check_sanctions_list(wallet_id) -> bool
```

### src/engines/cbdc_settlement_engine.py
```
class CbdcSettlementEngine:
    def create_settlement_batch(transactions: list) -> CbdcSettlementBatch
    def execute_bilateral_netting(batch_id) -> dict
    def calculate_monetary_aggregates(date) -> CbdcMonetaryAggregate   # M0/M1/M2
```

### src/engines/cbdc_fx_engine.py
```
class CbdcFxEngine:
    def get_rate(base, target) -> CbdcFxRate
    def convert(amount, base, target) -> float
```

### src/engines/cbdc_payment_router.py
```
class CbdcPaymentRouter:
    def route_payment(origin_country, dest_country, amount) -> dict   # optimal corridor
    def get_corridor_fees(origin, dest) -> dict
```

### src/engines/cbdc_ussd_engine.py
```
# USSD wallet menus (option 6 under *384*WASI#)
# Balance check, P2P transfer, merchant payment via USSD
```

### src/engines/tokenization_engine.py
```
class TokenizationEngine:
    def submit_activity_declaration(db, phone_hash, country, data) -> DailyActivityDeclaration     # Pillar 1
    def submit_business_data(db, business_id, country, data) -> BusinessDataSubmission             # Pillar 2
    def submit_milestone(db, contract_id, milestone_data) -> ContractMilestone                     # Pillar 3

class CrossValidationEngine:
    def validate_report(db, report_id, voter_hash, vote) -> float   # 3+ reporters → confidence 0.70+

class PaymentDisbursementEngine:
    def disburse(db, recipient_hash, amount_cfa, method) -> PaymentDisbursement   # eCFA first, mobile money fallback
```

### src/engines/risk_engine.py
```
class RiskEngine:
    def political_risk_score(country_code) -> float
    def volatility_adjusted_index(country_code, base_index) -> float
```

### src/engines/valuation_engine.py
```
class ValuationEngine:
    def dcf_valuation(country_code, fcf_projections, wacc, terminal_growth) -> DcfValuation
    def transaction_comparables(country_code) -> list[TransactionComparable]
    def sector_benchmarks(country_code) -> list[SectorBenchmark]
    # WACC = risk_free + beta * equity_premium + country_premium
```

### src/engines/legislative_engine.py
```
class LegislativeImpactEngine:
    def score_and_update_act(act: LegislativeAct) -> float      # regulatory impact 0-10
    def emit_news_event(act) -> NewsEvent | None                 # if magnitude > 5
```

### src/engines/fx_analytics_engine.py
```
class FxAnalyticsEngine:
    def rolling_volatility(pair, window_days) -> float           # 14/30/90 day windows
    def strength_index(currency) -> float                        # RSI/MACD equivalents
    def correlation_matrix(pairs: list) -> dict                  # numpy correlation
```

### src/engines/corridor_engine.py
```
class CorridorEngine:
    def seed_corridors(db) -> None
    def assess_corridor(origin, dest) -> TradeCorridorAssessment
```

### src/engines/divergence_engine.py
```
class DivergenceEngine:
    def detect_divergence(exchange_code, date) -> DivergenceSnapshot
    def flag_overvaluation(divergence_pct, threshold=15.0) -> bool
```

### src/engines/ml_engine.py
```
class MLEngine:
    def anomaly_detection(data) -> list
    def classify(features) -> str
    # Claude AI (Anthropic API) integration point
```

### src/engines/investment_engine.py
```
class InvestmentEngine:
    def portfolio_summary(investor_id) -> dict
    def calculate_returns(holdings) -> dict
    def asset_allocation(investor_id) -> dict
```

### src/engines/etf_engine.py
```
class EtfEngine:
    def seed_etf_catalog(db) -> None                        # 42 WASI ETF products
    def calculate_all_navs(db, nav_date) -> list[EtfNav]
    def rebalance_etf(etf_id) -> dict
```

### src/engines/microloan_engine.py
```
class MicroLoanEngine:
    def evaluate_application(app: MicroLoanApplication) -> MicroLoanOffer
    def price_loan(risk_tier, tenor, amount) -> float                      # rate based on risk
    def generate_amortization(agreement: MicroLoanAgreement) -> list       # payment schedule
    def process_repayment(agreement_id, amount) -> MicroLoanRepayment      # principal/interest split
    def assess_default_risk(agreement_id) -> float
```

### src/engines/sovereign_veto_engine.py
```
class SovereignVetoEngine:
    def check_veto(country_code, endpoint) -> bool
    def enforce_restrictions(country_code, request) -> None
```

### src/engines/intelligence_engine.py
```
class IntelligenceEngine:
    def generate_brief(country_code) -> str                 # Claude API synthesis
    def multi_source_analysis(country_code) -> dict
```

### src/engines/engagement_engine.py
```
class EngagementEngine:
    def award_badge(user_id, badge_id) -> UserBadge
    def track_streak(user_id) -> StreakTracker
    def update_leaderboard(user_id, points) -> LeaderboardEntry
    def generate_daily_challenge() -> DailyChallenge
```

### src/engines/royalty_engine.py
```
class RoyaltyEngine:
    def record_attribution(query_log: QueryLog) -> RoyaltyAttribution
    def calculate_payouts(period) -> list[RoyaltyPayment]
```

### src/engines/reconciliation_engine.py
```
class ReconciliationEngine:
    def check_source_health(source_name) -> DataSourceHealth
    def cross_validate(source_a, source_b, metric) -> ReconciliationLog

def seed_source_health(db) -> None
```

### src/engines/world_news_engine.py
```
class WorldNewsEngine:
    def fetch_news(sources: list) -> list[WorldNewsEvent]
    def analyze_sentiment(event) -> NewsSentiment
    def classify_category(event) -> str
```

### src/engines/ussd_engine.py
```
class USSDMenuEngine:
    # *384*WASI# menu tree: 9 options
    # 1=commodity prices, 2=trade declaration, 3=port report, 4=WASI query, 5=account
    # 6=eCFA wallet, 7=activity declaration (UBDI), 8=business data (CITD), 9=Faso Meabo
    def handle_session(session_id, input_text) -> str   # CON/END prefix protocol

class USSDDataAggregator:
    def aggregate_daily(country_code, date) -> USSDDailyAggregate
```

---

## 4. API ROUTES

### /api — Core (v1)

**src/routes/health.py**
```
GET  /api/health                           # public, no auth
```

**src/routes/auth.py**
```
POST /api/auth/register                    # public — UserRegister → TokenResponse
POST /api/auth/login                       # public — OAuth2PasswordRequestForm → JWT + refresh
POST /api/auth/refresh                     # RefreshRequest → new tokens
POST /api/auth/logout                      # revoke JWT
POST /api/auth/admin/revoke-sessions/{id}  # admin — revoke all user sessions
GET  /api/auth/me                          # auth — current user profile
DELETE /api/auth/me                        # auth — delete account (GDPR)
GET  /api/auth/me/export                   # auth — GDPR data export
```

**src/routes/indices.py**
```
GET  /api/indices/latest                   # free — most recent index per country
GET  /api/indices/history                  # 1 credit — composite history
GET  /api/indices/all                      # 2 credits — all countries all time
```

**src/routes/composite.py**
```
POST /api/composite/calculate              # 5 credits — trigger recalculation
GET  /api/composite/report                 # 3 credits — latest + 12m history + contributions
```

**src/routes/country.py**
```
GET  /api/country/{code}/index             # 1 credit — single country latest
GET  /api/country/{code}/history           # 2 credits — country history
```

**src/routes/payment.py**
```
POST /api/payment/topup                    # auth — top up x402 balance
GET  /api/payment/status                   # auth — balance + transactions
```

**src/routes/analytics.py**
```
# Shipping trends, trade analytics, economic indicators
```

**src/routes/signals.py**
```
# Live signals with news adjustments
```

**src/routes/reports.py**
```
# Government reports, economic briefs
```

**src/routes/wallet.py**
```
# User x402 wallet operations
```

**src/routes/chat.py**
```
# Claude AI economic Q&A integration
```

**src/routes/trade.py**
```
# Bilateral trade flows and analysis
```

**src/routes/markets.py**
```
# Stock market data (NGX/GSE/BRVM)
```

**src/routes/v1_guardrails.py**
```
# G1-G4 ML guardrail status endpoints
```

### /api/v2 — Extended

**src/routes/transport.py**
```
GET  /api/v2/transport/latest/{cc}         # multi-modal transport composite
GET  /api/v2/transport/history/{cc}        # transport history
GET  /api/v2/transport/composite           # all countries transport
POST /api/v2/transport/calculate           # trigger recalculation
```

**src/routes/bank.py**
```
GET  /api/v2/bank/credit-context           # pre-credit analysis
POST /api/v2/bank/loan-advisory            # loan structuring
POST /api/v2/bank/score-dossier            # 10 credits — COBOL-compatible credit scoring
```

**src/routes/live_signals.py**
```
GET  /api/v2/signals/live                  # current live signals
GET  /api/v2/signals/events                # active news events
GET  /api/v2/signals/sweep                 # news sweep status
GET  /api/v2/signals/{cc}/live             # country-specific signal
```

**src/routes/data_admin.py**
```
GET  /api/v2/data/status                   # enriched data pipeline status
POST /api/v2/data/worldbank/refresh        # 20 credits — trigger World Bank scraper
POST /api/v2/data/imf/refresh              # 10 credits — trigger IMF scraper
POST /api/v2/data/acled/refresh            # 5 credits — trigger ACLED scraper
POST /api/v2/data/comtrade/refresh         # 10 credits — trigger UN Comtrade scraper
POST /api/v2/data/commodities/refresh      # 5 credits — trigger commodity scraper
GET  /api/v2/data/commodities/latest       # 1 credit — latest commodity prices
GET  /api/v2/data/macro/{country_code}     # 1 credit — macro indicators
```

**src/routes/ussd.py**
```
POST /api/v2/ussd/session                  # initiate USSD session
POST /api/v2/ussd/callback                 # menu callback (CON/END protocol)
GET  /api/v2/ussd/sessions/{session_id}    # session status
GET  /api/v2/ussd/providers                # active MNO providers
# + 8 more endpoints for commodity, trade, port reports
```

**src/routes/data_truth_routes.py**
```
# G5/G6/G7 data provenance routes
```

### /api/v3 — Financial Services

**src/routes/cbdc_wallet.py**
```
POST /api/v3/cbdc/wallet/create            # create eCFA wallet
GET  /api/v3/cbdc/wallet/{wallet_id}       # wallet details
POST /api/v3/cbdc/wallet/{id}/set-pin      # set USSD PIN
GET  /api/v3/cbdc/wallet/{id}/transactions # transaction history
POST /api/v3/cbdc/wallet/{id}/freeze       # freeze account
# + 1 more endpoint
```

**src/routes/cbdc_transaction.py**
```
POST /api/v3/cbdc/transaction/transfer          # P2P transfer
POST /api/v3/cbdc/transaction/merchant-payment  # merchant payment
GET  /api/v3/cbdc/transaction/{transaction_id}  # transaction status
# + 5 more endpoints (settlement, reversals, cross-border)
```

**src/routes/cbdc_admin.py**
```
POST /api/v3/cbdc/admin/mint               # admin — create eCFA
POST /api/v3/cbdc/admin/burn               # admin — destroy eCFA
GET  /api/v3/cbdc/admin/monetary-aggregates # admin — M0/M1/M2
# + 8 more endpoints (wallets, audit, compliance)
```

**src/routes/cbdc_monetary_policy.py**
```
POST /api/v3/cbdc/monetary-policy/policy-rate          # set taux directeur
POST /api/v3/cbdc/monetary-policy/reserve-requirement  # set reserves
POST /api/v3/cbdc/monetary-policy/standing-facility    # open facility
GET  /api/v3/cbdc/monetary-policy/aggregate            # monetary aggregates
# + 12 more endpoints (decisions, collateral, audit)
```

**src/routes/cbdc_payments.py**
```
# Cross-border ECOWAS payment routing
```

**src/routes/forecast.py**
```
GET  /api/v3/forecast/composite            # 5 credits — WASI composite forecast
GET  /api/v3/forecast/commodity/{code}     # 2 credits — commodity forecast (COCOA/BRENT/GOLD/COTTON/COFFEE/IRON_ORE)
GET  /api/v3/forecast/summary              # 10 credits — all-countries dashboard
POST /api/v3/forecast/refresh              # 20 credits — trigger recalculation
GET  /api/v3/forecast/{cc}/index           # 3 credits — country WASI forecast
GET  /api/v3/forecast/{cc}/macro           # 3 credits — GDP/inflation forecast
```

**src/routes/tokenization.py**
```
POST /api/v3/tokenization/activity-declaration    # Pillar 1 (Citizen UBDI)
POST /api/v3/tokenization/business-submission     # Pillar 2 (Business CITD)
POST /api/v3/tokenization/milestone               # Pillar 3 (Faso Meabo)
# + 7 more endpoints (verification, payments, aggregates)
```

**src/routes/risk.py**
```
# Political risk assessment, volatility-adjusted indices
```

**src/routes/legislative.py**
```
GET  /api/v3/legislative/acts                     # all legislation
GET  /api/v3/legislative/{country_code}/acts      # country legislation
POST /api/v3/legislative/assess                   # impact assessment
```

**src/routes/valuation.py**
```
POST /api/v3/valuation/dcf                        # DCF valuation
GET  /api/v3/valuation/comparables                # transaction benchmarks
GET  /api/v3/valuation/sector-benchmarks          # peer metrics
```

**src/routes/fx.py**
```
# FX rates, volatility, correlation matrices
```

**src/routes/corridor.py**
```
# Trade corridor assessments
```

**src/routes/alerts.py**
```
# Alert configuration + history
```

**src/routes/reconciliation.py**
```
# Data source health, cross-source validation
```

**src/routes/world_news.py**
```
# Global news intelligence
```

**src/routes/engagement.py**
```
# Badges, leaderboards, daily challenges, streaks
```

**src/routes/royalty.py**
```
# Data provider revenue attribution
```

**src/routes/intelligence.py**
```
# Claude-powered country briefings
```

**src/routes/microloan.py**
```
POST /api/v3/microloans/apply                     # loan application
GET  /api/v3/microloans/offers/{application_id}   # underwritten offers
POST /api/v3/microloans/sign/{offer_id}           # sign agreement
POST /api/v3/microloans/disburse                  # fund disbursement
POST /api/v3/microloans/repay                     # repayment
# + 9 more endpoints (default, restructuring, guarantees, analytics)
```

**src/routes/sovereign.py**
```
# Credit ratings, DSA, external debt, CDS spreads, country vetoes
```

**src/routes/investment.py**
```
# Portfolio equity/bond holdings, transactions
```

**src/routes/etf.py**
```
GET  /api/v3/etf/catalog                          # 42 WASI ETF products
GET  /api/v3/etf/nav/all                          # all NAVs
GET  /api/v3/etf/{ticker}                         # product details + holdings
# + 6 more endpoints (performance, allocation)
```

### /api/v4 — Advanced Analytics

**src/routes/forecast_v4.py**
```
# Adaptive ensemble, backtesting, scenario analysis
# Fan charts, regime detection, multivariate adjustments
```

### /api/public — Free Tier

**src/routes/public_terminal.py**
```
# Free-tier terminal access (limited endpoints, no auth)
```

---

## 5. SCHEMAS (Pydantic Models)

### src/schemas/auth.py
```
class UserRegister(BaseModel):             # username, email, password
class TokenResponse(BaseModel):            # access_token, token_type
class TokenResponseWithRefresh(BaseModel): # + refresh_token
class RefreshRequest(BaseModel):           # refresh_token
class LogoutRequest(BaseModel):            # access_token
class UserResponse(BaseModel):             # id, username, email, tier, balance, is_admin
class DeleteAccountRequest(BaseModel):     # password confirmation
```

### src/schemas/index.py
```
class CountryIndexResponse(BaseModel):     # country_code, period_date, index_value, confidence, sub_scores
class AllIndicesResponse(BaseModel):        # list of CountryIndexResponse
```

### src/schemas/composite.py
```
class CompositeResponse(BaseModel):        # composite_value, mom_change, yoy_change, trend, volatility
class CompositeReport(BaseModel):          # composite + 12m history + country contributions
```

### src/schemas/payment.py
```
# TopupRequest, PaymentStatusResponse
```

### src/schemas/forecast.py
```
class ForecastPeriod(BaseModel):           # date, value, lower_bound, upper_bound
class ForecastResponse(BaseModel):         # method, horizon, periods: list[ForecastPeriod], confidence
class CommodityForecast(BaseModel):        # commodity_code, current_price, forecast_periods
```

### src/schemas/forecast_v2.py
```
class FanChartBand(BaseModel):             # percentile, values
class RegimeInfo(BaseModel):               # regime_type, probability, characteristics
class ForecastV4Period(BaseModel):         # date, value, fan_chart, regime
class ForecastV4Response(BaseModel):       # ensemble forecast with v4 features
class ScenarioRequest(BaseModel):          # scenario_type(base|bull|bear), assumptions
class ScenarioResponse(BaseModel):         # scenario results
class BacktestResponse(BaseModel):         # accuracy metrics per method
class ModelZooEntry(BaseModel):            # model registry entry
```

### src/schemas/cbdc_wallet.py
```
# WalletCreateRequest, WalletResponse, SetPinRequest, TransactionHistoryResponse
```

### src/schemas/cbdc_transaction.py
```
# TransferRequest, MerchantPaymentRequest, TransactionResponse
```

### src/schemas/cbdc_admin.py
```
# MintRequest, BurnRequest, AuditLogResponse, MonetaryAggregateResponse
```

### src/schemas/cbdc_monetary_policy.py
```
# PolicyRateRequest, ReserveRequirementRequest, StandingFacilityRequest, DecisionResponse
```

### src/schemas/cbdc_payments.py
```
# CrossBorderPaymentRequest, RemittanceRequest, PaymentStatusResponse
```

### src/schemas/ussd.py
```
# USSDSessionRequest, USSDCallbackRequest, USSDResponse (CON/END prefix)
# CommodityReportRequest, TradeDeclarationRequest, PortClearanceRequest
```

### src/schemas/tokenization.py
```
# ActivityDeclarationRequest, BusinessSubmissionRequest, MilestoneRequest
# VerificationVoteRequest, PaymentDisbursementResponse, AggregateResponse
```

### src/schemas/alert.py
```
# AlertRuleCreate, AlertResponse, WebhookCreate
```

### src/schemas/corridor.py
```
# CorridorAssessmentResponse
```

### src/schemas/risk.py
```
# PoliticalRiskResponse, VolatilityResponse
```

### src/schemas/legislative.py
```
# LegislativeActResponse, ImpactAssessmentRequest, ImpactScoreResponse
```

### src/schemas/valuation.py
```
# DcfRequest, DcfResponse, ComparableResponse, BenchmarkResponse
```

### src/schemas/fx.py
```
# FxRateResponse, VolatilityResponse, CorrelationMatrixResponse
```

### src/schemas/investment.py
```
# EquityHoldingResponse, BondHoldingResponse, TransactionRequest
```

### src/schemas/etf.py
```
# EtfProductResponse, EtfNavResponse, EtfHoldingResponse
```

---

## 6. TASKS & SCHEDULERS

### src/tasks/composite_update.py
```
def start_scheduler() -> None              # Initialize APScheduler
def stop_scheduler() -> None               # Shutdown
def update_composite_index() -> None       # CronTrigger(hour="*/6") — 00:00, 06:00, 12:00, 18:00 UTC
```

### src/tasks/wasi_data_scheduler.py
```
# Daily data pipeline orchestration at 02:00 UTC
# Runs all scrapers in sequence with error isolation
```

### src/tasks/data_ingestion.py
```
def ingest_all_csv_files(db) -> int        # scan data/*.csv → CountryIndex
def ingest_bceao_data(db) -> int           # enrich WAEMU with BCEAO data
```

### src/tasks/news_sweep.py
```
# RSS feed parser, keyword detection, +/-25 adjustment cap
# Runs hourly alongside 6h composite update
```

### src/tasks/forecast_task.py
```
def recalculate_all_forecasts(db) -> None  # CronTrigger(hour=4, minute=0) — daily 04:00 UTC
```

### src/tasks/forecast_v2_task.py
```
# Adaptive ensemble v2 recalculation
```

### src/tasks/ussd_aggregation.py
```
def run_ussd_aggregation(db) -> None       # every 4h
def seed_ussd_demo_data(db) -> None        # 380 demo records (30 days)
```

### src/tasks/ussd_real_scrapers.py
```
def run_wfp_food_price_scraper(db) -> None
def run_bceao_mobile_money_scraper(db) -> None
def run_port_throughput_scraper(db) -> None
def run_ecowas_trade_scraper(db) -> None
def seed_ussd_providers(db) -> None
```

### src/tasks/tokenization_aggregation.py
```
def run_tokenization_aggregation(db) -> None   # every 4h
def run_tokenization_payments(db) -> None      # daily 20:00 UTC
def seed_tokenization_demo_data(db) -> None
```

### src/tasks/cbdc_monetary_policy_task.py
```
def apply_daily_interest(db) -> None           # daily 00:05 UTC
def update_reserve_requirements(db) -> None    # daily 06:00 UTC
def check_facility_maturity(db) -> None        # hourly
def apply_monthly_audit(db) -> None            # monthly
```

### src/tasks/cbdc_settlement_task.py
```
def run_settlement_batch(db) -> None           # end-of-day batch
def calculate_monetary_aggregates(db) -> None  # M0/M1/M2
```

### src/tasks/cbdc_compliance_task.py
```
def run_compliance_screening(db) -> None       # hourly AML/CFT
```

### src/tasks/engagement_task.py
```
def seed_engagement_demo_data(db) -> None
def generate_daily_challenge(db) -> None
def process_streak_updates(db) -> None
```

### src/tasks/legislative_sweep.py
```
def run_legislative_sweep(db) -> None          # daily 02:00 UTC
```

### src/tasks/fx_analytics_task.py
```
def run_fx_analytics_update(db) -> None        # daily volatility + correlation
```

### src/tasks/divergence_snapshot.py
```
def run_divergence_snapshot(db) -> None         # daily after market close
```

### src/tasks/corridor_assessment.py
```
def run_corridor_assessment(db) -> None        # weekly
```

### src/tasks/reconciliation_task.py
```
def run_reconciliation(db) -> None             # daily source health check
```

### src/tasks/fx_rate_update.py
```
def run_fx_rate_update(db) -> None             # daily FX rate fetch
```

### src/tasks/bceao_ingestion.py
```
# BCEAO-specific data ingestion
```

---

## 7. SCRAPERS & PIPELINES

### src/pipelines/scrapers/base_scraper.py
```
class BaseScraper:
    def run(db: Session) -> int            # abstract — returns rows inserted
    def fetch(url: str) -> dict            # HTTP GET with retry
```

### Real Data Scrapers (11+)

| File | Target | Table | Auth | Frequency |
|------|--------|-------|------|-----------|
| worldbank_scraper.py | World Bank Open Data API | CountryIndex | none | startup + nightly |
| imf_scraper.py | IMF WEO DataMapper | MacroIndicator | none | startup + nightly |
| commodity_scraper.py | WB Pink Sheet | CommodityPrice | none | startup + nightly |
| comtrade_scraper.py | UN Comtrade | BilateralTrade | none (free tier) | startup + nightly |
| acled_scraper.py | ACLED Conflict Data | NewsEvent | ACLED_API_KEY (optional) | startup + nightly |
| ngx_scraper.py | Nigerian Exchange | StockMarketData | none | startup |
| gse_scraper.py | Ghana Stock Exchange | StockMarketData | none | startup |
| brvm_scraper.py | BRVM (UEMOA) | StockMarketData | none | startup |
| bceao_scraper.py | BCEAO Central Bank | MacroIndicator | none | startup |
| fx_scraper.py | FX rates | FxDailyRate | none | daily |
| legislative_scraper.py | Gov legislation | LegislativeAct | none | daily |
| world_news_sweep.py | RSS/News APIs | WorldNewsEvent | none | hourly |

### Country-Specific Scrapers
```
ng_scraper.py      # Nigeria-specific enrichment
ci_scraper.py      # Cote d'Ivoire
gh_scraper.py      # Ghana
sn_scraper.py      # Senegal
bf_scraper.py      # Burkina Faso
secondary_scraper.py  # Secondary tier countries
```

### Parsers
```
src/pipelines/parsers/bf_parser.py         # Burkina Faso data parsing
src/pipelines/parsers/bceao_parser.py      # BCEAO data parsing
```

---

## 8. UTILITIES & MIDDLEWARE

### src/utils/security.py
```
pwd_context = CryptContext(schemes=["bcrypt"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(password: str) -> str
def verify_password(plain: str, hashed: str) -> bool
def create_access_token(data: dict, expires_delta: timedelta) -> str         # PyJWT
def decode_access_token(token: str) -> dict
def create_refresh_token(user_id: int) -> tuple[str, str, str]              # token, hash, jti
def hash_refresh_token(token: str) -> str
def blacklist_jti(jti: str) -> None
def is_jti_blacklisted(jti: str) -> bool
def get_current_user(token, db) -> User                                      # FastAPI dependency
def require_admin(user: User) -> User                                        # admin check
def require_cbdc_role(role: str) -> Callable                                 # CBDC role check
```

### src/utils/credits.py
```
def deduct_credits(db, user: User, cost: float, endpoint: str) -> None      # atomic deduction + royalty attribution
def _extract_country_from_endpoint(endpoint: str) -> str | None
def _log_query(db, user_id, endpoint, cost) -> None
```

### src/utils/ml_guardrails.py
```
class MLGuardrails:
    def G1_data_quality_gate(confidence: float) -> dict     # reject < 0.30, warn < 0.60
    def G2_feature_attribution(sub_scores: dict) -> dict    # weighted contributions
    def G3_platt_scaling(raw_score: float, confidence: float, k=8.0) -> float   # calibration
    def G4_human_in_the_loop(context: dict) -> dict         # flag bank, low confidence, >20pt MoM
```

### src/utils/cbdc_crypto.py
```
def generate_wallet_id(country: str, wallet_type: str) -> str
def generate_transaction_id() -> str
def generate_nonce() -> str
def compute_entry_hash(entry_data: dict, prev_hash: str) -> str    # SHA-256 chain
def verify_pin(plain_pin: str, hashed_pin: str) -> bool
def build_canonical_tx_data(tx: dict) -> str
```

### src/utils/cbdc_audit.py
```
def log_mint(db, actor_id, amount, wallet_id) -> CbdcAuditLog
def log_burn(db, actor_id, amount, wallet_id) -> CbdcAuditLog
def log_wallet_frozen(db, actor_id, wallet_id, reason) -> CbdcAuditLog
def log_wallet_unfrozen(db, actor_id, wallet_id) -> CbdcAuditLog
```

### src/utils/cbdc_cobol.py
```
def format_cobol_numeric(value: float, spec: str) -> str    # e.g., SCORE_9V2 → "08550"
def parse_cobol_field(raw: str, spec: str) -> float
```

### src/utils/periods.py
```
def parse_quarter(label: str) -> tuple[date, date]          # "Q1-2026" → (2026-01-01, 2026-03-31)
def quarter_label(dt: date) -> str
def fiscal_year(dt: date) -> int
def iso_week(dt: date) -> int
def iso_year_week(dt: date) -> str
```

### src/utils/pagination.py
```
class PaginationParams(BaseModel):         # offset, limit, sort_by, sort_order
def paginate(query, params: PaginationParams) -> tuple[list, int]
```

### src/utils/phone_hash.py
```
def hash_phone(phone: str, salt: str) -> str    # HMAC-SHA256
```

### src/utils/logging_config.py
```
def setup_logging() -> None
```

### src/middleware/x402_payment_verification.py
```
class RequestLoggingMiddleware:             # logs all API requests to QueryLog
```

### src/middleware/request_id.py
```
class RequestIdMiddleware:                 # adds X-Request-ID header
```

### src/middleware/error_handler.py
```
class GlobalErrorHandlerMiddleware:        # catches all exceptions → JSON error response
```

---

## 9. TESTS

| Test File | Coverage | Tests |
|-----------|----------|-------|
| tests/test_api.py | Core API endpoints | 29 |
| tests/test_auth_tokens.py | JWT + refresh tokens | ~15 |
| tests/test_bank.py | Bank credit scoring | ~10 |
| tests/test_cbdc.py | eCFA wallet operations | ~20 |
| tests/test_cbdc_monetary_policy.py | Monetary policy | ~15 |
| tests/test_corridor.py | Trade corridors | ~8 |
| tests/test_forecast.py | Forecast engine | ~12 |
| tests/test_forecast_engine.py | Forecast validation | ~10 |
| tests/test_periods.py | Period parsing | ~8 |
| tests/test_valuation.py | DCF valuation | ~10 |
| tests/test_fx_analytics.py | FX analytics | ~10 |
| tests/test_world_news.py | World news parsing | 25 |
| tests/test_wasi_pay.py | x402 payment system | ~10 |
| tests/test_data_admin.py | Data admin routes | ~10 |
| tests/live_monetary_policy_test.py | Live BCEAO rates | ~5 |

**Total: 460+ passing tests**

Testing pattern (in-memory SQLite):
```python
from sqlalchemy.pool import StaticPool
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
```

---

## 10. INFRASTRUCTURE

### requirements.txt
```
fastapi==0.115.0, uvicorn==0.30.6, gunicorn==23.0.0
sqlalchemy==2.0.35, psycopg2-binary==2.9.11, alembic>=1.13.0
pydantic>=2.10.0, pydantic-settings>=2.5.2
PyJWT==2.9.0, passlib[bcrypt]==1.7.4, cryptography>=42.0.0
pandas>=2.2.3, numpy>=2.1.2
APScheduler>=3.10.4, httpx==0.27.2, requests>=2.31.0
feedparser>=6.0.10, slowapi, limits, aiofiles, email-validator
```

### Dockerfile
```
FROM python:3.14-slim
# libpq-dev for PostgreSQL
# gunicorn + uvicorn workers
# Health: GET /api/health (30s interval)
CMD: alembic upgrade head && gunicorn src.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker
```

### docker-compose.yml
```
services:
  db: postgres:16-alpine (port 5432)
  api: FastAPI (port 8000, depends_on db)
volumes: pgdata, ./data
```

### render.yaml
```
# Render.com: managed PostgreSQL + Python web service
# Python 3.12.8, LIGHT_STARTUP=true, SKIP_SCRAPERS=true
```

### Data Files
```
data/sample_abidjan_port_2019_2024.csv     # 72 rows, Abidjan port operations
data/sample_bceao_uemoa_2019_2024.csv      # 72 rows, BCEAO macro data
```

---

## ARCHITECTURE FLOW

```
Client Request
    │
    ▼
FastAPI App (src/main.py)
    │
    ├── Middleware: RequestId → ErrorHandler → RequestLogging → SecurityHeaders
    │
    ├── Auth: PyJWT + OAuth2 (src/utils/security.py)
    │
    ├── Credits: x402 deduction (src/utils/credits.py)
    │
    ├── Routes (src/routes/*.py) ──► Engines (src/engines/*.py) ──► Database (src/database/*.py)
    │                                      │
    │                                      ├── ML Guardrails (G1-G4)
    │                                      ├── Platt Scaling calibration
    │                                      └── Human-in-the-loop flags
    │
    ├── Schedulers (src/tasks/*.py)
    │   ├── Composite update: every 6h
    │   ├── News sweep: hourly
    │   ├── Forecast recalc: daily 04:00
    │   ├── USSD aggregation: every 4h
    │   ├── CBDC interest: daily 00:05
    │   ├── Legislative sweep: daily 02:00
    │   ├── FX analytics: daily
    │   ├── Compliance screening: hourly
    │   └── Settlement batch: end-of-day
    │
    └── Scrapers (src/pipelines/scrapers/*.py)
        ├── World Bank, IMF, ACLED, Comtrade, Commodities
        ├── NGX, GSE, BRVM stock exchanges
        ├── BCEAO central bank
        └── FX rates, legislation, world news

Database: SQLite (dev) ←→ PostgreSQL (prod)
    └── 80+ tables across 22 model files
    └── Alembic migrations
```

---

## WASI COUNTRY WEIGHTS (v3.0 ECOWAS)

| Tier | Countries | Weight |
|------|-----------|--------|
| Primary (75%) | NG 28%, CI 22%, GH 15%, SN 10% | 75% |
| Secondary (20%) | BF 4%, ML 4%, GN 4%, BJ 3%, TG 3% | 18%* |
| Tertiary (5%) | NE 1%, MR 1%, GW 1%, SL 1%, LR 1%, GM 1%, CV 1% | 7%* |

*Weights sum to 100% (1.0) across all 16 countries.

---

## API VERSION REGISTRY

| Version | Prefix | Scope |
|---------|--------|-------|
| v1 | /api | Core: auth, health, indices, composite, payments, analytics |
| v2 | /api/v2 | Extended: transport, bank, data admin, USSD, live signals |
| v3 | /api/v3 | Financial: CBDC, tokenization, forecast, legislative, valuation, FX, corridors, microloans, sovereign, ETF, engagement, intelligence |
| v4 | /api/v4 | Advanced: adaptive ensemble forecasting, backtesting, scenarios |
| public | /api/public | Free-tier terminal (no auth) |
