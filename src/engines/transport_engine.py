"""
TransportEngine — Multi-modal transport composite index.

Formula:
  WASI_Transport = W_maritime × Maritime + W_air × Air + W_rail × Rail + W_road × Road

Country profiles determine mode weights. Six profiles per WASI v3.0 spec (Section 1):
  coastal_major_port — NG, CI, GH, SN  (major Atlantic/Gulf of Guinea ports)
  coastal_transit_hub — BJ, TG          (regional transit corridors to landlocked)
  landlocked_rail    — BF               (SITARAIL freight, 60% of tonnage)
  landlocked_no_rail — ML, NE           (road dominant, no operational rail)
  coastal_mining     — GN, MR, SL, LR  (extractive exports, road-heavy hinterland)
  small_island       — CV, GM, GW      (maritime + air dominant, minimal road)

SITARAIL baseline (2019): ~1,016,200 tonnes/year → monthly ~84,683 t
SITARAIL actual   (2024): ~795,286 tonnes/year → monthly ~66,274 t
SITARAIL split: CI = 40% of tonnage, BF = 60% of tonnage.
Rail_Index base = 80 (relative to 2019 baseline).

Political risk discounts (air connectivity only):
  BF: -20% (airlines withdrew post-coup), ML: -15%, NE: -25%
Security discounts (road corridor_performance only):
  BF: -15%, ML: -20%, NE: -25%
"""
from typing import Dict, Optional
from datetime import date


# Six transport profiles with mode weights (must each sum to 1.0)
# Per WASI v3.0 spec Section 1 — corrected assignments
COUNTRY_PROFILES: Dict[str, str] = {
    "NG": "coastal_major_port",   "CI": "coastal_major_port",
    "GH": "coastal_major_port",   "SN": "coastal_major_port",
    "BF": "landlocked_rail",      "ML": "landlocked_no_rail",
    "GN": "coastal_mining",       "BJ": "coastal_transit_hub",
    "TG": "coastal_transit_hub",  "NE": "landlocked_no_rail",
    "MR": "coastal_mining",       "GW": "small_island",
    "SL": "coastal_mining",       "LR": "coastal_mining",
    "GM": "small_island",         "CV": "small_island",
}

# Profile weight vectors: {maritime, air, rail, road} — all must sum to 1.0
# Updated per WASI v3.0 spec Section 1
PROFILE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "coastal_major_port":  {"maritime": 0.35, "air": 0.25, "rail": 0.05, "road": 0.35},
    "coastal_transit_hub": {"maritime": 0.30, "air": 0.15, "rail": 0.05, "road": 0.50},
    "landlocked_rail":     {"maritime": 0.05, "air": 0.15, "rail": 0.35, "road": 0.45},
    "landlocked_no_rail":  {"maritime": 0.05, "air": 0.15, "rail": 0.05, "road": 0.75},
    "coastal_mining":      {"maritime": 0.25, "air": 0.15, "rail": 0.10, "road": 0.50},
    "small_island":        {"maritime": 0.40, "air": 0.30, "rail": 0.00, "road": 0.30},
}

# SITARAIL benchmarks (tonnes/month)
SITARAIL_BASELINE_MONTHLY = 84_683   # 2019 monthly average (1,016,200 t/yr)
SITARAIL_2024_MONTHLY = 66_274       # 2024 monthly average

# SITARAIL tonnage split between CI and BF
SITARAIL_SPLIT: Dict[str, float] = {
    "CI": 0.40,   # CI originates/receives ~40% of SITARAIL freight
    "BF": 0.60,   # BF landlocked destination = ~60% of freight
}

# Air connectivity political risk discounts (applied to connectivity sub-component only)
# Sources: IATA route suspensions 2022-2024
POLITICAL_RISK_DISCOUNTS: Dict[str, float] = {
    "BF": 0.20,   # -20%: airlines withdrew post-coup 2022
    "ML": 0.15,   # -15%: Air France suspended Bamako 2022
    "NE": 0.25,   # -25%: Niamey flight suspensions 2023 (partial resumption 2024)
}

