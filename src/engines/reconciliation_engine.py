"""
Data Reconciliation & Anomaly Detection Engine.

Validates data integrity across all WASI data sources:
- Statistical anomaly detection (Z-score, rate-of-change)
- Cross-source reconciliation (World Bank vs IMF GDP)
- Data freshness monitoring per source
- Missing critical field detection
- Source reliability scoring
- Data lineage recording
"""
import json
import logging
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from src.database.models import Base, Country, CountryIndex, MacroIndicator
from src.database.reconciliation_models import (
    DataSourceHealth, DataQuarantine, DataLineage, ReconciliationRun,
)

logger = logging.getLogger(__name__)

# ── Known data sources ────────────────────────────────────────────
KNOWN_SOURCES = [
    "worldbank", "imf", "acled", "comtrade", "commodity_wb",
]

# ── Stale data thresholds (days) ──────────────────────────────────
MAX_STALE_DAYS = 30
MAX_OFFLINE_DAYS = 90

# ── ECOWAS country codes ─────────────────────────────────────────
ECOWAS_CODES = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
    "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]


def seed_source_health(db: Session):
    """Seed DataSourceHealth rows for known sources if table empty."""
    existing = db.query(DataSourceHealth).count()
    if existing > 0:
        return
    now = datetime.now(timezone.utc)
    for name in KNOWN_SOURCES:
        db.add(DataSourceHealth(
            source_name=name,
            status="UNKNOWN",
            reliability_score=1.0,
            updated_at=now,
        ))
    db.commit()
    logger.info("Seeded %d data source health entries", len(KNOWN_SOURCES))


