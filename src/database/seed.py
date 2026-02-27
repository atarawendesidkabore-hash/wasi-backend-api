from datetime import date
from sqlalchemy.orm import Session
from src.database.models import Country, X402Tier, BilateralTrade, StockMarketData, AirTraffic, RailTraffic, RoadCorridor
from src.database.stock_seed_data import STOCK_MARKET_SEED

WASI_COUNTRIES = [
    # (code, name, tier, weight)  — v3.0 ECOWAS-focused set
    # Primary (75%)
    ("NG", "Nigeria",           "primary",   0.28),
    ("CI", "Cote d'Ivoire",     "primary",   0.22),
    ("GH", "Ghana",             "primary",   0.15),
    ("SN", "Senegal",           "primary",   0.10),
    # Secondary (20%)
    ("BF", "Burkina Faso",      "secondary", 0.04),
    ("ML", "Mali",              "secondary", 0.04),
    ("GN", "Guinea",            "secondary", 0.04),
    ("BJ", "Benin",             "secondary", 0.03),
    ("TG", "Togo",              "secondary", 0.03),
    # Tertiary (5%)
    ("NE", "Niger",             "tertiary",  0.01),
    ("MR", "Mauritania",        "tertiary",  0.01),
    ("GW", "Guinea-Bissau",     "tertiary",  0.01),
    ("SL", "Sierra Leone",      "tertiary",  0.01),
    ("LR", "Liberia",           "tertiary",  0.01),
    ("GM", "Gambia",            "tertiary",  0.01),
    ("CV", "Cabo Verde",        "tertiary",  0.01),
]

DEFAULT_TIERS = [
    # (tier_name, query_cost, monthly_limit, description)
    ("free",       0.0,  100,  "Free tier — 100 queries/month at no cost"),
    ("pro",        1.0,  None, "Pro tier — unlimited queries at 1 credit each"),
    ("enterprise", 0.5,  None, "Enterprise tier — unlimited queries at 0.5 credits each"),
]


def seed_countries(db: Session) -> None:
    for code, name, tier, weight in WASI_COUNTRIES:
        if not db.query(Country).filter(Country.code == code).first():
            db.add(Country(code=code, name=name, tier=tier, weight=weight))

    for tier_name, cost, limit, desc in DEFAULT_TIERS:
        if not db.query(X402Tier).filter(X402Tier.tier_name == tier_name).first():
            db.add(X402Tier(
                tier_name=tier_name,
                query_cost=cost,
                monthly_limit=limit,
                description=desc,
            ))

    db.commit()


# ── Bilateral trade seed data (2022 annual, USD) ──────────────────────────────
# Source: UN Comtrade estimates + World Bank WITS + national statistics
# Format: (wasi_code, partner_code, partner_name, year,
#           export_usd, import_usd, top_exports, top_imports)

_M = 1_000_000   # million multiplier
_B = 1_000_000_000  # billion multiplier

