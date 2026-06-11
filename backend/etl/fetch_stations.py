"""
ETL pipeline: fetches all EV charging stations from the NREL API,
validates/cleans the data, and persists it to the database.
"""
import os
import time
import logging
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

from backend.models.database import engine, SessionLocal, init_db, Station, StationSnapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

NREL_API_KEY = os.getenv("NREL_API_KEY")
NREL_BASE_URL = "https://developer.nrel.gov/api/alt-fuel-stations/v1.json"
PAGE_SIZE = 200


def fetch_page(offset: int, status: str = "E") -> dict:
    """Fetch one page of EV stations from NREL."""
    params = {
        "api_key": NREL_API_KEY,
        "fuel_type": "ELEC",
        "status": status,
        "limit": PAGE_SIZE,
        "offset": offset,
        "country": "US",
    }
    resp = requests.get(NREL_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def clean_station(raw: dict) -> dict | None:
    """Validate and normalize a raw station record. Returns None if invalid."""
    nrel_id = raw.get("id")
    lat = raw.get("latitude")
    lng = raw.get("longitude")

    if not nrel_id or lat is None or lng is None:
        return None

    return {
        "nrel_id": int(nrel_id),
        "station_name": (raw.get("station_name") or "").strip(),
        "street": (raw.get("street_address") or "").strip(),
        "city": (raw.get("city") or "").strip(),
        "state": (raw.get("state") or "").strip(),
        "zip_code": (raw.get("zip") or "").strip(),
        "latitude": float(lat),
        "longitude": float(lng),
        "status_code": raw.get("status_code", "E"),
        "ev_level1_ports": int(raw.get("ev_level1_evse_num") or 0),
        "ev_level2_ports": int(raw.get("ev_level2_evse_num") or 0),
        "ev_dc_fast_ports": int(raw.get("ev_dc_fast_num") or 0),
        "ev_network": (raw.get("ev_network") or "").strip(),
        "owner_type": (raw.get("owner_type_code") or "").strip(),
        "open_date": raw.get("open_date"),
    }


def upsert_station(db: Session, data: dict) -> None:
    """Insert or update a station record."""
    station = db.query(Station).filter(Station.nrel_id == data["nrel_id"]).first()
    if station:
        for k, v in data.items():
            setattr(station, k, v)
        station.last_synced = datetime.utcnow()
    else:
        db.add(Station(**data, last_synced=datetime.utcnow()))


def record_snapshot(db: Session, nrel_id: int, status_code: str) -> None:
    """Write a time-series snapshot for this polling cycle."""
    db.add(StationSnapshot(
        nrel_id=nrel_id,
        status_code=status_code,
        polled_at=datetime.utcnow()
    ))


def run_etl(snapshot: bool = True) -> int:
    """
    Full ETL run. Fetches all open + temporarily-closed stations.
    Returns total stations processed.
    """
    init_db()
    db = SessionLocal()
    total = 0

    try:
        for status in ("E", "T"):
            offset = 0
            while True:
                log.info(f"Fetching status={status} offset={offset}...")
                try:
                    page = fetch_page(offset, status)
                except requests.RequestException as e:
                    log.error(f"API error at offset {offset}: {e}")
                    break

                stations = page.get("alt_fuel_stations", [])
                if not stations:
                    break

                for raw in stations:
                    cleaned = clean_station(raw)
                    if cleaned:
                        upsert_station(db, cleaned)
                        if snapshot:
                            record_snapshot(db, cleaned["nrel_id"], cleaned["status_code"])
                        total += 1

                db.commit()
                log.info(f"  committed {len(stations)} stations (total: {total})")

                if len(stations) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                time.sleep(0.2)

    finally:
        db.close()

    log.info(f"ETL complete. Total stations processed: {total}")
    return total


if __name__ == "__main__":
    run_etl()
