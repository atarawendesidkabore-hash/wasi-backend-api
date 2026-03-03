"""
12-Step DCF Valuation Engine.

Implements the full Discounted Cash Flow pipeline:
  1. Calculate WACC (CAPM + Country Risk Premium)
  2. Project Revenue (declining growth rates)
  3. Operating Income (EBIT = Revenue × margin)
  4. NOPAT (EBIT × (1 - tax))
  5. Free Cash Flow (NOPAT + D&A - CapEx - ΔNWC)
  6. Discount FCFs to PV (mid-year convention)
  7. Terminal Value — Gordon Growth Model
  8. Terminal Value — Exit Multiple (EV/EBITDA)
  9. Sum Enterprise Value
  10. Equity Value (EV - Net Debt)
  11. Implied Share Price
  12. Blend Methodologies (Gordon weight + Exit Multiple weight)

Supports: COMPANY, COUNTRY, INFRASTRUCTURE entity types.
Scenario analysis: BULL / BASE / BEAR with probability-weighted blend.
Sensitivity table: WACC ± 2% × Terminal Growth ± 1%.
"""
import math
from src.utils.wacc_params import (
    COUNTRY_WACC_PARAMS, POLITICAL_RISK, _DEFAULT_WACC_PARAMS, _RF, _ERP,
)