BILATERAL_TRADE_DATA = [
    # ── Nigeria (NG) ──────────────────────────────────────────────────────────
    ("NG","CN","China",         2022, 1.6*_B, 13.8*_B, "crude oil,LNG,cocoa",    "machinery,electronics,textiles,steel"),
    ("NG","IN","India",         2022, 5.8*_B,  4.1*_B, "crude oil,LNG",          "pharmaceuticals,machinery,textiles"),
    ("NG","US","United States", 2022, 4.2*_B,  5.3*_B, "crude oil,LNG",          "machinery,chemicals,aircraft"),
    ("NG","NL","Netherlands",   2022,10.2*_B,  1.9*_B, "crude oil,LNG,cocoa",    "machinery,chemicals,food products"),
    ("NG","FR","France",        2022, 1.2*_B,  3.6*_B, "crude oil,cocoa",        "aircraft,pharmaceuticals,wine"),
    ("NG","CH","Switzerland",   2022, 0.5*_B,  0.7*_B, "gold,crude oil",         "pharmaceuticals,watches,chemicals"),
    ("NG","DE","Germany",       2022, 0.4*_B,  2.2*_B, "crude oil",              "machinery,vehicles,chemicals"),
    ("NG","GB","United Kingdom",2022, 0.9*_B,  2.8*_B, "crude oil,LNG",          "machinery,vehicles,food"),
    ("NG","AE","UAE",           2022, 1.1*_B,  1.4*_B, "crude oil,gold",         "gold,machinery,food"),
    ("NG","ES","Spain",         2022, 2.3*_B,  0.8*_B, "crude oil",              "vehicles,machinery,food"),

    # ── Côte d'Ivoire (CI) ───────────────────────────────────────────────────
    ("CI","NL","Netherlands",   2022, 3.2*_B,  0.9*_B, "cocoa beans,cocoa butter,coffee","machinery,chemicals,food"),
    ("CI","FR","France",        2022, 1.3*_B,  2.6*_B, "cocoa,coffee,timber",    "machinery,vehicles,pharmaceuticals"),
    ("CI","CH","Switzerland",   2022, 1.5*_B,  0.5*_B, "cocoa,coffee,cashew",    "pharmaceuticals,chemicals,machinery"),
    ("CI","US","United States", 2022, 0.9*_B,  1.3*_B, "cocoa,rubber",           "aircraft,machinery,chemicals"),
    ("CI","CN","China",         2022, 0.6*_B,  3.8*_B, "cocoa,timber,rubber",    "machinery,electronics,textiles"),
    ("CI","DE","Germany",       2022, 1.1*_B,  0.9*_B, "cocoa,coffee",           "machinery,vehicles,chemicals"),
    ("CI","BE","Belgium",       2022, 0.8*_B,  0.6*_B, "cocoa,coffee,cashew",    "machinery,chemicals,food"),
    ("CI","IN","India",         2022, 0.5*_B,  0.8*_B, "cashew,cocoa",           "pharmaceuticals,machinery,textiles"),
    ("CI","ES","Spain",         2022, 0.4*_B,  0.3*_B, "cocoa,rubber",           "food,machinery,chemicals"),
    ("CI","IT","Italy",         2022, 0.5*_B,  0.4*_B, "cocoa,coffee",           "machinery,vehicles,chemicals"),

    # ── Ghana (GH) ───────────────────────────────────────────────────────────
    ("GH","AE","UAE",           2022, 2.5*_B,  0.6*_B, "gold,diamonds",          "gold,machinery,food"),
    ("GH","CN","China",         2022, 0.4*_B,  4.1*_B, "gold,cocoa,timber",      "machinery,electronics,vehicles"),
    ("GH","CH","Switzerland",   2022, 0.8*_B,  0.3*_B, "gold,cocoa",             "pharmaceuticals,chemicals,machinery"),
    ("GH","IN","India",         2022, 0.8*_B,  1.3*_B, "gold,cocoa",             "pharmaceuticals,petroleum,textiles"),
    ("GH","US","United States", 2022, 0.6*_B,  1.0*_B, "gold,cocoa,crude oil",   "machinery,aircraft,chemicals"),
    ("GH","NL","Netherlands",   2022, 0.5*_B,  0.5*_B, "cocoa,timber",           "machinery,chemicals,food"),
    ("GH","FR","France",        2022, 0.2*_B,  0.8*_B, "gold,cocoa",             "aircraft,machinery,vehicles"),
    ("GH","GB","United Kingdom",2022, 0.3*_B,  0.6*_B, "gold,cocoa",             "machinery,vehicles,food"),

    # ── Senegal (SN) ─────────────────────────────────────────────────────────
    ("SN","FR","France",        2022, 0.5*_B,  1.4*_B, "phosphates,fish,peanuts","machinery,vehicles,food,pharmaceuticals"),
    ("SN","CN","China",         2022, 0.1*_B,  1.2*_B, "fish,phosphates",        "machinery,electronics,textiles"),
    ("SN","IN","India",         2022, 0.5*_B,  0.4*_B, "phosphates,fish",        "pharmaceuticals,textiles,machinery"),
    ("SN","CH","Switzerland",   2022, 0.1*_B,  0.1*_B, "phosphates,fish",        "pharmaceuticals,machinery"),
    ("SN","ES","Spain",         2022, 0.2*_B,  0.2*_B, "fish,peanuts",           "food,machinery,chemicals"),
    ("SN","IT","Italy",         2022, 0.1*_B,  0.2*_B, "fish,phosphates",        "machinery,food,chemicals"),
    ("SN","US","United States", 2022, 0.1*_B,  0.4*_B, "phosphates,gold",        "machinery,aircraft,food"),
    ("SN","DE","Germany",       2022, 0.1*_B,  0.3*_B, "fish,phosphates",        "machinery,vehicles,chemicals"),

    # ── Cameroon (CM) ────────────────────────────────────────────────────────
    ("CM","CN","China",         2022, 0.3*_B,  1.8*_B, "crude oil,timber,cocoa", "machinery,electronics,textiles"),
    ("CM","FR","France",        2022, 0.4*_B,  0.9*_B, "crude oil,cocoa,timber", "machinery,vehicles,pharmaceuticals"),
    ("CM","CH","Switzerland",   2022, 0.1*_B,  0.1*_B, "cocoa,coffee",           "pharmaceuticals,chemicals"),
    ("CM","IN","India",         2022, 0.2*_B,  0.3*_B, "crude oil,timber",       "pharmaceuticals,textiles,machinery"),
    ("CM","NL","Netherlands",   2022, 0.3*_B,  0.2*_B, "crude oil,cocoa",        "machinery,chemicals,food"),
    ("CM","BE","Belgium",       2022, 0.1*_B,  0.1*_B, "cocoa,coffee,timber",    "machinery,chemicals"),
    ("CM","DE","Germany",       2022, 0.1*_B,  0.3*_B, "cocoa,timber",           "machinery,vehicles,chemicals"),
    ("CM","US","United States", 2022, 0.1*_B,  0.3*_B, "crude oil,timber",       "machinery,aircraft,food"),

    # ── Angola (AO) ──────────────────────────────────────────────────────────
    ("AO","CN","China",         2022,14.5*_B,  5.2*_B, "crude oil,diamonds",     "machinery,construction,electronics"),
    ("AO","IN","India",         2022, 5.2*_B,  1.0*_B, "crude oil",              "pharmaceuticals,machinery,textiles"),
    ("AO","US","United States", 2022, 3.1*_B,  1.2*_B, "crude oil",              "machinery,aircraft,chemicals"),
    ("AO","FR","France",        2022, 0.8*_B,  0.9*_B, "crude oil,diamonds",     "machinery,vehicles,pharmaceuticals"),
    ("AO","CH","Switzerland",   2022, 0.3*_B,  0.2*_B, "diamonds,crude oil",     "pharmaceuticals,machinery,chemicals"),
    ("AO","NL","Netherlands",   2022, 2.5*_B,  0.5*_B, "crude oil",              "machinery,chemicals,food"),
    ("AO","PT","Portugal",      2022, 0.5*_B,  0.8*_B, "crude oil,diamonds",     "machinery,vehicles,food"),
    ("AO","ZA","South Africa",  2022, 0.4*_B,  0.9*_B, "crude oil",              "food,machinery,vehicles"),

    # ── Tanzania (TZ) ────────────────────────────────────────────────────────
    ("TZ","IN","India",         2022, 0.5*_B,  1.3*_B, "gold,coffee,tobacco",    "pharmaceuticals,machinery,textiles"),
    ("TZ","CN","China",         2022, 0.3*_B,  2.1*_B, "gold,sesame,copper",     "machinery,electronics,textiles"),
    ("TZ","CH","Switzerland",   2022, 0.2*_B,  0.1*_B, "gold,gemstones,coffee",  "pharmaceuticals,machinery"),
    ("TZ","AE","UAE",           2022, 0.6*_B,  0.3*_B, "gold,coffee",            "gold,machinery,food"),
    ("TZ","ZA","South Africa",  2022, 0.2*_B,  0.8*_B, "gold,coffee",            "machinery,vehicles,food"),
    ("TZ","DE","Germany",       2022, 0.1*_B,  0.3*_B, "coffee,tea",             "machinery,vehicles,chemicals"),
    ("TZ","GB","United Kingdom",2022, 0.1*_B,  0.2*_B, "coffee,tea,tobacco",     "machinery,vehicles,food"),
    ("TZ","BE","Belgium",       2022, 0.1*_B,  0.1*_B, "gold,coffee",            "machinery,chemicals"),

    # ── Kenya (KE) ───────────────────────────────────────────────────────────
    ("KE","NL","Netherlands",   2022, 0.5*_B,  0.5*_B, "tea,flowers,coffee",     "machinery,chemicals,food"),
    ("KE","GB","United Kingdom",2022, 0.5*_B,  0.5*_B, "tea,flowers,coffee",     "machinery,vehicles,food"),
    ("KE","US","United States", 2022, 0.3*_B,  0.7*_B, "tea,coffee,flowers",     "machinery,aircraft,chemicals"),
    ("KE","CN","China",         2022, 0.2*_B,  3.5*_B, "tea,coffee",             "machinery,electronics,vehicles"),
    ("KE","CH","Switzerland",   2022, 0.1*_B,  0.2*_B, "tea,flowers,coffee",     "pharmaceuticals,machinery,chemicals"),
    ("KE","IN","India",         2022, 0.3*_B,  1.2*_B, "tea,flowers",            "pharmaceuticals,petroleum,machinery"),
    ("KE","DE","Germany",       2022, 0.1*_B,  0.4*_B, "tea,flowers,coffee",     "machinery,vehicles,chemicals"),
    ("KE","AE","UAE",           2022, 0.4*_B,  0.5*_B, "flowers,tea,gold",       "gold,machinery,food"),

    # ── Morocco (MA) ─────────────────────────────────────────────────────────
    ("MA","FR","France",        2022, 4.0*_B,  6.5*_B, "autos,phosphates,fish,textiles","machinery,vehicles,electronics,food"),
    ("MA","ES","Spain",         2022, 3.5*_B,  4.8*_B, "autos,phosphates,fish",  "machinery,vehicles,food,chemicals"),
    ("MA","CH","Switzerland",   2022, 0.4*_B,  0.6*_B, "phosphates,fish,textiles","pharmaceuticals,machinery,watches"),
    ("MA","CN","China",         2022, 1.0*_B,  5.0*_B, "phosphates,fish",        "machinery,electronics,textiles"),
    ("MA","DE","Germany",       2022, 1.5*_B,  2.8*_B, "autos,phosphates",       "machinery,vehicles,chemicals"),
    ("MA","US","United States", 2022, 0.8*_B,  1.8*_B, "phosphates,fish,textiles","aircraft,machinery,chemicals"),
    ("MA","IN","India",         2022, 1.2*_B,  1.0*_B, "phosphates",             "petroleum,pharmaceuticals,textiles"),
    ("MA","IT","Italy",         2022, 0.8*_B,  1.2*_B, "textiles,phosphates",    "machinery,vehicles,chemicals"),

    # ── Mozambique (MZ) ──────────────────────────────────────────────────────
    ("MZ","CN","China",         2022, 0.5*_B,  1.5*_B, "coal,aluminum,LNG",      "machinery,electronics,textiles"),
    ("MZ","NL","Netherlands",   2022, 1.2*_B,  0.3*_B, "coal,aluminum,gas",      "machinery,chemicals"),
    ("MZ","IN","India",         2022, 0.4*_B,  0.5*_B, "coal,aluminum",          "pharmaceuticals,machinery,petroleum"),
    ("MZ","CH","Switzerland",   2022, 0.1*_B,  0.1*_B, "gems,coal",              "pharmaceuticals,machinery"),
    ("MZ","ZA","South Africa",  2022, 0.5*_B,  1.8*_B, "gas,aluminum,coal",      "food,machinery,vehicles"),
    ("MZ","PT","Portugal",      2022, 0.1*_B,  0.2*_B, "aluminum,fish",          "machinery,food,vehicles"),
    ("MZ","DE","Germany",       2022, 0.1*_B,  0.2*_B, "aluminum,coal",          "machinery,vehicles,chemicals"),
    ("MZ","US","United States", 2022, 0.1*_B,  0.3*_B, "aluminum,coal",          "aircraft,machinery,food"),

    # ── Ethiopia (ET) ────────────────────────────────────────────────────────
    ("ET","CN","China",         2022, 0.3*_B,  4.5*_B, "coffee,sesame,flowers",  "machinery,electronics,vehicles"),
    ("ET","US","United States", 2022, 0.4*_B,  0.8*_B, "coffee,sesame",          "aircraft,machinery,food"),
    ("ET","CH","Switzerland",   2022, 0.2*_B,  0.1*_B, "coffee,flowers",         "pharmaceuticals,machinery"),
    ("ET","NL","Netherlands",   2022, 0.3*_B,  0.2*_B, "coffee,flowers",         "machinery,chemicals,food"),
    ("ET","DE","Germany",       2022, 0.2*_B,  0.4*_B, "coffee,sesame",          "machinery,vehicles,chemicals"),
    ("ET","SA","Saudi Arabia",  2022, 0.1*_B,  0.5*_B, "coffee,sesame",          "petroleum,food,machinery"),
    ("ET","IN","India",         2022, 0.2*_B,  0.8*_B, "coffee,oilseeds",        "pharmaceuticals,textiles,machinery"),
    ("ET","JP","Japan",         2022, 0.1*_B,  0.2*_B, "coffee,flowers",         "machinery,vehicles,electronics"),

    # ── Benin (BJ) — transit hub, cotton, cashew ─────────────────────────────
    ("BJ","CN","China",         2022, 0.1*_B,  0.8*_B, "cotton,cashew,shrimps",  "machinery,electronics,textiles"),
    ("BJ","IN","India",         2022, 0.3*_B,  0.2*_B, "cotton,cashew",          "pharmaceuticals,textiles,machinery"),
    ("BJ","CH","Switzerland",   2022, 0.05*_B, 0.05*_B,"cotton,cashew",          "pharmaceuticals,machinery"),
    ("BJ","FR","France",        2022, 0.1*_B,  0.3*_B, "cotton,cashew",          "machinery,vehicles,food"),
    ("BJ","DE","Germany",       2022, 0.05*_B, 0.1*_B, "cotton,shrimps",         "machinery,chemicals"),
    ("BJ","ES","Spain",         2022, 0.1*_B,  0.1*_B, "cashew,cotton",          "food,machinery"),
    ("BJ","US","United States", 2022, 0.05*_B, 0.1*_B, "cotton,cashew",          "machinery,food"),
    ("BJ","NL","Netherlands",   2022, 0.1*_B,  0.1*_B, "cotton,cashew",          "food,machinery,chemicals"),

    # ── Togo (TG) — Lomé port transit hub, phosphates ─────────────────────────
    ("TG","CN","China",         2022, 0.1*_B,  0.9*_B, "phosphates,cotton,cocoa","machinery,electronics,textiles"),
    ("TG","FR","France",        2022, 0.1*_B,  0.3*_B, "phosphates,cotton",      "machinery,vehicles,food"),
    ("TG","CH","Switzerland",   2022, 0.05*_B, 0.05*_B,"phosphates,cotton",      "pharmaceuticals,machinery"),
    ("TG","IN","India",         2022, 0.1*_B,  0.2*_B, "phosphates,cotton",      "pharmaceuticals,textiles,machinery"),
    ("TG","BE","Belgium",       2022, 0.1*_B,  0.1*_B, "phosphates,cocoa",       "machinery,chemicals"),
    ("TG","DE","Germany",       2022, 0.05*_B, 0.1*_B, "phosphates",             "machinery,chemicals,vehicles"),
    ("TG","NL","Netherlands",   2022, 0.1*_B,  0.1*_B, "phosphates,cocoa",       "food,machinery,chemicals"),
    ("TG","US","United States", 2022, 0.05*_B, 0.1*_B, "phosphates,cotton",      "machinery,food"),

    # ── Guinea (GN) — bauxite, gold, iron ore ────────────────────────────────
    ("GN","CN","China",         2022, 1.5*_B,  1.2*_B, "bauxite,gold,iron ore",  "machinery,electronics,textiles"),
    ("GN","AE","UAE",           2022, 0.5*_B,  0.2*_B, "gold,bauxite",           "gold,food,machinery"),
    ("GN","CH","Switzerland",   2022, 0.2*_B,  0.1*_B, "gold,diamonds",          "pharmaceuticals,machinery"),
    ("GN","IN","India",         2022, 0.3*_B,  0.3*_B, "bauxite,gold",           "pharmaceuticals,textiles,machinery"),
    ("GN","FR","France",        2022, 0.2*_B,  0.4*_B, "bauxite,gold",           "machinery,vehicles,food"),
    ("GN","US","United States", 2022, 0.2*_B,  0.3*_B, "bauxite,gold",           "machinery,food,chemicals"),
    ("GN","ES","Spain",         2022, 0.1*_B,  0.1*_B, "bauxite,fish",           "food,machinery"),
    ("GN","AU","Australia",     2022, 0.2*_B,  0.1*_B, "bauxite,gold",           "machinery,food"),

    # ── Burkina Faso (BF) — landlocked, gold, cotton ─────────────────────────
    # International partners
    ("BF","CH","Switzerland",   2022, 2.8*_B,  0.1*_B, "gold",                   "pharmaceuticals,machinery"),
    ("BF","AE","UAE",           2022, 1.0*_B,  0.2*_B, "gold",                   "gold,food,machinery"),
    ("BF","CN","China",         2022, 0.1*_B,  1.2*_B, "gold,cotton",            "machinery,electronics,textiles"),
    ("BF","FR","France",        2022, 0.1*_B,  0.6*_B, "gold,cotton",            "machinery,vehicles,food"),
    ("BF","IN","India",         2022, 0.1*_B,  0.3*_B, "cotton,gold",            "pharmaceuticals,textiles,machinery"),
    ("BF","DE","Germany",       2022, 0.05*_B, 0.2*_B, "gold,cotton",            "machinery,vehicles,chemicals"),
    ("BF","NL","Netherlands",   2022, 0.1*_B,  0.1*_B, "cotton",                 "food,machinery,chemicals"),
    ("BF","ZA","South Africa",  2022, 0.05*_B, 0.1*_B, "gold",                   "food,machinery"),
    # ECOWAS regional partners (WITS/World Bank 2022 estimates)
    # CI is BF's largest regional partner (Abidjan corridor), GH 2nd (Tema), TG 3rd (Lomé)
    ("BF","CI","Cote d'Ivoire", 2022, 0.18*_B, 0.82*_B,"cotton,livestock",        "fuel,food,manufactured goods"),
    ("BF","GH","Ghana",         2022, 0.12*_B, 0.44*_B,"cotton,livestock,sesame",  "fuel,food,cement,manufactured goods"),
    ("BF","TG","Togo",          2022, 0.10*_B, 0.35*_B,"cotton,livestock,oilseeds","fuel,food,clinker,manufactured goods"),
    ("BF","SN","Senegal",       2022, 0.05*_B, 0.15*_B,"livestock,cotton",         "food,fish,fuel"),
    ("BF","NE","Niger",         2022, 0.08*_B, 0.05*_B,"manufactured goods,food",  "livestock,onions,cowpeas"),
    ("BF","ML","Mali",          2022, 0.06*_B, 0.05*_B,"food,manufactured goods",  "livestock,salt"),

    # ── Mali (ML) — landlocked, gold, cotton ─────────────────────────────────
    ("ML","CH","Switzerland",   2022, 2.5*_B,  0.1*_B, "gold",                   "pharmaceuticals,machinery"),
    ("ML","AE","UAE",           2022, 0.8*_B,  0.3*_B, "gold",                   "gold,food,machinery"),
    ("ML","CN","China",         2022, 0.2*_B,  1.0*_B, "gold,cotton",            "machinery,electronics,textiles"),
    ("ML","FR","France",        2022, 0.1*_B,  0.5*_B, "gold,cotton",            "machinery,vehicles,food"),
    ("ML","IN","India",         2022, 0.1*_B,  0.2*_B, "cotton,gold",            "pharmaceuticals,textiles,machinery"),
    ("ML","SN","Senegal",       2022, 0.2*_B,  0.3*_B, "gold,cotton",            "food,fuel,machinery"),
    ("ML","CI","Cote d'Ivoire", 2022, 0.3*_B,  0.8*_B, "gold,cotton,livestock",  "food,fuel,manufactured goods"),
    ("ML","DE","Germany",       2022, 0.05*_B, 0.2*_B, "gold",                   "machinery,vehicles,chemicals"),

    # ── Niger (NE) — landlocked, uranium, livestock ───────────────────────────
    ("NE","FR","France",        2022, 0.1*_B,  0.4*_B, "uranium,livestock",      "machinery,vehicles,food"),
    ("NE","CN","China",         2022, 0.1*_B,  0.5*_B, "uranium,oil",            "machinery,electronics,textiles"),
    ("NE","NG","Nigeria",       2022, 0.2*_B,  0.4*_B, "livestock,onions",       "fuel,manufactured goods,food"),
    ("NE","IN","India",         2022, 0.05*_B, 0.1*_B, "uranium,livestock",      "pharmaceuticals,textiles"),
    ("NE","CH","Switzerland",   2022, 0.05*_B, 0.05*_B,"uranium",                "pharmaceuticals,machinery"),
    ("NE","DE","Germany",       2022, 0.02*_B, 0.1*_B, "uranium",                "machinery,chemicals"),

    # ── Mauritania (MR) — fish, iron ore, gold ────────────────────────────────
    ("MR","CN","China",         2022, 0.5*_B,  0.8*_B, "iron ore,fish,gold",     "machinery,electronics,textiles"),
    ("MR","ES","Spain",         2022, 0.3*_B,  0.1*_B, "fish,iron ore",          "food,machinery,vehicles"),
    ("MR","FR","France",        2022, 0.1*_B,  0.3*_B, "iron ore,fish",          "machinery,vehicles,food"),
    ("MR","JP","Japan",         2022, 0.1*_B,  0.1*_B, "iron ore,fish",          "machinery,vehicles,electronics"),
    ("MR","IT","Italy",         2022, 0.1*_B,  0.1*_B, "fish",                   "food,machinery,chemicals"),
    ("MR","DE","Germany",       2022, 0.05*_B, 0.1*_B, "iron ore",               "machinery,vehicles,chemicals"),

    # ── Guinea-Bissau (GW) — cashew, fish ────────────────────────────────────
    ("GW","IN","India",         2022, 0.2*_B,  0.05*_B,"cashew nuts",            "pharmaceuticals,textiles,machinery"),
    ("GW","CN","China",         2022, 0.05*_B, 0.1*_B, "fish,cashew",            "machinery,electronics,textiles"),
    ("GW","PT","Portugal",      2022, 0.02*_B, 0.05*_B,"cashew,fish",            "machinery,food,vehicles"),
    ("GW","SN","Senegal",       2022, 0.05*_B, 0.1*_B, "cashew,fish",            "food,fuel,manufactured goods"),
    ("GW","FR","France",        2022, 0.01*_B, 0.03*_B,"cashew",                 "machinery,vehicles,food"),

    # ── Sierra Leone (SL) — diamonds, rutile, iron ore ────────────────────────
    ("SL","CN","China",         2022, 0.2*_B,  0.3*_B, "iron ore,rutile,diamonds","machinery,electronics,textiles"),
    ("SL","BE","Belgium",       2022, 0.1*_B,  0.05*_B,"diamonds",               "machinery,chemicals"),
    ("SL","GB","United Kingdom",2022, 0.05*_B, 0.1*_B, "diamonds,rutile",        "machinery,vehicles,food"),
    ("SL","NL","Netherlands",   2022, 0.05*_B, 0.05*_B,"rutile,diamonds",        "food,machinery,chemicals"),
    ("SL","IN","India",         2022, 0.05*_B, 0.1*_B, "rutile,iron ore",        "pharmaceuticals,textiles,machinery"),

    # ── Liberia (LR) — iron ore, rubber, timber ──────────────────────────────
    ("LR","CN","China",         2022, 0.3*_B,  0.2*_B, "iron ore,rubber",        "machinery,electronics,textiles"),
    ("LR","DE","Germany",       2022, 0.05*_B, 0.1*_B, "rubber,iron ore",        "machinery,chemicals,vehicles"),
    ("LR","CH","Switzerland",   2022, 0.05*_B, 0.05*_B,"iron ore,gold",          "pharmaceuticals,machinery"),
    ("LR","IN","India",         2022, 0.05*_B, 0.1*_B, "rubber,iron ore",        "pharmaceuticals,textiles,machinery"),
    ("LR","US","United States", 2022, 0.05*_B, 0.1*_B, "rubber,iron ore",        "machinery,food,chemicals"),

    # ── Gambia (GM) — peanuts, fish, tourism ─────────────────────────────────
    ("GM","CN","China",         2022, 0.05*_B, 0.15*_B,"peanuts,fish",           "machinery,electronics,textiles"),
    ("GM","IN","India",         2022, 0.05*_B, 0.05*_B,"peanuts,fish",           "pharmaceuticals,textiles"),
    ("GM","SN","Senegal",       2022, 0.05*_B, 0.1*_B, "peanuts,fish",           "food,fuel,manufactured goods"),
    ("GM","GB","United Kingdom",2022, 0.02*_B, 0.05*_B,"peanuts,fish",           "machinery,food,vehicles"),
    ("GM","NL","Netherlands",   2022, 0.02*_B, 0.03*_B,"fish",                   "food,machinery,chemicals"),

    # ── Cabo Verde (CV) — fish, salt, tourism ────────────────────────────────
    ("CV","PT","Portugal",      2022, 0.1*_B,  0.2*_B, "fish,crustaceans",       "food,machinery,vehicles,fuel"),
    ("CV","ES","Spain",         2022, 0.05*_B, 0.1*_B, "fish,salt",              "food,machinery,fuel"),
    ("CV","CN","China",         2022, 0.02*_B, 0.1*_B, "fish",                   "machinery,electronics,textiles"),
    ("CV","NL","Netherlands",   2022, 0.02*_B, 0.05*_B,"fish",                   "food,machinery,chemicals"),
    ("CV","FR","France",        2022, 0.01*_B, 0.05*_B,"fish,crustaceans",       "food,machinery,vehicles"),

    # ── Madagascar (MG) ──────────────────────────────────────────────────────
    ("MG","FR","France",        2022, 0.3*_B,  0.5*_B, "vanilla,cloves,nickel",  "machinery,vehicles,food,pharmaceuticals"),
    ("MG","CN","China",         2022, 0.2*_B,  0.6*_B, "nickel,chrome,seafood",  "machinery,electronics,textiles"),
    ("MG","CH","Switzerland",   2022, 0.05*_B, 0.05*_B,"vanilla,gems",           "pharmaceuticals,machinery"),
    ("MG","US","United States", 2022, 0.1*_B,  0.2*_B, "vanilla,cloves,seafood", "machinery,food,chemicals"),
    ("MG","DE","Germany",       2022, 0.05*_B, 0.1*_B, "vanilla,cloves",         "machinery,vehicles,chemicals"),
    ("MG","IT","Italy",         2022, 0.05*_B, 0.1*_B, "vanilla,seafood",        "machinery,food,chemicals"),
    ("MG","IN","India",         2022, 0.1*_B,  0.2*_B, "vanilla,nickel",         "pharmaceuticals,textiles,machinery"),
    ("MG","JP","Japan",         2022, 0.05*_B, 0.1*_B, "vanilla,seafood",        "machinery,vehicles,electronics"),

    # ── Mauritius (MU) ───────────────────────────────────────────────────────
    ("MU","FR","France",        2022, 0.5*_B,  0.8*_B, "textiles,sugar,fish",    "machinery,vehicles,pharmaceuticals,wine"),
    ("MU","CH","Switzerland",   2022, 0.3*_B,  0.4*_B, "financial services,textiles","pharmaceuticals,watches,machinery"),
    ("MU","GB","United Kingdom",2022, 0.3*_B,  0.5*_B, "textiles,sugar,fish",    "machinery,vehicles,food"),
    ("MU","IN","India",         2022, 0.4*_B,  0.8*_B, "textiles,financial services","petroleum,machinery,textiles"),
    ("MU","CN","China",         2022, 0.1*_B,  1.2*_B, "seafood,textiles",       "machinery,electronics,textiles"),
    ("MU","ZA","South Africa",  2022, 0.2*_B,  0.6*_B, "textiles,sugar",         "food,machinery,vehicles"),
    ("MU","DE","Germany",       2022, 0.1*_B,  0.2*_B, "textiles,sugar",         "machinery,vehicles,chemicals"),
    ("MU","US","United States", 2022, 0.2*_B,  0.3*_B, "textiles,financial services","machinery,aircraft,food"),
]


