"""
Computes per-station health indicators from the snapshot time series.
"""
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal, StationSnapshot, StationHealth, Station

log = logging.getLogger(__name__)


def compute_health(nrel_id: int, db: Session) -> dict | None:
    """
    Compute uptime rate, outage count, MTBF, and availability score
    for a single station from its snapshot history.
    """
    rows = (
        db.query(StationSnapshot)
        .filter(StationSnapshot.nrel_id == nrel_id)
        .order_by(StationSnapshot.polled_at)
        .all()
    )

    if len(rows) < 2:
        return None

    df = pd.DataFrame([{"status_code": r.status_code, "polled_at": r.polled_at} for r in rows])
    df["polled_at"] = pd.to_datetime(df["polled_at"])
    df = df.sort_values("polled_at").reset_index(drop=True)

    # Uptime rate is fraction of snapshots where station was open
    total = len(df)
    open_count = (df["status_code"] == "E").sum()
    uptime_rate = round(open_count / total, 4)

    # Outage count is number of E -> T transitions
    df["prev_status"] = df["status_code"].shift(1)
    outage_count = int(((df["status_code"] == "T") & (df["prev_status"] == "E")).sum())

    # MTBF — total observed hours divided by number of outages
    total_hours = (df["polled_at"].iloc[-1] - df["polled_at"].iloc[0]).total_seconds() / 3600
    mtbf_hours = round(total_hours / outage_count, 2) if outage_count > 0 else round(total_hours, 2)

    # Availability score is weighted combination scaled to 0-100
    # uptime contributes 60%, mtbf relative to 720hr baseline 30%, low outage frequency 10%
    mtbf_score = min(mtbf_hours / 720, 1.0)
    outage_penalty = max(0, 1 - (outage_count / max(total, 1)))
    availability_score = round((uptime_rate * 60) + (mtbf_score * 30) + (outage_penalty * 10), 2)

    return {
        "nrel_id": nrel_id,
        "uptime_rate": uptime_rate,
        "outage_count": outage_count,
        "mtbf_hours": mtbf_hours,
        "availability_score": availability_score,
    }


def save_health(metrics: dict, db: Session) -> None:
    """Insert or update station health record."""
    record = db.query(StationHealth).filter(StationHealth.nrel_id == metrics["nrel_id"]).first()
    if record:
        for k, v in metrics.items():
            setattr(record, k, v)
        record.last_computed = datetime.utcnow()
    else:
        db.add(StationHealth(**metrics, last_computed=datetime.utcnow()))


def compute_all_health() -> int:
    """Compute health metrics for every station. Returns count updated."""
    db = SessionLocal()
    updated = 0

    try:
        station_ids = [row.nrel_id for row in db.query(Station.nrel_id).all()]
        log.info(f"Computing health metrics for {len(station_ids)} stations...")

        for nrel_id in station_ids:
            metrics = compute_health(nrel_id, db)
            if metrics:
                save_health(metrics, db)
                updated += 1

        db.commit()
        log.info(f"Health metrics updated for {updated} stations")
    finally:
        db.close()

    return updated


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    compute_all_health()
