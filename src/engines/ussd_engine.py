"""
USSD Engine — Session management, menu trees, and data aggregation.

Handles the stateless USSD callback protocol:
  1. MNO sends POST with sessionId, phoneNumber, serviceCode, text
  2. Engine determines menu level from text input chain
  3. Returns CON (continue) or END (terminate) response
  4. Data captured at each step is aggregated into WASI signals

Menu Structure (*384*WASI#):
  1. Prix du marché (Market prices)
     → Select commodity → Enter price → Confirm
  2. Déclaration commerce (Trade declaration)
     → Select corridor → Select goods → Enter quantity/value → Confirm
  3. Port / Douanes (Port clearance)
     → Select port → Report status → Enter delay hours → Confirm
  4. Mobile Money stats (MNO partners only)
     → Automated aggregate push from MNO gateway
  5. Mon compte WASI (WASI account)
     → Check balance → View country index → Subscribe to alerts
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import Country
from src.database.ussd_models import (
    USSDProvider, USSDSession, USSDMobileMoneyFlow,
    USSDCommodityReport, USSDTradeDeclaration,
    USSDPortClearance, USSDDailyAggregate,
)

logger = logging.getLogger(__name__)

# ── Currency mapping ──────────────────────────────────────────────────
COUNTRY_CURRENCY = {
    "CI": "XOF", "SN": "XOF", "ML": "XOF", "BF": "XOF",
    "BJ": "XOF", "TG": "XOF", "NE": "XOF", "GW": "XOF",
    "NG": "NGN", "GH": "GHS", "GN": "GNF", "SL": "SLE",
    "LR": "LRD", "GM": "GMD", "MR": "MRU", "CV": "CVE",
}

# ── Approximate FX rates (updated daily by MNO feeds) ────────────────
DEFAULT_FX_RATES = {
    "XOF": 610.0,   # 1 USD ≈ 610 FCFA
    "NGN": 1550.0,  # 1 USD ≈ 1550 Naira
    "GHS": 15.0,    # 1 USD ≈ 15 Cedi
    "GNF": 8600.0,  # 1 USD ≈ 8600 GNF
    "SLE": 22.0,    # 1 USD ≈ 22 SLE (new leone)
    "LRD": 192.0,   # 1 USD ≈ 192 LRD
    "GMD": 70.0,    # 1 USD ≈ 70 Dalasi
    "MRU": 40.0,    # 1 USD ≈ 40 Ouguiya
    "CVE": 102.0,   # 1 USD ≈ 102 Escudo
}

# ── Commodity codes for market reports ────────────────────────────────
COMMODITY_CODES = {
    "1": ("LOCAL_RICE", "Riz local"),
    "2": ("IMPORTED_RICE", "Riz importé"),
    "3": ("MAIZE", "Maïs"),
    "4": ("MILLET", "Mil"),
    "5": ("SORGHUM", "Sorgho"),
    "6": ("ONION", "Oignon"),
    "7": ("TOMATO", "Tomate"),
    "8": ("PALM_OIL", "Huile de palme"),
    "9": ("CASHEW", "Noix de cajou"),
    "10": ("COCOA_LOCAL", "Cacao local"),
    "11": ("CATTLE", "Bétail (boeuf)"),
    "12": ("GOAT", "Chèvre"),
    "13": ("FISH", "Poisson"),
    "14": ("SHEA_BUTTER", "Beurre de karité"),
}

# ── Border posts for trade declarations ───────────────────────────────
BORDER_POSTS = {
    "1": ("SEME-KRAKE", "NG", "BJ", "Sèmè-Kraké (Nigeria-Bénin)"),
    "2": ("AFLAO-LOME", "GH", "TG", "Aflao-Lomé (Ghana-Togo)"),
    "3": ("NOEPKE", "TG", "BJ", "Noépké (Togo-Bénin)"),
    "4": ("PAGA", "GH", "BF", "Paga (Ghana-Burkina)"),
    "5": ("KIDIRA", "SN", "ML", "Kidira (Sénégal-Mali)"),
    "6": ("NIANGOLOKO", "BF", "CI", "Niangoloko (Burkina-CI)"),
    "7": ("MALANVILLE", "BJ", "NE", "Malanville (Bénin-Niger)"),
    "8": ("ROSSO", "SN", "MR", "Rosso (Sénégal-Mauritanie)"),
    "9": ("CINKASSE", "TG", "BF", "Cinkassé (Togo-Burkina)"),
    "10": ("JIBIYA", "NG", "NE", "Jibiya (Nigeria-Niger)"),
}

# ── Port codes for clearance reports ──────────────────────────────────
PORTS = {
    "1": ("NGAPP", "NG", "Port Apapa, Lagos"),
    "2": ("NGTIN", "NG", "Port Tin Can Island, Lagos"),
    "3": ("CIABJ", "CI", "Port Autonome d'Abidjan"),
    "4": ("CISPY", "CI", "Port de San Pedro"),
    "5": ("GHTEM", "GH", "Port de Tema"),
    "6": ("GHTKO", "GH", "Port de Takoradi"),
    "7": ("SNDKR", "SN", "Port Autonome de Dakar"),
    "8": ("TGLFW", "TG", "Port Autonome de Lomé"),
    "9": ("BJCOO", "BJ", "Port Autonome de Cotonou"),
    "10": ("GNCON", "GN", "Port de Conakry"),
}

# ── Goods categories for trade declarations ───────────────────────────
GOODS_CATEGORIES = {
    "1": ("FOOD_GRAINS", "Céréales / Alimentation"),
    "2": ("LIVESTOCK", "Bétail"),
    "3": ("TEXTILES", "Textiles / Vêtements"),
    "4": ("ELECTRONICS", "Électronique"),
    "5": ("FUEL", "Carburant / Pétrole"),
    "6": ("CONSTRUCTION", "Matériaux construction"),
    "7": ("VEHICLES", "Véhicules / Pièces"),
    "8": ("OTHER", "Autres marchandises"),
}


def _hash_phone(phone: str) -> str:
    """SHA-256 hash of phone number for privacy compliance."""
    return hashlib.sha256(phone.strip().encode()).hexdigest()


def _to_usd(amount_local: float, currency: str) -> float:
    """Convert local currency to USD using default FX rates."""
    rate = DEFAULT_FX_RATES.get(currency, 1.0)
    return round(amount_local / rate, 2) if rate > 0 else 0.0


class USSDMenuEngine:
    """
    Handles the USSD menu tree navigation and data capture.

    Protocol: Africa's Talking / Infobip style
      - Input: sessionId, serviceCode, phoneNumber, text
      - text = "" on first dial, "1" after selecting option 1,
        "1*500" after selecting option 1 then entering 500, etc.
      - Response starts with "CON " (continue session) or "END " (end session)
    """

    def __init__(self, db: Session):
        self.db = db

    def process_callback(
        self,
        session_id: str,
        service_code: str,
        phone_number: str,
        text: str,
        provider_code: str = "GENERIC",
    ) -> Tuple[str, str]:
        """
        Process a USSD callback and return (response_text, session_type).

        Returns:
            (response_text, session_type) — response starts with CON or END
        """
        phone_hash = _hash_phone(phone_number)
        parts = text.split("*") if text else []
        level = len(parts)

        # Determine country from provider mapping or phone prefix
        country_code = self._detect_country(phone_number, provider_code)

        if level == 0:
            # Main menu
            response = (
                "CON Bienvenue sur WASI\n"
                "West African Shipping Intelligence\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "1. Prix du marché\n"
                "2. Déclaration commerce\n"
                "3. Port / Douanes\n"
                "4. Indice WASI pays\n"
                "5. Mon compte\n"
                "6. eCFA Portefeuille"
            )
            session_type = "MENU"
        elif parts[0] == "1":
            response, session_type = self._handle_commodity_menu(
                parts[1:], country_code, phone_hash
            )
        elif parts[0] == "2":
            response, session_type = self._handle_trade_menu(
                parts[1:], country_code, phone_hash
            )
        elif parts[0] == "3":
            response, session_type = self._handle_port_menu(
                parts[1:], country_code, phone_hash
            )
        elif parts[0] == "4":
            response, session_type = self._handle_index_query(
                parts[1:], country_code
            )
        elif parts[0] == "5":
            response, session_type = self._handle_account_menu(
                parts[1:], phone_hash
            )
        elif parts[0] == "6":
            # eCFA CBDC Wallet — delegates to CbdcUSSDEngine
            from src.engines.cbdc_ussd_engine import CbdcUSSDEngine
            ecfa_engine = CbdcUSSDEngine(self.db)
            response, session_type = ecfa_engine.handle_ecfa_menu(
                parts[1:], phone_number, country_code
            )
        else:
            response = "END Option invalide. Composez à nouveau *384*WASI#"
            session_type = "ERROR"

        # Log session
        self._log_session(
            session_id=session_id,
            provider_code=provider_code,
            phone_hash=phone_hash,
            country_code=country_code,
            service_code=service_code,
            session_type=session_type,
            menu_level=level,
            user_input=text,
            response_text=response,
            status="active" if response.startswith("CON") else "completed",
        )

        return response, session_type

    # ── Menu handlers ─────────────────────────────────────────────────

    def _handle_commodity_menu(
        self, parts: list, country_code: str, phone_hash: str
    ) -> Tuple[str, str]:
        """Market price reporting flow."""
        if len(parts) == 0:
            # List commodities
            lines = ["CON Sélectionnez le produit:"]
            for k, (_, name) in COMMODITY_CODES.items():
                lines.append(f"{k}. {name}")
            return "\n".join(lines), "COMMODITY_PRICE"

        if len(parts) == 1:
            code_key = parts[0]
            if code_key not in COMMODITY_CODES:
                return "END Produit invalide.", "ERROR"
            _, name = COMMODITY_CODES[code_key]
            currency = COUNTRY_CURRENCY.get(country_code, "XOF")
            return (
                f"CON {name}\n"
                f"Entrez le prix par kg en {currency}:"
            ), "COMMODITY_PRICE"

        if len(parts) == 2:
            code_key = parts[0]
            try:
                price = float(parts[1])
            except ValueError:
                return "END Prix invalide. Réessayez.", "ERROR"
            _, name = COMMODITY_CODES.get(code_key, ("?", "?"))
            currency = COUNTRY_CURRENCY.get(country_code, "XOF")
            return (
                f"CON Confirmer:\n"
                f"{name} = {price:.0f} {currency}/kg\n"
                f"1. Confirmer\n"
                f"2. Annuler"
            ), "COMMODITY_PRICE"

        if len(parts) == 3:
            if parts[2] == "1":
                # Save the report
                code_key = parts[0]
                try:
                    price = float(parts[1])
                except ValueError:
                    return "END Erreur de prix.", "ERROR"
                commodity_code, commodity_name = COMMODITY_CODES.get(
                    code_key, ("OTHER", "Autre")
                )
                currency = COUNTRY_CURRENCY.get(country_code, "XOF")
                self._save_commodity_report(
                    country_code=country_code,
                    commodity_code=commodity_code,
                    commodity_name=commodity_name,
                    price_local=price,
                    currency=currency,
                    phone_hash=phone_hash,
                )
                return (
                    f"END Merci! Prix enregistré:\n"
                    f"{commodity_name} = {price:.0f} {currency}/kg\n"
                    f"WASI vous remercie pour votre contribution."
                ), "COMMODITY_PRICE"
            else:
                return "END Annulé. Merci.", "COMMODITY_PRICE"

        return "END Session expirée. Recomposez *384*WASI#", "COMMODITY_PRICE"

    def _handle_trade_menu(
        self, parts: list, country_code: str, phone_hash: str
    ) -> Tuple[str, str]:
        """Cross-border trade declaration flow."""
        if len(parts) == 0:
            lines = ["CON Poste frontière:"]
            for k, (_, _, _, desc) in BORDER_POSTS.items():
                lines.append(f"{k}. {desc}")
            return "\n".join(lines), "TRADE_DECLARATION"

        if len(parts) == 1:
            if parts[0] not in BORDER_POSTS:
                return "END Poste invalide.", "ERROR"
            lines = ["CON Catégorie marchandise:"]
            for k, (_, name) in GOODS_CATEGORIES.items():
                lines.append(f"{k}. {name}")
            return "\n".join(lines), "TRADE_DECLARATION"

        if len(parts) == 2:
            if parts[1] not in GOODS_CATEGORIES:
                return "END Catégorie invalide.", "ERROR"
            return (
                "CON Direction:\n"
                "1. Export (sortie)\n"
                "2. Import (entrée)\n"
                "3. Transit"
            ), "TRADE_DECLARATION"

        if len(parts) == 3:
            currency = COUNTRY_CURRENCY.get(country_code, "XOF")
            return (
                f"CON Valeur totale en {currency}\n"
                f"(ex: 500000):"
            ), "TRADE_DECLARATION"

        if len(parts) == 4:
            try:
                value = float(parts[3])
            except ValueError:
                return "END Valeur invalide.", "ERROR"
            post_key = parts[0]
            goods_key = parts[1]
            dir_key = parts[2]
            post_name = BORDER_POSTS.get(post_key, ("?", "?", "?", "?"))[3]
            goods_name = GOODS_CATEGORIES.get(goods_key, ("?", "?"))[1]
            directions = {"1": "EXPORT", "2": "IMPORT", "3": "TRANSIT"}
            direction = directions.get(dir_key, "EXPORT")
            currency = COUNTRY_CURRENCY.get(country_code, "XOF")
            return (
                f"CON Confirmer déclaration:\n"
                f"Poste: {post_name}\n"
                f"Produit: {goods_name}\n"
                f"Dir: {direction}\n"
                f"Valeur: {value:.0f} {currency}\n"
                f"1. Confirmer\n"
                f"2. Annuler"
            ), "TRADE_DECLARATION"

        if len(parts) == 5:
            if parts[4] == "1":
                post_key, goods_key, dir_key = parts[0], parts[1], parts[2]
                try:
                    value = float(parts[3])
                except ValueError:
                    return "END Erreur.", "ERROR"
                post_code, origin, dest, _ = BORDER_POSTS.get(
                    post_key, ("?", country_code, "??", "?")
                )
                goods_code, _ = GOODS_CATEGORIES.get(goods_key, ("OTHER", "Autre"))
                directions = {"1": "EXPORT", "2": "IMPORT", "3": "TRANSIT"}
                direction = directions.get(dir_key, "EXPORT")
                currency = COUNTRY_CURRENCY.get(country_code, "XOF")

                self._save_trade_declaration(
                    country_code=country_code,
                    border_post=post_code,
                    origin=origin,
                    destination=dest,
                    direction=direction,
                    commodity_category=goods_code,
                    value_local=value,
                    currency=currency,
                    phone_hash=phone_hash,
                )
                return (
                    f"END Déclaration enregistrée!\n"
                    f"Réf: WASI-{datetime.utcnow().strftime('%Y%m%d%H%M')}\n"
                    f"Merci pour votre contribution."
                ), "TRADE_DECLARATION"
            else:
                return "END Annulé.", "TRADE_DECLARATION"

        return "END Session expirée.", "TRADE_DECLARATION"

    def _handle_port_menu(
        self, parts: list, country_code: str, phone_hash: str
    ) -> Tuple[str, str]:
        """Port clearance reporting flow."""
        if len(parts) == 0:
            lines = ["CON Sélectionnez le port:"]
            for k, (_, _, desc) in PORTS.items():
                lines.append(f"{k}. {desc}")
            return "\n".join(lines), "PORT_CLEARANCE"

        if len(parts) == 1:
            if parts[0] not in PORTS:
                return "END Port invalide.", "ERROR"
            return (
                "CON Niveau de congestion:\n"
                "1. Faible (< 3 jours)\n"
                "2. Moyen (3-7 jours)\n"
                "3. Élevé (7-14 jours)\n"
                "4. Critique (> 14 jours)"
            ), "PORT_CLEARANCE"

        if len(parts) == 2:
            return (
                "CON Délai douane actuel (heures):\n"
                "(ex: 48)"
            ), "PORT_CLEARANCE"

        if len(parts) == 3:
            try:
                delay = float(parts[2])
            except ValueError:
                return "END Délai invalide.", "ERROR"
            port_key = parts[0]
            congestion_map = {"1": "LOW", "2": "MEDIUM", "3": "HIGH", "4": "CRITICAL"}
            congestion = congestion_map.get(parts[1], "MEDIUM")
            _, _, port_name = PORTS.get(port_key, ("?", "?", "?"))
            return (
                f"CON Confirmer rapport port:\n"
                f"{port_name}\n"
                f"Congestion: {congestion}\n"
                f"Délai douane: {delay:.0f}h\n"
                f"1. Confirmer\n"
                f"2. Annuler"
            ), "PORT_CLEARANCE"

        if len(parts) == 4:
            if parts[3] == "1":
                port_key = parts[0]
                congestion_map = {"1": "LOW", "2": "MEDIUM", "3": "HIGH", "4": "CRITICAL"}
                congestion = congestion_map.get(parts[1], "MEDIUM")
                try:
                    delay = float(parts[2])
                except ValueError:
                    delay = 0.0
                port_code, port_cc, port_name = PORTS.get(
                    port_key, ("?", country_code, "?")
                )
                self._save_port_clearance(
                    country_code=port_cc,
                    port_code=port_code,
                    port_name=port_name,
                    congestion_level=congestion,
                    customs_delay_hours=delay,
                    phone_hash=phone_hash,
                )
                return (
                    f"END Rapport enregistré!\n"
                    f"{port_name}\n"
                    f"Merci, agent WASI."
                ), "PORT_CLEARANCE"
            else:
                return "END Annulé.", "PORT_CLEARANCE"

        return "END Session expirée.", "PORT_CLEARANCE"

    def _handle_index_query(
        self, parts: list, country_code: str
    ) -> Tuple[str, str]:
        """Show WASI index for the user's country."""
        from src.database.models import CountryIndex

        country = (
            self.db.query(Country)
            .filter(Country.code == country_code)
            .first()
        )
        if not country:
            return f"END Pays {country_code} non trouvé dans WASI.", "INDEX_QUERY"

        latest = (
            self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.desc())
            .first()
        )
        if not latest:
            return (
                f"END WASI — {country.name} ({country.code})\n"
                f"Pas de données disponibles.\n"
                f"Contribuez via le menu principal!"
            ), "INDEX_QUERY"

        def _fmt(val):
            return f"{val:.1f}" if val is not None else "N/D"

        return (
            f"END WASI — {country.name} ({country.code})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Indice: {latest.index_value:.1f}/100\n"
            f"Transport: {_fmt(latest.shipping_score)}\n"
            f"Commerce: {_fmt(latest.trade_score)}\n"
            f"Infra: {_fmt(latest.infrastructure_score)}\n"
            f"Économie: {_fmt(latest.economic_score)}\n"
            f"Date: {latest.period_date}\n"
            f"Poids ECOWAS: {country.weight*100:.0f}%"
        ), "INDEX_QUERY"

    def _handle_account_menu(
        self, parts: list, phone_hash: str
    ) -> Tuple[str, str]:
        """User account management."""
        if len(parts) == 0:
            return (
                "CON Mon compte WASI:\n"
                "1. Statistiques contributions\n"
                "2. S'abonner aux alertes\n"
                "3. Aide"
            ), "ACCOUNT"

        if parts[0] == "1":
            # Count user's contributions
            session_count = (
                self.db.query(USSDSession)
                .filter(
                    USSDSession.phone_hash == phone_hash,
                    USSDSession.status == "completed",
                )
                .count()
            )
            return (
                f"END Vos contributions WASI:\n"
                f"Sessions: {session_count}\n"
                f"Merci pour votre participation!"
            ), "ACCOUNT"

        if parts[0] == "2":
            return (
                "END Alertes WASI activées!\n"
                "Vous recevrez un SMS quand\n"
                "l'indice de votre pays change\n"
                "de +/- 5 points."
            ), "ACCOUNT"

        return (
            "END WASI — Aide\n"
            "Composez *384*WASI# pour:\n"
            "- Rapporter prix marchés\n"
            "- Déclarer commerce transfrontalier\n"
            "- Signaler congestion portuaire\n"
            "- Consulter l'indice WASI\n"
            "Contact: support@wasi.africa"
        ), "ACCOUNT"

    # ── Data persistence ──────────────────────────────────────────────

    def _detect_country(self, phone_number: str, provider_code: str) -> str:
        """Detect country from phone prefix or provider mapping."""
        phone = phone_number.strip().lstrip("+")
        # West African phone prefixes
        prefix_map = {
            "225": "CI", "221": "SN", "223": "ML", "226": "BF",
            "229": "BJ", "228": "TG", "227": "NE", "234": "NG",
            "233": "GH", "224": "GN", "232": "SL", "231": "LR",
            "220": "GM", "222": "MR", "238": "CV", "245": "GW",
        }
        for prefix, code in prefix_map.items():
            if phone.startswith(prefix):
                return code

        # Fallback: check provider's country_codes
        provider = (
            self.db.query(USSDProvider)
            .filter(USSDProvider.provider_code == provider_code)
            .first()
        )
        if provider and provider.country_codes:
            return provider.country_codes.split(",")[0].strip()

        return "CI"  # Default to Ivory Coast (largest ECOWAS USSD market)

    def _get_country_id(self, country_code: str) -> Optional[int]:
        """Resolve ISO-2 country code to DB country ID."""
        country = (
            self.db.query(Country)
            .filter(Country.code == country_code)
            .first()
        )
        return country.id if country else None

    def _log_session(self, **kwargs) -> None:
        """Persist USSD session record."""
        provider = (
            self.db.query(USSDProvider)
            .filter(USSDProvider.provider_code == kwargs["provider_code"])
            .first()
        )
        provider_id = provider.id if provider else None

        # Skip logging if no provider registered (dev mode)
        if provider_id is None:
            return

        session = USSDSession(
            session_id=kwargs["session_id"],
            provider_id=provider_id,
            phone_hash=kwargs["phone_hash"],
            country_code=kwargs["country_code"],
            service_code=kwargs["service_code"],
            session_type=kwargs["session_type"],
            menu_level=kwargs["menu_level"],
            user_input=kwargs["user_input"],
            response_text=kwargs["response_text"][:500],
            status=kwargs["status"],
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow() if kwargs["status"] == "completed" else None,
        )
        self.db.add(session)
        self.db.commit()

    def _save_commodity_report(
        self, country_code: str, commodity_code: str, commodity_name: str,
        price_local: float, currency: str, phone_hash: str,
    ) -> None:
        """Save a commodity price report from USSD."""
        country_id = self._get_country_id(country_code)
        if not country_id:
            return

        today = date.today()
        price_usd = _to_usd(price_local, currency)

        existing = (
            self.db.query(USSDCommodityReport)
            .filter(
                USSDCommodityReport.country_id == country_id,
                USSDCommodityReport.period_date == today,
                USSDCommodityReport.market_name == "USSD_AGGREGATE",
                USSDCommodityReport.commodity_code == commodity_code,
            )
            .first()
        )

        if existing:
            # Running average
            n = existing.report_count
            existing.price_local = (existing.price_local * n + price_local) / (n + 1)
            existing.price_usd = _to_usd(existing.price_local, currency)
            existing.report_count = n + 1
            existing.confidence = min(0.90, 0.50 + 0.05 * existing.report_count)
        else:
            report = USSDCommodityReport(
                country_id=country_id,
                period_date=today,
                market_name="USSD_AGGREGATE",
                market_type="MIXED",
                commodity_code=commodity_code,
                commodity_name=commodity_name,
                price_local=price_local,
                price_usd=price_usd,
                local_currency=currency,
                reporter_phone_hash=phone_hash,
                confidence=0.55,
            )
            self.db.add(report)

        self.db.commit()

    def _save_trade_declaration(
        self, country_code: str, border_post: str, origin: str,
        destination: str, direction: str, commodity_category: str,
        value_local: float, currency: str, phone_hash: str,
    ) -> None:
        """Save a cross-border trade declaration."""
        country_id = self._get_country_id(country_code)
        if not country_id:
            return

        today = date.today()
        value_usd = _to_usd(value_local, currency)

        existing = (
            self.db.query(USSDTradeDeclaration)
            .filter(
                USSDTradeDeclaration.country_id == country_id,
                USSDTradeDeclaration.period_date == today,
                USSDTradeDeclaration.border_post == border_post,
                USSDTradeDeclaration.commodity_category == commodity_category,
                USSDTradeDeclaration.direction == direction,
            )
            .first()
        )

        if existing:
            existing.declared_value_local = (
                existing.declared_value_local + value_local
            )
            existing.declared_value_usd = (
                existing.declared_value_usd + value_usd
            )
            existing.declaration_count += 1
            existing.confidence = min(0.80, 0.40 + 0.05 * existing.declaration_count)
        else:
            decl = USSDTradeDeclaration(
                country_id=country_id,
                period_date=today,
                border_post=border_post,
                origin_country=origin,
                destination_country=destination,
                direction=direction,
                commodity_category=commodity_category,
                declared_value_local=value_local,
                declared_value_usd=value_usd,
                local_currency=currency,
                trader_phone_hash=phone_hash,
                confidence=0.45,
            )
            self.db.add(decl)

        self.db.commit()

    def _save_port_clearance(
        self, country_code: str, port_code: str, port_name: str,
        congestion_level: str, customs_delay_hours: float,
        phone_hash: str,
    ) -> None:
        """Save a port clearance report."""
        country_id = self._get_country_id(country_code)
        if not country_id:
            return

        today = date.today()

        existing = (
            self.db.query(USSDPortClearance)
            .filter(
                USSDPortClearance.country_id == country_id,
                USSDPortClearance.period_date == today,
                USSDPortClearance.port_name == port_name,
            )
            .first()
        )

        if existing:
            n = existing.reporter_count
            existing.avg_clearance_hours = (
                (existing.avg_clearance_hours or 0) * n + customs_delay_hours
            ) / (n + 1)
            existing.customs_delay_hours = existing.avg_clearance_hours
            existing.congestion_level = congestion_level
            existing.reporter_count = n + 1
            existing.confidence = min(0.90, 0.55 + 0.05 * existing.reporter_count)
        else:
            clearance = USSDPortClearance(
                country_id=country_id,
                period_date=today,
                port_name=port_name,
                port_code=port_code,
                avg_clearance_hours=customs_delay_hours,
                customs_delay_hours=customs_delay_hours,
                congestion_level=congestion_level,
                confidence=0.55,
            )
            self.db.add(clearance)

        self.db.commit()