def seed_bilateral_trade(db: Session) -> int:
    """
    Insert bilateral trade records for all WASI countries.
    Skips records that already exist (idempotent).
    Returns the number of new records inserted.
    """
    inserted = 0
    for row in BILATERAL_TRADE_DATA:
        wasi_code, partner_code, partner_name, year, exp, imp, top_exp, top_imp = row

        country = db.query(Country).filter(Country.code == wasi_code).first()
        if not country:
            continue

        exists = (
            db.query(BilateralTrade)
            .filter(
                BilateralTrade.country_id == country.id,
                BilateralTrade.partner_code == partner_code,
                BilateralTrade.year == year,
            )
            .first()
        )
        if exists:
            continue

        db.add(BilateralTrade(
            country_id=country.id,
            partner_code=partner_code,
            partner_name=partner_name,
            year=year,
            export_value_usd=exp,
            import_value_usd=imp,
            total_trade_usd=exp + imp,
            trade_balance_usd=exp - imp,
            top_exports=top_exp,
            top_imports=top_imp,
        ))
        inserted += 1

    if inserted:
        db.commit()
    return inserted


def seed_stock_market_data(db: Session) -> int:
    """
    Insert historical monthly stock index data for NGX, GSE, BRVM (2019-2023).
    Idempotent — skips rows that already exist.
    Returns number of new rows inserted.
    """
    inserted = 0
    for row in STOCK_MARKET_SEED:
        (exchange_code, index_name, country_codes,
         trade_date_str, index_value, change_pct,
         ytd_change_pct, market_cap_usd, volume_usd) = row

        trade_date = date.fromisoformat(trade_date_str)

        exists = (
            db.query(StockMarketData)
            .filter(
                StockMarketData.exchange_code == exchange_code,
                StockMarketData.index_name == index_name,
                StockMarketData.trade_date == trade_date,
            )
            .first()
        )
        if exists:
            continue

        # T3: approximate historical FX rates per exchange
        _FX = {"NGX": (1500.0, "NGN"), "GSE": (15.5, "GHS"), "BRVM": (600.0, "XOF")}
        fx_rate, local_ccy = _FX.get(exchange_code, (1.0, "USD"))

        db.add(StockMarketData(
            exchange_code=exchange_code,
            index_name=index_name,
            country_codes=country_codes,
            trade_date=trade_date,
            index_value=index_value,
            change_pct=change_pct,
            ytd_change_pct=ytd_change_pct,
            market_cap_usd=market_cap_usd,
            volume_usd=volume_usd,
            market_cap_local=round(market_cap_usd * fx_rate, 0) if market_cap_usd else None,
            local_currency=local_ccy,
            fx_rate_usd=fx_rate,
            fx_rate_date=trade_date,
            data_source="seed_historical",
            confidence=0.85,
        ))
        inserted += 1

    if inserted:
        db.commit()
    return inserted