class ValuationEngine:
    """Stateless 12-step DCF valuation engine. No DB dependency."""

    DEFAULT_PROJECTION_YEARS = 5
    DEFAULT_TERMINAL_GROWTH = 0.025
    DEFAULT_EXIT_MULTIPLE = 8.0
    DEFAULT_GORDON_WEIGHT = 0.50

    SCENARIO_MULTIPLIERS = {
        "BULL": 1.20,
        "BASE": 1.00,
        "BEAR": 0.75,
    }
    DEFAULT_SCENARIO_WEIGHTS = {
        "BULL": 0.25,
        "BASE": 0.50,
        "BEAR": 0.25,
    }

    # ── Step 1: WACC ──────────────────────────────────────────────

    def calculate_wacc(
        self,
        country_code: str,
        political_risk: float | None = None,
        wasi_index: float | None = None,
        rate_premium_bps: int = 250,
        custom_beta: float | None = None,
        custom_eq_ratio: float | None = None,
        custom_tax_rate: float | None = None,
    ) -> dict:
        """
        CAPM-based WACC with country risk premium.

        Re  = Rf + β × ERP + CRP
        Rd  = Rf + sovereign_spread
        CRP = f(political_risk, wasi_index)
        WACC = (E/V × Re) + (D/V × Rd × (1 − Tax))
        """
        p = COUNTRY_WACC_PARAMS.get(country_code.upper(), _DEFAULT_WACC_PARAMS)
        pol = political_risk if political_risk is not None else POLITICAL_RISK.get(country_code.upper(), 5.0)
        wasi = wasi_index if wasi_index is not None else 50.0

        beta = custom_beta if custom_beta is not None else p["beta"]
        eq = custom_eq_ratio if custom_eq_ratio is not None else p["eq_ratio"]
        tax = custom_tax_rate if custom_tax_rate is not None else p["tax"]

        crp = (pol / 10.0) * 0.072 + (1.0 - wasi / 100.0) * 0.048
        re = _RF + beta * _ERP + crp
        rd = _RF + rate_premium_bps / 10_000.0
        dt = 1.0 - eq
        wacc = eq * re + dt * rd * (1.0 - tax)

        return {
            "wacc": wacc,
            "wacc_pct": round(wacc * 100, 2),
            "cost_of_equity_pct": round(re * 100, 2),
            "cost_of_debt_pct": round(rd * 100, 2),
            "risk_free_rate_pct": round(_RF * 100, 2),
            "equity_risk_premium_pct": round(_ERP * 100, 2),
            "country_risk_premium_pct": round(crp * 100, 2),
            "beta": beta,
            "equity_ratio_pct": round(eq * 100, 1),
            "debt_ratio_pct": round(dt * 100, 1),
            "corporate_tax_rate_pct": round(tax * 100, 1),
        }

    # ── Steps 2-5: Project Free Cash Flows ───────────────────────

    def project_free_cash_flows(
        self,
        base_revenue: float,
        base_ebit_margin: float,
        base_da_pct: float,
        base_capex_pct: float,
        base_nwc_change_pct: float,
        tax_rate: float,
        revenue_growth_rates: list[float],
        margin_trajectory: list[float] | None = None,
        projection_years: int = 5,
    ) -> list[dict]:
        """
        Steps 2-5: Revenue → EBIT → NOPAT → FCFF per projection year.

        Args:
            base_revenue: Last actual year revenue (USD).
            base_ebit_margin: Operating margin (0-1).
            base_da_pct: D&A as fraction of revenue.
            base_capex_pct: CapEx as fraction of revenue.
            base_nwc_change_pct: Change in NWC as fraction of revenue.
            tax_rate: Corporate tax rate (0-1).
            revenue_growth_rates: Per-year growth rates (len >= projection_years).
            margin_trajectory: Optional per-year margins; defaults to base_ebit_margin.
            projection_years: Number of forecast years.

        Returns:
            List of dicts with year, revenue, ebit, nopat, da, capex, delta_nwc, fcf.
        """
        fcfs = []
        revenue = base_revenue

        for i in range(projection_years):
            growth = revenue_growth_rates[i] if i < len(revenue_growth_rates) else revenue_growth_rates[-1]
            revenue = revenue * (1.0 + growth)

            margin = margin_trajectory[i] if margin_trajectory and i < len(margin_trajectory) else base_ebit_margin
            ebit = revenue * margin
            nopat = ebit * (1.0 - tax_rate)
            da = revenue * base_da_pct
            capex = revenue * base_capex_pct
            delta_nwc = revenue * base_nwc_change_pct

            fcf = nopat + da - capex - delta_nwc
            ebitda = ebit + da

            fcfs.append({
                "year": i + 1,
                "revenue_usd": round(revenue, 2),
                "revenue_growth_pct": round(growth * 100, 2),
                "ebit_usd": round(ebit, 2),
                "ebit_margin_pct": round(margin * 100, 2),
                "ebitda_usd": round(ebitda, 2),
                "nopat_usd": round(nopat, 2),
                "da_usd": round(da, 2),
                "capex_usd": round(capex, 2),
                "delta_nwc_usd": round(delta_nwc, 2),
                "fcf_usd": round(fcf, 2),
            })

        return fcfs

    # ── Step 6: Discount FCFs to Present Value ───────────────────

    def discount_fcfs(
        self,
        fcfs: list[dict],
        wacc: float,
        mid_year: bool = True,
    ) -> list[dict]:
        """
        Step 6: Apply discount factors using mid-year convention.

        discount_factor = 1 / (1 + WACC)^(year - 0.5)  [mid-year]
        discount_factor = 1 / (1 + WACC)^year           [year-end]
        """
        total_pv = 0.0
        for period in fcfs:
            year = period["year"]
            exponent = year - 0.5 if mid_year else year
            df = 1.0 / (1.0 + wacc) ** exponent
            pv = period["fcf_usd"] * df
            period["discount_factor"] = round(df, 6)
            period["pv_fcf_usd"] = round(pv, 2)
            total_pv += pv

        return fcfs

    # ── Steps 7-8: Terminal Value ────────────────────────────────

    def calculate_terminal_value(
        self,
        last_year_fcf: float,
        last_year_ebitda: float,
        wacc: float,
        terminal_growth: float = 0.025,
        exit_multiple: float = 8.0,
        projection_years: int = 5,
        mid_year: bool = True,
    ) -> dict:
        """
        Steps 7-8: Gordon Growth Model + Exit Multiple.

        Gordon: TV = FCF × (1+g) / (WACC - g)
        Exit:   TV = EBITDA × EV/EBITDA multiple
        """
        if terminal_growth >= wacc:
            terminal_growth = wacc - 0.01

        tv_gordon = last_year_fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
        tv_exit = last_year_ebitda * exit_multiple

        # Discount terminal values to present
        exponent = projection_years - 0.5 if mid_year else projection_years
        tv_discount_factor = 1.0 / (1.0 + wacc) ** exponent
        pv_gordon = tv_gordon * tv_discount_factor
        pv_exit = tv_exit * tv_discount_factor

        return {
            "gordon_tv_usd": round(tv_gordon, 2),
            "gordon_pv_usd": round(pv_gordon, 2),
            "exit_tv_usd": round(tv_exit, 2),
            "exit_pv_usd": round(pv_exit, 2),
            "terminal_growth_pct": round(terminal_growth * 100, 2),
            "exit_multiple": exit_multiple,
            "tv_discount_factor": round(tv_discount_factor, 6),
        }

    # ── Steps 9-12: Enterprise → Equity → Share Price ────────────

    def calculate_equity_value(
        self,
        pv_fcfs_total: float,
        pv_terminal_gordon: float,
        pv_terminal_exit: float,
        net_debt: float,
        shares_outstanding: int | None = None,
        gordon_weight: float = 0.50,
        current_share_price: float | None = None,
    ) -> dict:
        """
        Steps 9-12: Blend terminal values, compute EV, equity, implied price.
        """
        blended_pv_terminal = (
            gordon_weight * pv_terminal_gordon +
            (1.0 - gordon_weight) * pv_terminal_exit
        )
        enterprise_value = pv_fcfs_total + blended_pv_terminal
        equity_value = enterprise_value - net_debt

        implied_price = None
        upside_pct = None
        if shares_outstanding and shares_outstanding > 0:
            implied_price = round(equity_value / shares_outstanding, 2)
            if current_share_price and current_share_price > 0:
                upside_pct = round(
                    (implied_price - current_share_price) / current_share_price * 100, 2
                )

        return {
            "pv_fcfs_total_usd": round(pv_fcfs_total, 2),
            "blended_pv_terminal_usd": round(blended_pv_terminal, 2),
            "enterprise_value_usd": round(enterprise_value, 2),
            "net_debt_usd": round(net_debt, 2),
            "equity_value_usd": round(equity_value, 2),
            "implied_share_price": implied_price,
            "upside_pct": upside_pct,
            "gordon_weight": gordon_weight,
        }

    # ── Full 12-Step DCF Pipeline ────────────────────────────────

    def run_dcf(
        self,
        financials: dict,
        wacc_params: dict,
        scenario: str = "BASE",
        projection_years: int = 5,
        terminal_growth: float = 0.025,
        exit_multiple: float = 8.0,
        gordon_weight: float = 0.50,
        revenue_growth_overrides: list[float] | None = None,
    ) -> dict:
        """
        Full 12-step DCF for a single scenario.

        financials dict keys:
            base_revenue, base_ebit_margin, base_da_pct, base_capex_pct,
            base_nwc_change_pct, tax_rate, revenue_growth_rates,
            net_debt, shares_outstanding, current_share_price,
            margin_trajectory (optional)
        """
        wacc = wacc_params["wacc"]

        # Apply scenario multiplier to growth rates
        multiplier = self.SCENARIO_MULTIPLIERS.get(scenario, 1.0)
        base_growth = revenue_growth_overrides or financials.get("revenue_growth_rates", [0.05] * projection_years)
        scenario_growth = [g * multiplier for g in base_growth]

        # Adjust margin trajectory for scenarios
        base_margin = financials.get("base_ebit_margin", 0.15)
        margin_traj = financials.get("margin_trajectory")
        if margin_traj:
            if scenario == "BULL":
                margin_traj = [m * 1.05 for m in margin_traj]
            elif scenario == "BEAR":
                margin_traj = [m * 0.90 for m in margin_traj]

        # Steps 2-5: Project FCFs
        fcfs = self.project_free_cash_flows(
            base_revenue=financials["base_revenue"],
            base_ebit_margin=base_margin,
            base_da_pct=financials.get("base_da_pct", 0.05),
            base_capex_pct=financials.get("base_capex_pct", 0.08),
            base_nwc_change_pct=financials.get("base_nwc_change_pct", 0.02),
            tax_rate=financials.get("tax_rate", wacc_params.get("corporate_tax_rate_pct", 28.0) / 100.0),
            revenue_growth_rates=scenario_growth,
            margin_trajectory=margin_traj,
            projection_years=projection_years,
        )

        # Step 6: Discount
        fcfs = self.discount_fcfs(fcfs, wacc)
        pv_fcfs_total = sum(p["pv_fcf_usd"] for p in fcfs)

        # Steps 7-8: Terminal value
        last = fcfs[-1]
        tv = self.calculate_terminal_value(
            last_year_fcf=last["fcf_usd"],
            last_year_ebitda=last["ebitda_usd"],
            wacc=wacc,
            terminal_growth=terminal_growth,
            exit_multiple=exit_multiple,
            projection_years=projection_years,
        )

        # Steps 9-12: Equity value
        equity = self.calculate_equity_value(
            pv_fcfs_total=pv_fcfs_total,
            pv_terminal_gordon=tv["gordon_pv_usd"],
            pv_terminal_exit=tv["exit_pv_usd"],
            net_debt=financials.get("net_debt", 0.0),
            shares_outstanding=financials.get("shares_outstanding"),
            gordon_weight=gordon_weight,
            current_share_price=financials.get("current_share_price"),
        )

        return {
            "scenario": scenario,
            "wacc": wacc_params,
            "projections": fcfs,
            "terminal_value": tv,
            **equity,
            "projection_years": projection_years,
        }

    # ── Scenario Analysis ────────────────────────────────────────

    def run_scenario_analysis(
        self,
        financials: dict,
        wacc_params: dict,
        scenario_weights: dict | None = None,
        bull_growth_override: list[float] | None = None,
        bear_growth_override: list[float] | None = None,
        **kwargs,
    ) -> dict:
        """
        Run BULL/BASE/BEAR scenarios, compute probability-weighted blend.
        """
        weights = scenario_weights or self.DEFAULT_SCENARIO_WEIGHTS
        total_w = sum(weights.values())
        weights = {k: v / total_w for k, v in weights.items()}

        # Extract revenue_growth_overrides from kwargs so it doesn't conflict
        # with the explicit per-scenario overrides passed to run_dcf
        base_growth_overrides = kwargs.pop("revenue_growth_overrides", None)

        scenarios = {}
        for scenario in ["BULL", "BASE", "BEAR"]:
            overrides = base_growth_overrides
            if scenario == "BULL" and bull_growth_override:
                overrides = bull_growth_override
            elif scenario == "BEAR" and bear_growth_override:
                overrides = bear_growth_override

            result = self.run_dcf(
                financials=financials,
                wacc_params=wacc_params,
                scenario=scenario,
                revenue_growth_overrides=overrides,
                **kwargs,
            )
            result["weight"] = weights.get(scenario, 0.0)
            scenarios[scenario] = result

        # Compute blended values
        blended_ev = sum(
            scenarios[s]["enterprise_value_usd"] * scenarios[s]["weight"]
            for s in scenarios
        )
        blended_equity = sum(
            scenarios[s]["equity_value_usd"] * scenarios[s]["weight"]
            for s in scenarios
        )
        blended_price = None
        blended_upside = None
        shares = financials.get("shares_outstanding")
        if shares and shares > 0:
            blended_price = round(blended_equity / shares, 2)
            current = financials.get("current_share_price")
            if current and current > 0:
                blended_upside = round(
                    (blended_price - current) / current * 100, 2
                )

        blended = {
            "scenario": "BLENDED",
            "weight": 1.0,
            "wacc": wacc_params,
            "enterprise_value_usd": round(blended_ev, 2),
            "equity_value_usd": round(blended_equity, 2),
            "implied_share_price": blended_price,
            "upside_pct": blended_upside,
            "pv_fcfs_total_usd": round(
                sum(scenarios[s]["pv_fcfs_total_usd"] * scenarios[s]["weight"] for s in scenarios), 2
            ),
            "blended_pv_terminal_usd": round(
                sum(scenarios[s]["blended_pv_terminal_usd"] * scenarios[s]["weight"] for s in scenarios), 2
            ),
            "net_debt_usd": financials.get("net_debt", 0.0),
            "gordon_weight": kwargs.get("gordon_weight", self.DEFAULT_GORDON_WEIGHT),
            "projections": scenarios["BASE"]["projections"],
            "terminal_value": scenarios["BASE"]["terminal_value"],
        }

        return {
            "scenarios": scenarios,
            "blended": blended,
        }

    # ── Sensitivity Table ────────────────────────────────────────

    def generate_sensitivity_table(
        self,
        base_result: dict,
        financials: dict,
        wacc_center: float | None = None,
        tg_center: float | None = None,
        wacc_range: tuple = (-0.02, 0.02, 0.005),
        tg_range: tuple = (-0.01, 0.01, 0.0025),
    ) -> list[dict]:
        """
        2D sensitivity grid: vary WACC and terminal growth rate.
        Re-runs Steps 6-12 only (FCF projections held constant).
        """
        wacc_base = wacc_center or base_result["wacc"]["wacc"]
        tg_base = tg_center or (base_result["terminal_value"]["terminal_growth_pct"] / 100.0)
        fcfs = base_result["projections"]

        cells = []
        wacc_val = wacc_base + wacc_range[0]
        while wacc_val <= wacc_base + wacc_range[1] + 1e-9:
            tg_val = tg_base + tg_range[0]
            while tg_val <= tg_base + tg_range[1] + 1e-9:
                if tg_val >= wacc_val:
                    cells.append({
                        "wacc_pct": round(wacc_val * 100, 2),
                        "terminal_growth_pct": round(tg_val * 100, 2),
                        "enterprise_value_usd": None,
                        "equity_value_usd": None,
                        "implied_share_price": None,
                    })
                    tg_val += tg_range[2]
                    continue

                # Re-discount FCFs at this WACC
                pv_total = 0.0
                for p in fcfs:
                    year = p["year"]
                    df = 1.0 / (1.0 + wacc_val) ** (year - 0.5)
                    pv_total += p["fcf_usd"] * df

                last = fcfs[-1]
                proj_years = len(fcfs)

                # Terminal value at this WACC + TG
                tv_gordon = last["fcf_usd"] * (1.0 + tg_val) / (wacc_val - tg_val)
                tv_exit = last["ebitda_usd"] * base_result["terminal_value"]["exit_multiple"]
                tv_df = 1.0 / (1.0 + wacc_val) ** (proj_years - 0.5)

                gordon_w = base_result.get("gordon_weight", 0.50)
                pv_tv = gordon_w * tv_gordon * tv_df + (1.0 - gordon_w) * tv_exit * tv_df
                ev = pv_total + pv_tv
                equity = ev - financials.get("net_debt", 0.0)

                price = None
                shares = financials.get("shares_outstanding")
                if shares and shares > 0:
                    price = round(equity / shares, 2)

                cells.append({
                    "wacc_pct": round(wacc_val * 100, 2),
                    "terminal_growth_pct": round(tg_val * 100, 2),
                    "enterprise_value_usd": round(ev, 2),
                    "equity_value_usd": round(equity, 2),
                    "implied_share_price": price,
                })

                tg_val += tg_range[2]
            wacc_val += wacc_range[2]

        return cells

    # ── Country Economy DCF Adapter ──────────────────────────────

    def prepare_country_financials(
        self,
        macro_data: list[dict],
        trade_surplus_usd: float = 0.0,
        commodity_sensitivity: float = 0.0,
        wasi_index: float = 50.0,
    ) -> dict:
        """
        Adapt macro data into DCF-compatible financials for country-level valuation.

        macro_data: list of {year, gdp_usd_billions, gdp_growth_pct, inflation_pct,
                              debt_gdp_pct, is_projection} sorted by year asc.

        Revenue proxy = GDP in USD.
        Operating margin proxy = (100 - debt_gdp_pct) / 200  (lower debt → higher margin).
        CapEx proxy = 5% of GDP (government capital expenditure).
        D&A proxy = 3% of GDP.
        NWC change proxy = 1% of GDP.
        """
        if not macro_data:
            return {
                "base_revenue": 10_000_000_000,
                "base_ebit_margin": 0.10,
                "base_da_pct": 0.03,
                "base_capex_pct": 0.05,
                "base_nwc_change_pct": 0.01,
                "tax_rate": 0.28,
                "revenue_growth_rates": [0.04, 0.04, 0.03, 0.03, 0.03],
                "net_debt": 0.0,
                "shares_outstanding": None,
                "current_share_price": None,
            }

        latest = macro_data[-1]
        gdp_usd = (latest.get("gdp_usd_billions") or 10.0) * 1_000_000_000
        debt_ratio = latest.get("debt_gdp_pct") or 40.0

        # Derive growth rates from historical + IMF projections
        growth_rates = []
        for row in macro_data:
            g = row.get("gdp_growth_pct")
            if g is not None:
                growth_rates.append(g / 100.0)

        # Use last 3 years of growth to project, or default 4%
        if len(growth_rates) >= 2:
            recent_avg = sum(growth_rates[-3:]) / len(growth_rates[-3:])
            # Declining growth trajectory
            proj_growth = [
                recent_avg,
                recent_avg * 0.90,
                recent_avg * 0.80,
                recent_avg * 0.70,
                recent_avg * 0.65,
            ]
        else:
            proj_growth = [0.04, 0.035, 0.03, 0.03, 0.025]

        margin = max(0.05, min(0.30, (100.0 - debt_ratio) / 200.0))

        return {
            "base_revenue": gdp_usd,
            "base_ebit_margin": round(margin, 4),
            "base_da_pct": 0.03,
            "base_capex_pct": 0.05,
            "base_nwc_change_pct": 0.01,
            "tax_rate": 0.28,
            "revenue_growth_rates": [round(g, 4) for g in proj_growth],
            "net_debt": round(gdp_usd * debt_ratio / 100.0, 2),
            "shares_outstanding": None,
            "current_share_price": None,
        }

    # ── Infrastructure Project DCF Adapter ───────────────────────

    def prepare_infrastructure_financials(
        self,
        project_statements: list[dict],
        total_project_cost_usd: float = 0.0,
        construction_years: int = 2,
        operational_years: int = 3,
    ) -> dict:
        """
        Two-phase infrastructure model:
        - Construction phase: negative FCFs (capex outlay, no revenue).
        - Operational phase: growing revenue, maintenance costs.
        """
        projection_years = construction_years + operational_years

        if project_statements:
            # Use submitted financials
            latest = project_statements[-1]
            base_rev = latest.get("project_revenue_usd") or total_project_cost_usd * 0.15
            constr = latest.get("construction_cost_usd") or total_project_cost_usd / construction_years
            maint = latest.get("maintenance_cost_usd") or base_rev * 0.10
        else:
            base_rev = total_project_cost_usd * 0.15
            constr = total_project_cost_usd / max(construction_years, 1)
            maint = base_rev * 0.10

        # Build per-year growth rates: 0% during construction, growing during ops
        growth_rates = []
        for i in range(projection_years):
            if i < construction_years:
                growth_rates.append(0.0)
            else:
                ops_year = i - construction_years
                growth_rates.append(0.10 * (0.85 ** ops_year))

        return {
            "base_revenue": base_rev,
            "base_ebit_margin": 0.25,
            "base_da_pct": 0.08,
            "base_capex_pct": constr / max(base_rev, 1.0) if base_rev > 0 else 0.50,
            "base_nwc_change_pct": 0.02,
            "tax_rate": 0.25,
            "revenue_growth_rates": growth_rates,
            "net_debt": total_project_cost_usd * 0.60,
            "shares_outstanding": None,
            "current_share_price": None,
        }

    # ── Narrative Generator ──────────────────────────────────────

    def generate_narrative(
        self,
        entity_type: str,
        name: str,
        country_code: str,
        blended: dict,
        scenarios: dict,
        risk_score: float | None = None,
    ) -> str:
        """Generate a human-readable valuation narrative."""
        ev = blended["enterprise_value_usd"]
        equity = blended["equity_value_usd"]
        price = blended.get("implied_share_price")
        upside = blended.get("upside_pct")

        def _fmt(val):
            if val is None:
                return "N/A"
            if abs(val) >= 1e9:
                return f"${val / 1e9:,.1f}B"
            if abs(val) >= 1e6:
                return f"${val / 1e6:,.1f}M"
            return f"${val:,.0f}"

        parts = [
            f"DCF Valuation for {name} ({country_code}) — {entity_type}.",
            f"Enterprise Value: {_fmt(ev)}.",
            f"Equity Value: {_fmt(equity)}.",
        ]

        if price is not None:
            parts.append(f"Implied Share Price: ${price:,.2f}.")
            if upside is not None:
                direction = "upside" if upside > 0 else "downside"
                parts.append(f"{abs(upside):.1f}% {direction} to current price.")

        bull_ev = scenarios.get("BULL", {}).get("enterprise_value_usd", 0)
        bear_ev = scenarios.get("BEAR", {}).get("enterprise_value_usd", 0)
        parts.append(
            f"Scenario range: {_fmt(bear_ev)} (Bear) to {_fmt(bull_ev)} (Bull)."
        )

        if risk_score is not None:
            if risk_score >= 70:
                parts.append("Risk: ELEVATED — increased uncertainty in projections.")
            elif risk_score >= 40:
                parts.append("Risk: MODERATE — standard uncertainty levels.")
            else:
                parts.append("Risk: LOW — favorable risk profile.")

        parts.append("This valuation requires analyst review before investment decisions.")

        return " ".join(parts)