class USSDDataAggregator:
    """
    Aggregates daily USSD data into country-level signals for WASI index.

    Runs daily (or on-demand) to compute:
      - mobile_money_score: Transaction velocity (0–100)
      - commodity_price_score: Market stability (0–100)
      - informal_trade_score: Trade flow intensity (0–100)
      - port_efficiency_score: Clearance speed (0–100)
      - ussd_composite_score: Weighted average (0–100)

    Weights: money=30%, commodity=20%, trade=25%, port=25%
    """

    WEIGHTS = {
        "mobile_money": 0.30,
        "commodity": 0.20,
        "informal_trade": 0.25,
        "port_efficiency": 0.25,
    }

    def __init__(self, db: Session):
        self.db = db

    def aggregate_country(self, country_code: str, target_date: date = None) -> dict:
        """Compute daily USSD aggregate for a single country."""
        target_date = target_date or date.today()
        country = (
            self.db.query(Country)
            .filter(Country.code == country_code)
            .first()
        )
        if not country:
            return {}

        # Score each sub-signal
        money_score = self._score_mobile_money(country.id, target_date)
        commodity_score = self._score_commodity_prices(country.id, target_date)
        trade_score = self._score_informal_trade(country.id, target_date)
        port_score = self._score_port_efficiency(country.id, target_date)

        # Count data points
        data_points = self._count_data_points(country.id, target_date)
        providers = self._count_providers(country.id, target_date)

        # Weighted composite (only include non-None scores)
        scores = {}
        if money_score is not None:
            scores["mobile_money"] = money_score
        if commodity_score is not None:
            scores["commodity"] = commodity_score
        if trade_score is not None:
            scores["informal_trade"] = trade_score
        if port_score is not None:
            scores["port_efficiency"] = port_score

        if scores:
            total_weight = sum(self.WEIGHTS[k] for k in scores)
            composite = sum(
                scores[k] * self.WEIGHTS[k] / total_weight
                for k in scores
            )
        else:
            composite = None

        # Confidence based on data richness
        confidence = min(0.90, 0.30 + 0.10 * providers + 0.002 * data_points)

        # Persist
        existing = (
            self.db.query(USSDDailyAggregate)
            .filter(
                USSDDailyAggregate.country_id == country.id,
                USSDDailyAggregate.period_date == target_date,
            )
            .first()
        )

        result = {
            "country_code": country_code,
            "period_date": str(target_date),
            "mobile_money_score": money_score,
            "commodity_price_score": commodity_score,
            "informal_trade_score": trade_score,
            "port_efficiency_score": port_score,
            "ussd_composite_score": round(composite, 4) if composite else None,
            "data_points": data_points,
            "providers_reporting": providers,
            "confidence": round(confidence, 4),
        }

        if existing:
            existing.mobile_money_score = money_score
            existing.commodity_price_score = commodity_score
            existing.informal_trade_score = trade_score
            existing.port_efficiency_score = port_score
            existing.ussd_composite_score = composite
            existing.data_points_count = data_points
            existing.providers_reporting = providers
            existing.confidence = confidence
            existing.calculated_at = datetime.utcnow()
        else:
            agg = USSDDailyAggregate(
                country_id=country.id,
                period_date=target_date,
                mobile_money_score=money_score,
                commodity_price_score=commodity_score,
                informal_trade_score=trade_score,
                port_efficiency_score=port_score,
                ussd_composite_score=composite,
                data_points_count=data_points,
                providers_reporting=providers,
                confidence=confidence,
            )
            self.db.add(agg)

        self.db.commit()
        return result

    def aggregate_all(self, target_date: date = None) -> list:
        """Aggregate USSD data for all 16 WASI countries."""
        target_date = target_date or date.today()
        countries = self.db.query(Country).filter(Country.is_active == True).all()
        results = []
        for c in countries:
            result = self.aggregate_country(c.code, target_date)
            if result:
                results.append(result)
        return results

    # ── Sub-signal scorers ────────────────────────────────────────────

    def _score_mobile_money(self, country_id: int, target_date: date) -> Optional[float]:
        """Score 0–100 based on mobile money transaction velocity."""
        flows = (
            self.db.query(USSDMobileMoneyFlow)
            .filter(
                USSDMobileMoneyFlow.country_id == country_id,
                USSDMobileMoneyFlow.period_date == target_date,
            )
            .all()
        )
        if not flows:
            return None

        total_txns = sum(f.transaction_count for f in flows)
        total_usd = sum(f.total_value_usd for f in flows)

        # Compare to previous period average (works for both daily and monthly data)
        # Look back 90 days to find prior records for comparison
        lookback = target_date - timedelta(days=90)
        avg_txns = (
            self.db.query(func.avg(USSDMobileMoneyFlow.transaction_count))
            .filter(
                USSDMobileMoneyFlow.country_id == country_id,
                USSDMobileMoneyFlow.period_date.between(lookback, target_date - timedelta(days=1)),
            )
            .scalar()
        )

        if avg_txns and avg_txns > 0:
            # Velocity ratio: current vs historical average
            velocity = total_txns / avg_txns
            # Normalize: 0.5x = 0, 1.0x = 50, 2.0x = 100
            score = min(100, max(0, (velocity - 0.5) / 1.5 * 100))
        else:
            # No prior data — score based on absolute volume (higher = better)
            # Scale: 100K txns/month = 50, 1M+ = 80+
            score = min(85, 30 + (total_txns / 1_000_000) * 50)

        return round(score, 2)

    def _score_commodity_prices(self, country_id: int, target_date: date) -> Optional[float]:
        """Score 0–100 based on commodity price stability (low volatility = high score)."""
        reports = (
            self.db.query(USSDCommodityReport)
            .filter(
                USSDCommodityReport.country_id == country_id,
                USSDCommodityReport.period_date == target_date,
            )
            .all()
        )
        if not reports:
            return None

        # Try explicit pct_change_week first
        changes = [abs(r.pct_change_week) for r in reports if r.pct_change_week is not None]

        # If no pre-computed changes, calculate MoM from previous period
        if not changes:
            prev_date = target_date - timedelta(days=30)
            prev_reports = {
                (r.commodity_code, r.market_name): r.price_local
                for r in self.db.query(USSDCommodityReport)
                .filter(
                    USSDCommodityReport.country_id == country_id,
                    USSDCommodityReport.period_date >= prev_date,
                    USSDCommodityReport.period_date < target_date,
                )
                .all()
            }
            for r in reports:
                key = (r.commodity_code, r.market_name)
                if key in prev_reports and prev_reports[key] > 0:
                    pct = abs((r.price_local - prev_reports[key]) / prev_reports[key] * 100)
                    changes.append(pct)

        if not changes:
            # Data exists but no comparison possible — give a neutral-positive score
            # based on number of commodity reports (more data = better)
            return min(70.0, 50.0 + len(reports) * 0.5)

        avg_change = sum(changes) / len(changes)
        # 0% change = 100 score, 50% change = 0 score
        score = max(0, 100 - avg_change * 2)
        return round(score, 2)

    def _score_informal_trade(self, country_id: int, target_date: date) -> Optional[float]:
        """Score 0–100 based on informal cross-border trade volume."""
        declarations = (
            self.db.query(USSDTradeDeclaration)
            .filter(
                USSDTradeDeclaration.country_id == country_id,
                USSDTradeDeclaration.period_date == target_date,
            )
            .all()
        )
        if not declarations:
            return None

        total_usd = sum(d.declared_value_usd or 0 for d in declarations)
        total_count = sum(d.declaration_count or 0 for d in declarations)

        # Volume scoring: compare to regional benchmarks
        # Monthly truck counts: major corridor = 5000+, minor = 500+
        # Scale using both count and value
        count_score = min(100, total_count / 50)  # 5000 trucks/month → 100
        value_score = min(100, total_usd / 5_000_000)  # $500M/month → 100
        score = count_score * 0.4 + value_score * 0.6
        return round(min(100, max(0, score)), 2)

    def _score_port_efficiency(self, country_id: int, target_date: date) -> Optional[float]:
        """Score 0–100 based on port clearance speed (faster = higher)."""
        clearances = (
            self.db.query(USSDPortClearance)
            .filter(
                USSDPortClearance.country_id == country_id,
                USSDPortClearance.period_date == target_date,
            )
            .all()
        )
        if not clearances:
            return None

        avg_delay = sum(c.avg_clearance_hours or 0 for c in clearances) / len(clearances)
        # UNCTAD data is in hours; West African avg dwell = 10-20 days (240-480h)
        # Invert: 0h = 100, 480h (20 days) = 0
        score = max(0, 100 - (avg_delay / 480) * 100)
        return round(score, 2)

    def _count_data_points(self, country_id: int, target_date: date) -> int:
        """Count total USSD data points for the day."""
        money = (
            self.db.query(func.sum(USSDMobileMoneyFlow.transaction_count))
            .filter(
                USSDMobileMoneyFlow.country_id == country_id,
                USSDMobileMoneyFlow.period_date == target_date,
            )
            .scalar()
        ) or 0
        commodity = (
            self.db.query(func.sum(USSDCommodityReport.report_count))
            .filter(
                USSDCommodityReport.country_id == country_id,
                USSDCommodityReport.period_date == target_date,
            )
            .scalar()
        ) or 0
        trade = (
            self.db.query(func.sum(USSDTradeDeclaration.declaration_count))
            .filter(
                USSDTradeDeclaration.country_id == country_id,
                USSDTradeDeclaration.period_date == target_date,
            )
            .scalar()
        ) or 0
        port = (
            self.db.query(func.sum(USSDPortClearance.reporter_count))
            .filter(
                USSDPortClearance.country_id == country_id,
                USSDPortClearance.period_date == target_date,
            )
            .scalar()
        ) or 0
        return int(money + commodity + trade + port)

    def _count_providers(self, country_id: int, target_date: date) -> int:
        """Count distinct MNO providers reporting for this country today."""
        count = (
            self.db.query(func.count(func.distinct(USSDMobileMoneyFlow.provider_code)))
            .filter(
                USSDMobileMoneyFlow.country_id == country_id,
                USSDMobileMoneyFlow.period_date == target_date,
            )
            .scalar()
        ) or 0
        return int(count)