# ── Transport seed data ────────────────────────────────────────────────────────
# Air traffic: monthly passengers for primary airport (2024 estimate)
# (country_code, airport_code, airport_name, period_date_str, passengers, cargo_t, movements, on_time_pct, air_index)
AIR_TRAFFIC_SEED = [
    # Nigeria — Lagos Murtala Muhammed (FAAN, total domestic+intl ~16.8M/yr = ~1.4M/month)
    ("NG", "LOS", "Lagos Murtala Muhammed", "2024-01-01", 1_420_000, 9_200.0, 8_400, 71.0, 68.0),
    ("NG", "LOS", "Lagos Murtala Muhammed", "2024-02-01", 1_350_000, 8_800.0, 7_900, 69.0, 65.0),
    ("NG", "LOS", "Lagos Murtala Muhammed", "2024-03-01", 1_480_000, 9_500.0, 8_700, 72.0, 70.0),
    # Côte d'Ivoire — Abidjan FHB (AERIA)
    ("CI", "ABJ", "Abidjan Felix Houphouet-Boigny", "2024-01-01", 235_000, 3_800.0, 2_900, 78.0, 74.0),
    ("CI", "ABJ", "Abidjan Felix Houphouet-Boigny", "2024-02-01", 220_000, 3_600.0, 2_700, 76.0, 71.0),
    ("CI", "ABJ", "Abidjan Felix Houphouet-Boigny", "2024-03-01", 250_000, 4_000.0, 3_100, 79.0, 76.0),
    # Ghana — Accra Kotoka (GACL, ~3.3M/yr = ~275K/month)
    ("GH", "ACC", "Accra Kotoka International", "2024-01-01", 280_000, 4_000.0, 2_800, 74.0, 71.0),
    ("GH", "ACC", "Accra Kotoka International", "2024-02-01", 260_000, 3_700.0, 2_600, 72.0, 68.0),
    ("GH", "ACC", "Accra Kotoka International", "2024-03-01", 290_000, 4_200.0, 2_900, 75.0, 73.0),
    # Senegal — Dakar AIBD
    ("SN", "DSS", "Dakar Blaise Diagne", "2024-01-01", 215_000, 3_200.0, 2_600, 80.0, 75.0),
    ("SN", "DSS", "Dakar Blaise Diagne", "2024-02-01", 200_000, 3_000.0, 2_400, 78.0, 72.0),
    ("SN", "DSS", "Dakar Blaise Diagne", "2024-03-01", 230_000, 3_500.0, 2_800, 81.0, 77.0),
    # Burkina Faso — Ouagadougou
    ("BF", "OUA", "Ouagadougou International", "2024-01-01",  48_000,  800.0, 1_200, 65.0, 55.0),
    ("BF", "OUA", "Ouagadougou International", "2024-02-01",  45_000,  750.0, 1_100, 63.0, 52.0),
    # Mali — Bamako-Sénou
    ("ML", "BKO", "Bamako-Senou International", "2024-01-01",  38_000,  650.0, 1_000, 62.0, 50.0),
    ("ML", "BKO", "Bamako-Senou International", "2024-02-01",  36_000,  620.0,   950, 60.0, 48.0),
    # Guinea — Conakry
    ("GN", "CKY", "Conakry International", "2024-01-01",  28_000,  520.0,   800, 58.0, 45.0),
    ("GN", "CKY", "Conakry International", "2024-02-01",  26_000,  490.0,   760, 56.0, 43.0),
]

