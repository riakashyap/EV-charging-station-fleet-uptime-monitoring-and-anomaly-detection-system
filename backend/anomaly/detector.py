"""
Anomaly detection for EV charging station fleet health.
Uses three methods: z-score, IQR-based flagging, and rolling window deviation.
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, StationHealth, StationSnapshot, AnomalyAlert

log = logging.getLogger(__name__)

# How many std deviations from mean before we flag (z-score)
ZSCORE_THRESHOLD = 2.0

# How far below Q1 before we flag (IQR)
IQR_MULTIPLIER = 1.5

# Rolling window size (number of snapshots to look back)
ROLLING_WINDOW = 24

# How many std deviations from own rolling mean before flagging
ROLLING_THRESHOLD = 2.0


def load_health_dataframe(db: Session) -> pd.DataFrame:
    """Load all station health records into a DataFrame."""
    rows = db.query(StationHealth).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "nrel_id": r.nrel_id,
        "uptime_rate": r.uptime_rate,
        "outage_count": r.outage_count,
        "mtbf_hours": r.mtbf_hours,
        "availability_score": r.availability_score,
    } for r in rows])


def alert_exists(db: Session, nrel_id: int, alert_type: str) -> bool:
    """Check if an unresolved alert of this type already exists for this station."""
    return db.query(AnomalyAlert).filter(
        AnomalyAlert.nrel_id == nrel_id,
        AnomalyAlert.alert_type == alert_type,
        AnomalyAlert.resolved == False,
    ).first() is not None


def create_alert(db: Session, nrel_id: int, alert_type: str, severity: str, message: str) -> None:
    """Write a new anomaly alert to the database."""
    if not alert_exists(db, nrel_id, alert_type):
        db.add(AnomalyAlert(
            nrel_id=nrel_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            detected_at=datetime.utcnow(),
            resolved=False,
        ))


def zscore_detection(df: pd.DataFrame, db: Session) -> int:
    """
    Flag stations whose uptime_rate is more than ZSCORE_THRESHOLD
    standard deviations below the fleet mean.
    """
    if df.empty or len(df) < 10:
        return 0

    flagged = 0
    z_scores = stats.zscore(df["uptime_rate"].dropna())
    df = df.copy()
    df["zscore"] = z_scores

    for _, row in df[df["zscore"] < -ZSCORE_THRESHOLD].iterrows():
        severity = "high" if row["zscore"] < -3.0 else "medium"
        message = (
            f"Station {row['nrel_id']} uptime rate {row['uptime_rate']:.1%} is "
            f"{abs(row['zscore']):.1f} std deviations below fleet average."
        )
        create_alert(db, int(row["nrel_id"]), "zscore", severity, message)
        flagged += 1

    return flagged


def iqr_detection(df: pd.DataFrame, db: Session) -> int:
    """
    Flag stations whose availability_score falls below Q1 - 1.5*IQR.
    """
    if df.empty or len(df) < 10:
        return 0

    flagged = 0
    scores = df["availability_score"].dropna()
    q1 = scores.quantile(0.25)
    q3 = scores.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - IQR_MULTIPLIER * iqr

    outliers = df[df["availability_score"] < lower_bound]
    for _, row in outliers.iterrows():
        severity = "high" if row["availability_score"] < lower_bound - iqr else "medium"
        message = (
            f"Station {row['nrel_id']} availability score {row['availability_score']:.1f} "
            f"is below fleet lower bound of {lower_bound:.1f} (IQR method)."
        )
        create_alert(db, int(row["nrel_id"]), "iqr", severity, message)
        flagged += 1

    return flagged


def rolling_window_detection(db: Session) -> int:
    """
    For each station, compare its most recent ROLLING_WINDOW snapshots
    against its own historical baseline. Flag if recent mean deviates
    significantly from its own rolling average.
    """
    flagged = 0

    # Load all snapshots ordered by station and time
    rows = db.query(StationSnapshot).order_by(
        StationSnapshot.nrel_id, StationSnapshot.polled_at
    ).all()

    if not rows:
        return 0

    df = pd.DataFrame([{
        "nrel_id": r.nrel_id,
        "is_open": 1 if r.status_code == "E" else 0,
        "polled_at": r.polled_at,
    } for r in rows])

    for nrel_id, group in df.groupby("nrel_id"):
        group = group.sort_values("polled_at").reset_index(drop=True)

        if len(group) < ROLLING_WINDOW * 2:
            continue

        # Baseline: all history except last window
        baseline = group.iloc[:-ROLLING_WINDOW]["is_open"]
        recent = group.iloc[-ROLLING_WINDOW:]["is_open"]

        baseline_mean = baseline.mean()
        baseline_std = baseline.std()

        if baseline_std == 0:
            continue

        recent_mean = recent.mean()
        deviation = (recent_mean - baseline_mean) / baseline_std

        if deviation < -ROLLING_THRESHOLD:
            severity = "high" if deviation < -3.0 else "medium"
            message = (
                f"Station {nrel_id} recent uptime {recent_mean:.1%} has dropped sharply "
                f"from its own baseline of {baseline_mean:.1%} "
                f"({abs(deviation):.1f} std deviations below its own average)."
            )
            create_alert(db, int(nrel_id), "rolling", severity, message)
            flagged += 1

    return flagged


def generate_alerts() -> dict:
    """
    Run all three anomaly detection methods and persist alerts.
    Returns a summary of how many alerts each method generated.
    """
    db = SessionLocal()
    summary = {"zscore": 0, "iqr": 0, "rolling": 0}

    try:
        df = load_health_dataframe(db)
        log.info(f"Running anomaly detection on {len(df)} stations...")

        summary["zscore"] = zscore_detection(df, db)
        summary["iqr"] = iqr_detection(df, db)
        summary["rolling"] = rolling_window_detection(db)

        db.commit()
        log.info(f"Anomaly detection complete: {summary}")
    finally:
        db.close()

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = generate_alerts()
    print(f"Alerts generated: {result}")