# Road corridor_performance security discounts (applied to corridor sub-component only)
# Sources: OPA checkpoint data, corridor disruption reports 2023-2024
SECURITY_DISCOUNTS: Dict[str, float] = {
    "BF": 0.15,   # -15%: convoy attacks, checkpoint extortion on Tema-Ouaga corridor
    "ML": 0.20,   # -20%: armed group activity on Dakar-Bamako corridor
    "NE": 0.25,   # -25%: Niamey corridor restrictions post-coup 2023
}

# Air traffic benchmarks (passengers/month) — primary airport per country
AIR_BENCHMARKS: Dict[str, int] = {
    "NG": 1_400_000,  # Lagos Murtala Muhammed (FAAN, ~16.8M/yr total domestic+intl)
    "CI": 240_000,    # Abidjan Félix Houphouët-Boigny (AERIA, ~2.8M/yr)
    "GH": 275_000,    # Accra Kotoka (GACL, ~3.3M/yr — 2024 actual)
    "SN": 220_000,    # Dakar Blaise Diagne (AIBD, ~2.7M/yr)
    "BF": 50_000,     # Ouagadougou (~0.6M/yr)
    "ML": 40_000,     # Bamako-Sénou (~0.5M/yr)
    "GN": 30_000,     # Conakry (~0.35M/yr)
    "BJ": 25_000,     # Cotonou (~0.3M/yr)
    "TG": 25_000,     # Lomé-Tokoin (~0.3M/yr)
    "NE": 15_000,     # Niamey (~0.18M/yr)
    "MR": 20_000,     # Nouakchott (~0.24M/yr)
    "GW": 5_000,      # Bissau (~0.06M/yr)
    "SL": 10_000,     # Freetown (~0.12M/yr)
    "LR": 10_000,     # Monrovia (~0.12M/yr)
    "GM": 15_000,     # Banjul (~0.18M/yr)
    "CV": 20_000,     # Praia (~0.24M/yr)
}