class ReconciliationEngine:
    """Core engine for data quality verification and anomaly detection."""

    def __init__(self, db: Session):
        self.db = db

    # ── 1. Statistical Anomaly Detection (Z-score) ────────────────

    def check_z_score_anomalies(
        self,
        table_class,
        field_name: str,
        country_id: Optional[int] = None,
        lookback_days: int = 90,
        z_threshold: float = 3.0,
    ) -> list[dict]:
        """Flag records where field value exceeds z_threshold standard deviations."""
        cutoff = date.today() - timedelta(days=lookback_days)
        field = getattr(table_class, field_name, None)
        if field is None:
            return []

        query = self.db.query(table_class).filter(
            field.isnot(None),
        )

        # Filter by date field
        if hasattr(table_class, "period_date"):
            query = query.filter(table_class.period_date >= cutoff)
        elif hasattr(table_class, "created_at"):
            query = query.filter(table_class.created_at >= datetime(
                cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc,
            ))

        if country_id is not None and hasattr(table_class, "country_id"):
            query = query.filter(table_class.country_id == country_id)

        records = query.all()
        if len(records) < 5:
            return []

        values = np.array([getattr(r, field_name) for r in records], dtype=float)
        mean = float(np.mean(values))
        std = float(np.std(values))
        if std < 1e-10:
            return []

        flagged = []
        for rec in records:
            val = float(getattr(rec, field_name))
            z = abs(val - mean) / std
            if z > z_threshold:
                severity = "CRITICAL" if z > 4.0 else "HIGH"
                country_code = None
                if hasattr(rec, "country_id"):
                    country = self.db.query(Country).filter(
                        Country.id == rec.country_id
                    ).first()
                    if country:
                        country_code = country.code

                detail = json.dumps({
                    "field": field_name,
                    "value": val,
                    "mean": round(mean, 4),
                    "std_dev": round(std, 4),
                    "z_score": round(z, 2),
                    "threshold": z_threshold,
                })
                q = DataQuarantine(
                    table_name=table_class.__tablename__,
                    record_id=rec.id,
                    country_code=country_code,
                    anomaly_type="Z_SCORE",
                    anomaly_detail=detail,
                    severity=severity,
                )
                self.db.add(q)
                flagged.append({
                    "record_id": rec.id,
                    "value": val,
                    "z_score": round(z, 2),
                    "severity": severity,
                })

        if flagged:
            self.db.flush()
        return flagged

    # ── 2. Rate-of-Change Detection ───────────────────────────────

    def check_rate_of_change(
        self,
        table_class,
        field_name: str,
        max_pct_change: float = 50.0,
    ) -> list[dict]:
        """Flag records where consecutive values change by more than max_pct_change%."""
        if not hasattr(table_class, "country_id"):
            return []

        field = getattr(table_class, field_name, None)
        if field is None:
            return []

        flagged = []
        country_ids = [
            r[0] for r in
            self.db.query(table_class.country_id).distinct().all()
        ]

        order_field = (
            table_class.period_date if hasattr(table_class, "period_date")
            else table_class.id
        )

        for cid in country_ids:
            rows = (
                self.db.query(table_class)
                .filter(
                    table_class.country_id == cid,
                    field.isnot(None),
                )
                .order_by(desc(order_field))
                .limit(2)
                .all()
            )
            if len(rows) < 2:
                continue

            current_val = float(getattr(rows[0], field_name))
            prev_val = float(getattr(rows[1], field_name))

            if abs(prev_val) < 1e-10:
                continue

            pct_change = abs((current_val - prev_val) / prev_val) * 100
            if pct_change > max_pct_change:
                if pct_change > 100:
                    severity = "CRITICAL"
                elif pct_change > 75:
                    severity = "HIGH"
                else:
                    severity = "MEDIUM"

                country = self.db.query(Country).filter(Country.id == cid).first()
                cc = country.code if country else None

                detail = json.dumps({
                    "field": field_name,
                    "current": current_val,
                    "previous": prev_val,
                    "pct_change": round(pct_change, 2),
                    "threshold": max_pct_change,
                })
                q = DataQuarantine(
                    table_name=table_class.__tablename__,
                    record_id=rows[0].id,
                    country_code=cc,
                    anomaly_type="RATE_OF_CHANGE",
                    anomaly_detail=detail,
                    severity=severity,
                )
                self.db.add(q)
                flagged.append({
                    "country_code": cc,
                    "record_id": rows[0].id,
                    "pct_change": round(pct_change, 2),
                    "severity": severity,
                })

        if flagged:
            self.db.flush()
        return flagged

    # ── 3. Cross-Source GDP Validation ─────────────────────────────

    def cross_validate_gdp(self, tolerance_pct: float = 20.0) -> list[dict]:
        """Compare World Bank GDP growth vs IMF GDP growth for same country/year."""
        flagged = []

        countries = self.db.query(Country).filter(
            Country.code.in_(ECOWAS_CODES)
        ).all()

        for country in countries:
            # Latest CountryIndex with gdp_growth_pct (World Bank source)
            wb_rec = (
                self.db.query(CountryIndex)
                .filter(
                    CountryIndex.country_id == country.id,
                    CountryIndex.gdp_growth_pct.isnot(None),
                )
                .order_by(desc(CountryIndex.period_date))
                .first()
            )
            if not wb_rec or wb_rec.gdp_growth_pct is None:
                continue

            # Latest MacroIndicator (IMF source)
            imf_rec = (
                self.db.query(MacroIndicator)
                .filter(
                    MacroIndicator.country_id == country.id,
                    MacroIndicator.gdp_growth_pct.isnot(None),
                    MacroIndicator.is_projection == False,  # noqa: E712
                )
                .order_by(desc(MacroIndicator.year))
                .first()
            )
            if not imf_rec or imf_rec.gdp_growth_pct is None:
                continue

            wb_val = float(wb_rec.gdp_growth_pct)
            imf_val = float(imf_rec.gdp_growth_pct)

            avg = (abs(wb_val) + abs(imf_val)) / 2
            if avg < 0.1:
                continue

            divergence_pct = abs(wb_val - imf_val) / avg * 100
            if divergence_pct > tolerance_pct:
                severity = "HIGH" if divergence_pct > 50 else "MEDIUM"
                detail = json.dumps({
                    "worldbank_gdp_growth": wb_val,
                    "imf_gdp_growth": imf_val,
                    "divergence_pct": round(divergence_pct, 2),
                    "tolerance": tolerance_pct,
                    "wb_period": str(wb_rec.period_date),
                    "imf_year": imf_rec.year,
                })
                q = DataQuarantine(
                    table_name="cross_source",
                    record_id=wb_rec.id,
                    country_code=country.code,
                    anomaly_type="CROSS_SOURCE",
                    anomaly_detail=detail,
                    severity=severity,
                )
                self.db.add(q)
                flagged.append({
                    "country_code": country.code,
                    "wb_gdp": wb_val,
                    "imf_gdp": imf_val,
                    "divergence_pct": round(divergence_pct, 2),
                    "severity": severity,
                })

        if flagged:
            self.db.flush()
        return flagged

    # ── 4. Data Freshness Check ───────────────────────────────────

    def check_data_freshness(self, max_stale_days: int = MAX_STALE_DAYS) -> list[dict]:
        """Check each data source for staleness."""
        flagged = []
        now = datetime.now(timezone.utc)

        sources = self.db.query(DataSourceHealth).all()
        for src in sources:
            if src.last_success_at is None:
                src.status = "UNKNOWN"
                continue

            last = src.last_success_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)

            age_days = (now - last).total_seconds() / 86400

            if age_days > MAX_OFFLINE_DAYS:
                src.status = "OFFLINE"
                severity = "CRITICAL"
            elif age_days > max_stale_days:
                src.status = "DEGRADED"
                severity = "HIGH"
            else:
                src.status = "HEALTHY"
                continue

            detail = json.dumps({
                "source": src.source_name,
                "last_success": str(src.last_success_at),
                "age_days": round(age_days, 1),
                "threshold_days": max_stale_days,
            })
            q = DataQuarantine(
                table_name="data_source_health",
                record_id=src.id,
                country_code=None,
                anomaly_type="STALE",
                anomaly_detail=detail,
                severity=severity,
                status="PENDING",
            )
            self.db.add(q)
            flagged.append({
                "source": src.source_name,
                "age_days": round(age_days, 1),
                "status": src.status,
                "severity": severity,
            })

        self.db.flush()
        return flagged

    # ── 5. Missing Critical Fields ────────────────────────────────

    def check_missing_critical_fields(self) -> list[dict]:
        """Flag CountryIndex records missing critical fields."""
        flagged = []
        critical_fields = ["index_value", "shipping_score", "trade_score"]

        countries = self.db.query(Country).filter(
            Country.code.in_(ECOWAS_CODES)
        ).all()

        for country in countries:
            latest = (
                self.db.query(CountryIndex)
                .filter(CountryIndex.country_id == country.id)
                .order_by(desc(CountryIndex.period_date))
                .first()
            )
            if not latest:
                continue

            missing = [
                f for f in critical_fields
                if getattr(latest, f, None) is None
            ]
            if missing:
                detail = json.dumps({
                    "missing_fields": missing,
                    "period_date": str(latest.period_date),
                })
                q = DataQuarantine(
                    table_name="country_index",
                    record_id=latest.id,
                    country_code=country.code,
                    anomaly_type="MISSING_CRITICAL",
                    anomaly_detail=detail,
                    severity="HIGH",
                )
                self.db.add(q)
                flagged.append({
                    "country_code": country.code,
                    "record_id": latest.id,
                    "missing_fields": missing,
                })

        if flagged:
            self.db.flush()
        return flagged

    # ── 6. Source Health Update ────────────────────────────────────

    def update_source_health(
        self,
        source_name: str,
        success: bool,
        latency_ms: float,
        error_msg: Optional[str] = None,
    ):
        """Update reliability metrics for a data source after a fetch."""
        now = datetime.now(timezone.utc)
        src = self.db.query(DataSourceHealth).filter(
            DataSourceHealth.source_name == source_name
        ).first()

        if not src:
            src = DataSourceHealth(
                source_name=source_name, updated_at=now,
            )
            self.db.add(src)

        src.fetch_count += 1
        src.last_fetch_at = now

        if success:
            src.success_count += 1
            src.last_success_at = now
        else:
            src.error_count += 1
            src.last_error_message = error_msg

        # Rolling average latency
        if src.avg_latency_ms == 0:
            src.avg_latency_ms = latency_ms
        else:
            src.avg_latency_ms = src.avg_latency_ms * 0.8 + latency_ms * 0.2

        # Reliability = success_rate × freshness_factor
        success_rate = src.success_count / max(1, src.fetch_count)
        if src.last_success_at:
            last = src.last_success_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            hours_since = (now - last).total_seconds() / 3600
            freshness = max(0.0, 1.0 - hours_since / (MAX_STALE_DAYS * 24))
        else:
            freshness = 0.0

        src.reliability_score = round(success_rate * freshness, 4)

        if src.reliability_score >= 0.8:
            src.status = "HEALTHY"
        elif src.reliability_score >= 0.5:
            src.status = "DEGRADED"
        else:
            src.status = "OFFLINE"

        src.updated_at = now
        self.db.flush()

    # ── 7. Lineage Recording ──────────────────────────────────────

    def record_lineage(
        self,
        target_table: str,
        target_id: int,
        sources: list[dict],
    ):
        """Record data lineage: which source records contributed to a target.

        Each source dict: {"table": str, "id": int, "weight": float, "value": float}
        """
        for s in sources:
            self.db.add(DataLineage(
                target_table=target_table,
                target_id=target_id,
                source_table=s["table"],
                source_id=s["id"],
                contribution_weight=s.get("weight", 1.0),
                snapshot_value=s.get("value"),
            ))
        self.db.flush()

    # ── 8. Full Reconciliation Run ────────────────────────────────

    def run_full_reconciliation(self, run_type: str = "SCHEDULED") -> dict:
        """Execute all checks, return summary."""
        t0 = time.time()
        now = datetime.now(timezone.utc)

        run = ReconciliationRun(
            run_type=run_type,
            started_at=now,
        )
        self.db.add(run)
        self.db.flush()

        total_checked = 0
        total_anomalies = 0
        by_type = {}

        # Z-score on CountryIndex.index_value
        z_flags = self.check_z_score_anomalies(CountryIndex, "index_value")
        total_checked += self.db.query(CountryIndex).count()
        total_anomalies += len(z_flags)
        by_type["Z_SCORE"] = len(z_flags)

        # Rate-of-change on CountryIndex.index_value
        roc_flags = self.check_rate_of_change(CountryIndex, "index_value")
        total_anomalies += len(roc_flags)
        by_type["RATE_OF_CHANGE"] = len(roc_flags)

        # Cross-source GDP
        gdp_flags = self.cross_validate_gdp()
        total_checked += self.db.query(MacroIndicator).count()
        total_anomalies += len(gdp_flags)
        by_type["CROSS_SOURCE"] = len(gdp_flags)

        # Freshness
        fresh_flags = self.check_data_freshness()
        total_anomalies += len(fresh_flags)
        by_type["STALE"] = len(fresh_flags)

        # Missing critical
        missing_flags = self.check_missing_critical_fields()
        total_anomalies += len(missing_flags)
        by_type["MISSING_CRITICAL"] = len(missing_flags)

        duration_ms = round((time.time() - t0) * 1000, 1)

        run.completed_at = datetime.now(timezone.utc)
        run.records_checked = total_checked
        run.anomalies_found = total_anomalies
        run.quarantined = total_anomalies
        run.summary_json = json.dumps({
            "by_type": by_type,
            "duration_ms": duration_ms,
        })

        self.db.commit()

        logger.info(
            "Reconciliation complete: checked=%d anomalies=%d duration=%.0fms",
            total_checked, total_anomalies, duration_ms,
        )

        return {
            "run_id": run.id,
            "run_type": run_type,
            "records_checked": total_checked,
            "anomalies_found": total_anomalies,
            "quarantined": total_anomalies,
            "by_type": by_type,
            "duration_ms": duration_ms,
        }

    # ── 9. Integrity Dashboard ────────────────────────────────────

    def get_integrity_dashboard(self) -> dict:
        """Return overall data quality scorecard."""
        now = datetime.now(timezone.utc)

        # Source health
        sources = self.db.query(DataSourceHealth).all()
        source_list = []
        total_reliability = 0.0
        for s in sources:
            source_list.append({
                "source": s.source_name,
                "status": s.status,
                "reliability": round(s.reliability_score, 4),
                "fetch_count": s.fetch_count,
                "error_count": s.error_count,
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "last_success": str(s.last_success_at) if s.last_success_at else None,
            })
            total_reliability += s.reliability_score

        # Quarantine summary
        pending = self.db.query(DataQuarantine).filter(
            DataQuarantine.status == "PENDING"
        ).count()
        by_severity = {}
        for sev in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            count = self.db.query(DataQuarantine).filter(
                DataQuarantine.status == "PENDING",
                DataQuarantine.severity == sev,
            ).count()
            if count:
                by_severity[sev] = count

        by_type = {}
        for atype in ["Z_SCORE", "RATE_OF_CHANGE", "CROSS_SOURCE", "STALE", "MISSING_CRITICAL"]:
            count = self.db.query(DataQuarantine).filter(
                DataQuarantine.status == "PENDING",
                DataQuarantine.anomaly_type == atype,
            ).count()
            if count:
                by_type[atype] = count

        # Latest reconciliation run
        last_run = (
            self.db.query(ReconciliationRun)
            .order_by(desc(ReconciliationRun.id))
            .first()
        )

        # Overall integrity score
        n_sources = len(sources) if sources else 1
        integrity_score = round(total_reliability / n_sources * 100, 1)

        return {
            "as_of": now.isoformat() + "Z",
            "integrity_score": integrity_score,
            "sources": source_list,
            "quarantine": {
                "pending": pending,
                "by_severity": by_severity,
                "by_type": by_type,
            },
            "last_reconciliation": {
                "run_id": last_run.id if last_run else None,
                "completed_at": str(last_run.completed_at) if last_run else None,
                "anomalies_found": last_run.anomalies_found if last_run else 0,
            },
        }

    # ── 10. Quarantine Management ─────────────────────────────────

    def resolve_quarantine(
        self,
        quarantine_id: int,
        action: str,
        user_id: int,
    ) -> Optional[dict]:
        """Approve or reject a quarantined record."""
        q = self.db.query(DataQuarantine).filter(
            DataQuarantine.id == quarantine_id
        ).first()
        if not q:
            return None

        now = datetime.now(timezone.utc)
        if action == "approve":
            q.status = "APPROVED"
        elif action == "reject":
            q.status = "REJECTED"
        else:
            return None

        q.reviewed_by = user_id
        q.reviewed_at = now
        self.db.commit()

        return {
            "id": q.id,
            "status": q.status,
            "reviewed_by": user_id,
            "reviewed_at": now.isoformat() + "Z",
        }

    # ── 11. Lineage Query ─────────────────────────────────────────

    def get_lineage(self, target_table: str, target_id: int) -> list[dict]:
        """Get data lineage for a specific record."""
        rows = (
            self.db.query(DataLineage)
            .filter(
                DataLineage.target_table == target_table,
                DataLineage.target_id == target_id,
            )
            .order_by(desc(DataLineage.contribution_weight))
            .all()
        )
        return [
            {
                "source_table": r.source_table,
                "source_id": r.source_id,
                "contribution_weight": r.contribution_weight,
                "snapshot_value": r.snapshot_value,
                "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            }
            for r in rows
        ]
