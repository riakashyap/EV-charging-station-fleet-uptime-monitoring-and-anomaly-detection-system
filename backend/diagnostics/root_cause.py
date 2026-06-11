"""
Diagnostic layer — analyzes outage patterns for a flagged station
and generates root-cause hypotheses for technician review.
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, StationSnapshot, StationHealth, AnomalyAlert

log = logging.getLogger(__name__)

# Thresholds for pattern classification
SHORT_OUTAGE_HOURS = 2.0       # outages under this = likely network
LONG_OUTAGE_HOURS = 12.0       # outages over this = likely hardware/power
HIGH_FREQUENCY = 5             # more than this many outages = likely network
LOW_FREQUENCY = 2              # fewer than this = likely hardware/power
SELF_RECOVERY_RATE_HIGH = 0.7  # station recovered on its own >70% of the time


def analyze_outage_pattern(nrel_id: int, db: Session) -> dict:
    """
    Load snapshot history for a station and compute outage pattern metrics.
    Returns a dict describing the outage behavior.
    """
    rows = (
        db.query(StationSnapshot)
        .filter(StationSnapshot.nrel_id == nrel_id)
        .order_by(StationSnapshot.polled_at)
        .all()
    )

    if len(rows) < 4:
        return {"error": "insufficient_data", "nrel_id": nrel_id}

    df = pd.DataFrame([{
        "status_code": r.status_code,
        "polled_at": pd.to_datetime(r.polled_at),
    } for r in rows]).sort_values("polled_at").reset_index(drop=True)

    df["prev_status"] = df["status_code"].shift(1)
    df["next_status"] = df["status_code"].shift(-1)
    df["time_delta_hrs"] = df["polled_at"].diff().dt.total_seconds() / 3600

    # Identify outage blocks (consecutive T snapshots)
    outage_durations = []
    self_recoveries = 0
    in_outage = False
    outage_start = None

    for i, row in df.iterrows():
        if row["status_code"] == "T" and not in_outage:
            in_outage = True
            outage_start = row["polled_at"]
        elif row["status_code"] == "E" and in_outage:
            in_outage = False
            duration_hrs = (row["polled_at"] - outage_start).total_seconds() / 3600
            outage_durations.append(duration_hrs)
            self_recoveries += 1  # came back to E = self-recovered (no manual intervention recorded)

    outage_count = len(outage_durations)
    avg_outage_duration = round(sum(outage_durations) / outage_count, 2) if outage_count > 0 else 0.0
    max_outage_duration = round(max(outage_durations), 2) if outage_count > 0 else 0.0
    self_recovery_rate = round(self_recoveries / outage_count, 2) if outage_count > 0 else 1.0

    total_hours = (df["polled_at"].iloc[-1] - df["polled_at"].iloc[0]).total_seconds() / 3600
    outage_frequency = round(outage_count / max(total_hours / 24, 1), 2)  # outages per day

    return {
        "nrel_id": nrel_id,
        "total_snapshots": len(df),
        "total_hours_observed": round(total_hours, 2),
        "outage_count": outage_count,
        "avg_outage_duration_hrs": avg_outage_duration,
        "max_outage_duration_hrs": max_outage_duration,
        "self_recovery_rate": self_recovery_rate,
        "outage_frequency_per_day": outage_frequency,
    }


def hypothesize_root_cause(pattern: dict) -> dict:
    """
    Apply rule-based logic to pattern metrics to produce a
    root-cause hypothesis with confidence level and recommended action.
    """
    if "error" in pattern:
        return {
            "hypothesis": "unknown",
            "confidence": "low",
            "reasoning": "Not enough data to diagnose.",
            "recommended_action": "Continue monitoring — insufficient history.",
        }

    avg_dur = pattern["avg_outage_duration_hrs"]
    max_dur = pattern["max_outage_duration_hrs"]
    count = pattern["outage_count"]
    recovery_rate = pattern["self_recovery_rate"]
    freq = pattern["outage_frequency_per_day"]

    # --- Network failure ---
    # Many short outages that self-resolve
    if count >= HIGH_FREQUENCY and avg_dur <= SHORT_OUTAGE_HOURS and recovery_rate >= SELF_RECOVERY_RATE_HIGH:
        return {
            "hypothesis": "network_failure",
            "confidence": "high",
            "reasoning": (
                f"Station has {count} outages averaging {avg_dur:.1f}h each, "
                f"with {recovery_rate:.0%} self-recovery rate. "
                "Frequent short self-resolving outages are characteristic of network/connectivity issues."
            ),
            "recommended_action": (
                "Check network connectivity, SIM card, or cellular signal at this location. "
                "Inspect communication hardware. Consider firmware update."
            ),
        }

    # --- Hardware failure ---
    # Few but very long outages, low self-recovery
    if count <= LOW_FREQUENCY and max_dur >= LONG_OUTAGE_HOURS and recovery_rate < 0.5:
        return {
            "hypothesis": "hardware_failure",
            "confidence": "high",
            "reasoning": (
                f"Station has {count} outage(s) with max duration {max_dur:.1f}h "
                f"and only {recovery_rate:.0%} self-recovery. "
                "Long non-self-resolving outages suggest physical hardware failure."
            ),
            "recommended_action": (
                "Dispatch technician for on-site inspection. "
                "Check charging unit, connectors, and internal electronics. "
                "Likely requires component replacement."
            ),
        }

    # --- Power supply failure ---
    # Sudden long outage, no self-recovery, low frequency
    if max_dur >= LONG_OUTAGE_HOURS and recovery_rate < 0.3 and freq < 0.5:
        return {
            "hypothesis": "power_supply_failure",
            "confidence": "medium",
            "reasoning": (
                f"Station has experienced outage(s) lasting up to {max_dur:.1f}h "
                f"with very low self-recovery ({recovery_rate:.0%}). "
                "Sustained non-recoverable outages may indicate power supply or electrical failure."
            ),
            "recommended_action": (
                "Check electrical supply, circuit breakers, and utility connection. "
                "Contact utility provider if power issue is confirmed. "
                "Inspect power management unit on-site."
            ),
        }

    # --- Intermittent / unclear ---
    return {
        "hypothesis": "intermittent_unknown",
        "confidence": "low",
        "reasoning": (
            f"Station has {count} outage(s) averaging {avg_dur:.1f}h each. "
            "Pattern does not clearly match network, hardware, or power failure signatures."
        ),
        "recommended_action": (
            "Monitor for further outages to build more diagnostic history. "
            "Review station logs if accessible. Consider remote diagnostic check."
        ),
    }


def diagnose_station(nrel_id: int) -> dict:
    """
    Full diagnostic report for a single station.
    Returns pattern analysis + root cause hypothesis.
    """
    db = SessionLocal()
    try:
        pattern = analyze_outage_pattern(nrel_id, db)
        hypothesis = hypothesize_root_cause(pattern)

        # Attach current health metrics if available
        health = db.query(StationHealth).filter(StationHealth.nrel_id == nrel_id).first()
        health_summary = {
            "uptime_rate": health.uptime_rate if health else None,
            "availability_score": health.availability_score if health else None,
            "mtbf_hours": health.mtbf_hours if health else None,
        }

        # Attach open alerts
        alerts = db.query(AnomalyAlert).filter(
            AnomalyAlert.nrel_id == nrel_id,
            AnomalyAlert.resolved == False,
        ).all()
        open_alerts = [{"type": a.alert_type, "severity": a.severity, "message": a.message} for a in alerts]

        return {
            "nrel_id": nrel_id,
            "diagnosed_at": datetime.utcnow().isoformat(),
            "health": health_summary,
            "outage_pattern": pattern,
            "root_cause": hypothesis,
            "open_alerts": open_alerts,
        }
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    nrel_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    import json
    report = diagnose_station(nrel_id)
    print(json.dumps(report, indent=2))