class TransportEngine:

    def get_profile(self, country_code: str) -> str:
        return COUNTRY_PROFILES.get(country_code, "coastal_major_port")

    def get_weights(self, country_code: str) -> Dict[str, float]:
        profile = self.get_profile(country_code)
        return PROFILE_WEIGHTS[profile].copy()

    def normalize_air(
        self,
        passengers: Optional[int],
        cargo_tonnes: Optional[float] = None,
        ecowas_routes: Optional[int] = None,
        country_code: str = "",
    ) -> float:
        """
        Air index using 3 sub-components:
          0.40 × pax_component + 0.40 × cargo_component + 0.20 × connectivity_component
        Political risk discount applied to connectivity only (BF -20%, ML -15%, NE -25%).
        Falls back to single-component benchmark score when only pax data available.
        """
        benchmark = AIR_BENCHMARKS.get(country_code, 50_000)
        discount = POLITICAL_RISK_DISCOUNTS.get(country_code, 0.0)

        # Pax component
        if passengers and passengers > 0:
            pax_component = min(100.0, (passengers / benchmark) * 100.0)
        else:
            pax_component = 50.0

        # Cargo component (cargo_benchmark ≈ 1% of pax in tonnes)
        cargo_benchmark = benchmark * 0.01
        if cargo_tonnes and cargo_tonnes > 0:
            cargo_component = min(100.0, (cargo_tonnes / cargo_benchmark) * 100.0)
        else:
            cargo_component = pax_component   # proxy when no cargo data

        # Connectivity component (ECOWAS routes; benchmark = 20 routes for major hub)
        route_benchmark = max(5, benchmark // 60_000)   # scaled to airport size
        if ecowas_routes and ecowas_routes > 0:
            connectivity_base = min(100.0, (ecowas_routes / route_benchmark) * 100.0)
        else:
            connectivity_base = 50.0
        connectivity_adj = connectivity_base * (1.0 - discount)

        air_composite = 0.40 * pax_component + 0.40 * cargo_component + 0.20 * connectivity_adj
        return round(min(100.0, max(0.0, air_composite)), 2)

    def normalize_rail(
        self,
        freight_tonnes: Optional[float],
        country_code: str = "",
        structural_break: bool = False,
    ) -> float:
        """
        Normalize monthly rail freight to 0–100.
        SITARAIL split: CI=40%, BF=60% of SITARAIL tonnage.
        Guinea: +25% boost if Simandou structural_break flag is True.
        Countries without operational rail return 0.0.
        """
        # Guinea Simandou rail (not SITARAIL)
        if country_code == "GN":
            if not freight_tonnes or freight_tonnes <= 0:
                return 0.0
            score = (freight_tonnes / SITARAIL_BASELINE_MONTHLY) * 80.0
            if structural_break:
                score = score * 1.25   # +25% structural break boost
            return round(min(100.0, max(0.0, score)), 2)

        # SITARAIL countries: apply corridor split
        split = SITARAIL_SPLIT.get(country_code, 0.0)
        if split == 0.0 or not freight_tonnes or freight_tonnes <= 0:
            return 0.0   # no operational rail for this country
        base_score = (freight_tonnes / SITARAIL_BASELINE_MONTHLY) * 80.0
        score = base_score * split
        return round(min(100.0, max(0.0, score)), 2)

    def normalize_road(
        self,
        avg_transit_days: Optional[float],
        border_wait_hours: Optional[float],
        road_quality_score: Optional[float],
        country_code: str = "",
    ) -> float:
        """
        Road index: 0.50 × transit_vol + 0.30 × corridor_perf + 0.20 × fuel_proxy.
        Security discount applied to corridor_perf only (BF -15%, ML -20%, NE -25%).
        Benchmarks: avg_transit_days ≤ 3 → 100; ≥ 14 → 0
                    border_wait_hours ≤ 4 → 100; ≥ 72 → 0
        """
        discount = SECURITY_DISCOUNTS.get(country_code, 0.0)

        # Transit volume component (fewer days = higher score)
        if avg_transit_days is not None:
            transit_vol = max(0.0, (14.0 - avg_transit_days) / 11.0 * 100.0)
        else:
            transit_vol = 60.0   # ECOWAS median

        # Corridor performance (border wait + road quality, averaged)
        corridor_scores = []
        if border_wait_hours is not None:
            corridor_scores.append(max(0.0, (72.0 - border_wait_hours) / 68.0 * 100.0))
        if road_quality_score is not None:
            corridor_scores.append(road_quality_score)
        corridor_base = sum(corridor_scores) / len(corridor_scores) if corridor_scores else 60.0
        corridor_perf = corridor_base * (1.0 - discount)

        # Fuel proxy (road_quality_score when no fuel data; default 60)
        fuel_proxy = road_quality_score if road_quality_score is not None else 60.0

        road = 0.50 * transit_vol + 0.30 * corridor_perf + 0.20 * fuel_proxy
        return round(min(100.0, max(0.0, road)), 2)

    def calculate_transport_composite(
        self,
        country_code: str,
        period_date: date,
        maritime_index: Optional[float] = None,
        air_index: Optional[float] = None,
        rail_index: Optional[float] = None,
        road_index: Optional[float] = None,
    ) -> Dict:
        """
        Calculate the multi-modal transport composite for a country.
        Missing modes are excluded and remaining weights re-normalized.
        """
        profile = self.get_profile(country_code)
        base_weights = PROFILE_WEIGHTS[profile].copy()

        available = {}
        if maritime_index is not None:
            available["maritime"] = maritime_index
        if air_index is not None:
            available["air"] = air_index
        if rail_index is not None:
            available["rail"] = rail_index
        if road_index is not None:
            available["road"] = road_index

        # Re-normalize weights for available modes
        total_w = sum(base_weights[m] for m in available)
        if total_w == 0:
            total_w = 1.0

        effective = {m: base_weights[m] / total_w for m in available}
        composite = sum(available[m] * effective[m] for m in available)

        return {
            "country_code": country_code,
            "period_date": period_date,
            "country_profile": profile,
            "maritime_index": maritime_index,
            "air_index": air_index,
            "rail_index": rail_index,
            "road_index": road_index,
            "w_maritime": round(effective.get("maritime", 0.0), 4),
            "w_air": round(effective.get("air", 0.0), 4),
            "w_rail": round(effective.get("rail", 0.0), 4),
            "w_road": round(effective.get("road", 0.0), 4),
            "transport_composite": round(composite, 4),
        }