# Rail traffic: SITARAIL monthly freight (BF and CI legs, 2024)
# (country_code, line_name, period_date_str, freight_t, passengers, avg_transit_days, on_time_pct, rail_index)
RAIL_TRAFFIC_SEED = [
    ("BF", "SITARAIL", "2024-01-01", 33_000.0, 12_000, 2.5, 68.0, 57.0),
    ("BF", "SITARAIL", "2024-02-01", 31_500.0, 11_500, 2.6, 66.0, 55.0),
    ("BF", "SITARAIL", "2024-03-01", 34_000.0, 12_500, 2.4, 69.0, 58.0),
    ("CI", "SITARAIL", "2024-01-01", 33_274.0, 18_000, 1.8, 72.0, 59.0),
    ("CI", "SITARAIL", "2024-02-01", 31_900.0, 17_000, 1.9, 70.0, 57.0),
    ("CI", "SITARAIL", "2024-03-01", 35_000.0, 19_000, 1.7, 73.0, 61.0),
]


def seed_transport_data(db: Session) -> int:
    """
    Insert air and rail traffic seed data (FAAN/AERIA/GACL/AIBD/SITARAIL 2024).
    Idempotent. Returns number of new rows inserted.
    """
    inserted = 0

    for row in AIR_TRAFFIC_SEED:
        cc, apt_code, apt_name, period_str, pax, cargo, mvt, otp, air_idx = row
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue
        pd_ = date.fromisoformat(period_str)
        exists = (
            db.query(AirTraffic)
            .filter(AirTraffic.country_id == country.id, AirTraffic.period_date == pd_,
                    AirTraffic.airport_code == apt_code)
            .first()
        )
        if exists:
            continue
        db.add(AirTraffic(
            country_id=country.id, period_date=pd_, airport_code=apt_code,
            airport_name=apt_name, passengers_total=pax, cargo_tonnes=cargo,
            aircraft_movements=mvt, on_time_pct=otp, air_index=air_idx,
            data_source="seed_2024", confidence=0.80,
        ))
        inserted += 1

    for row in RAIL_TRAFFIC_SEED:
        cc, line, period_str, freight, pax, transit, otp, rail_idx = row
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue
        pd_ = date.fromisoformat(period_str)
        exists = (
            db.query(RailTraffic)
            .filter(RailTraffic.country_id == country.id, RailTraffic.period_date == pd_,
                    RailTraffic.line_name == line)
            .first()
        )
        if exists:
            continue
        db.add(RailTraffic(
            country_id=country.id, period_date=pd_, line_name=line,
            freight_tonnes=freight, passenger_count=pax, avg_transit_days=transit,
            on_time_pct=otp, rail_index=rail_idx,
            data_source="seed_sitarail_2024", confidence=0.75,
        ))
        inserted += 1

    if inserted:
        db.commit()
    return inserted


# Road corridor seed data (WASI v3.0 — 2024 ECOWAS ground corridors)
# (corridor_name, primary_country_code, avg_transit_days, border_wait_hours, road_quality_score, road_index, truck_count, period_str)
ROAD_CORRIDOR_SEED = [
    # Lagos–Abidjan corridor (NG primary)
    ("LAGOS-ABIDJAN", "NG", 4.2, 18.0, 62.0, 58.0, 4200, "2024-01-01"),
    ("LAGOS-ABIDJAN", "NG", 4.3, 19.5, 61.0, 57.2, 4050, "2024-02-01"),
    ("LAGOS-ABIDJAN", "NG", 4.1, 17.0, 63.0, 59.1, 4350, "2024-03-01"),
    # Tema–Ouagadougou corridor (GH primary)
    ("TEMA-OUAGADOUGOU", "GH", 5.8, 24.0, 55.0, 48.0, 2800, "2024-01-01"),
    ("TEMA-OUAGADOUGOU", "GH", 6.0, 25.5, 54.0, 46.8, 2650, "2024-02-01"),
    ("TEMA-OUAGADOUGOU", "GH", 5.7, 23.0, 56.0, 49.2, 2900, "2024-03-01"),
    # Dakar–Bamako corridor (SN primary)
    ("DAKAR-BAMAKO", "SN", 6.5, 20.0, 58.0, 51.0, 1800, "2024-01-01"),
    ("DAKAR-BAMAKO", "SN", 6.7, 21.0, 57.5, 50.2, 1720, "2024-02-01"),
    ("DAKAR-BAMAKO", "SN", 6.3, 19.0, 58.5, 52.1, 1870, "2024-03-01"),
    # Abidjan–Bamako corridor (CI primary)
    ("ABIDJAN-BAMAKO", "CI", 5.0, 16.0, 64.0, 60.0, 3200, "2024-01-01"),
    ("ABIDJAN-BAMAKO", "CI", 5.2, 17.0, 63.5, 59.1, 3050, "2024-02-01"),
    ("ABIDJAN-BAMAKO", "CI", 4.9, 15.5, 64.5, 61.0, 3320, "2024-03-01"),
    # Conakry–Freetown corridor (GN primary)
    ("CONAKRY-FREETOWN", "GN", 3.8, 12.0, 52.0, 62.0, 950, "2024-01-01"),
    ("CONAKRY-FREETOWN", "GN", 3.9, 12.5, 51.5, 61.3, 910, "2024-02-01"),
    ("CONAKRY-FREETOWN", "GN", 3.7, 11.5, 52.5, 62.8, 980, "2024-03-01"),
    # Lomé–Niamey corridor (TG primary)
    ("LOME-NIAMEY", "TG", 7.2, 30.0, 48.0, 42.0, 1600, "2024-01-01"),
    ("LOME-NIAMEY", "TG", 7.5, 31.5, 47.5, 41.1, 1520, "2024-02-01"),
    ("LOME-NIAMEY", "TG", 7.0, 29.0, 48.5, 43.0, 1650, "2024-03-01"),
]


def seed_road_data(db: Session) -> int:
    """
    Insert road corridor seed data (ECOWAS 2024 key corridors).
    Idempotent. Returns number of new rows inserted.
    """
    inserted = 0

    for row in ROAD_CORRIDOR_SEED:
        corridor, cc, transit, border_wait, quality, road_idx, trucks, period_str = row
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue
        pd_ = date.fromisoformat(period_str)
        exists = (
            db.query(RoadCorridor)
            .filter(
                RoadCorridor.country_id == country.id,
                RoadCorridor.period_date == pd_,
                RoadCorridor.corridor_name == corridor,
            )
            .first()
        )
        if exists:
            continue
        db.add(RoadCorridor(
            country_id=country.id,
            period_date=pd_,
            corridor_name=corridor,
            truck_count=trucks,
            avg_transit_days=transit,
            border_wait_hours=border_wait,
            road_quality_score=quality,
            road_index=road_idx,
            data_source="seed_ecowas_2024",
            confidence=0.70,
        ))
        inserted += 1

    if inserted:
        db.commit()
    return inserted
