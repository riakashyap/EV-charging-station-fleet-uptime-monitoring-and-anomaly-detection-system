"""
FastAPI backend — exposes fleet health metrics, anomaly alerts,
and diagnostic reports via REST endpoints.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.models.database import init_db, get_db, Station, StationHealth, AnomalyAlert
from backend.models.health_metrics import compute_all_health
from backend.anomaly.detector import generate_alerts
from backend.diagnostics.root_cause import diagnose_station
from backend.etl.fetch_stations import run_etl
from backend.etl.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    start_scheduler()
    log.info("EV Fleet Monitor API started")
    yield
    # Shutdown
    stop_scheduler()
    log.info("EV Fleet Monitor API stopped")


app = FastAPI(
    title="EV Fleet Monitor API",
    description="Fleet uptime monitoring and anomaly detection for EV charging stations",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/")
def root():
    return {"status": "ok", "service": "EV Fleet Monitor API"}



# Stations
@app.get("/stations")
def list_stations(
    state: Optional[str] = Query(None, description="Filter by US state code e.g. CA"),
    network: Optional[str] = Query(None, description="Filter by EV network name"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """Return a paginated list of stations with optional filters."""
    query = db.query(Station)
    if state:
        query = query.filter(Station.state == state.upper())
    if network:
        query = query.filter(Station.ev_network.ilike(f"%{network}%"))

    total = query.count()
    stations = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "stations": [
            {
                "nrel_id": s.nrel_id,
                "station_name": s.station_name,
                "city": s.city,
                "state": s.state,
                "status_code": s.status_code,
                "ev_network": s.ev_network,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "ev_level2_ports": s.ev_level2_ports,
                "ev_dc_fast_ports": s.ev_dc_fast_ports,
            }
            for s in stations
        ],
    }


@app.get("/stations/{nrel_id}")
def get_station(nrel_id: int, db: Session = Depends(get_db)):
    """Return full details for a single station."""
    station = db.query(Station).filter(Station.nrel_id == nrel_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {nrel_id} not found")
    return {
        "nrel_id": station.nrel_id,
        "station_name": station.station_name,
        "street": station.street,
        "city": station.city,
        "state": station.state,
        "zip_code": station.zip_code,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "status_code": station.status_code,
        "ev_network": station.ev_network,
        "owner_type": station.owner_type,
        "ev_level1_ports": station.ev_level1_ports,
        "ev_level2_ports": station.ev_level2_ports,
        "ev_dc_fast_ports": station.ev_dc_fast_ports,
        "open_date": station.open_date,
        "last_synced": station.last_synced,
    }



# Health metrics
@app.get("/stations/{nrel_id}/health")
def get_station_health(nrel_id: int, db: Session = Depends(get_db)):
    """Return computed health metrics for a single station."""
    health = db.query(StationHealth).filter(StationHealth.nrel_id == nrel_id).first()
    if not health:
        raise HTTPException(status_code=404, detail=f"No health data for station {nrel_id}")
    return {
        "nrel_id": health.nrel_id,
        "uptime_rate": health.uptime_rate,
        "outage_count": health.outage_count,
        "mtbf_hours": health.mtbf_hours,
        "availability_score": health.availability_score,
        "last_computed": health.last_computed,
    }


@app.get("/fleet/summary")
def fleet_summary(db: Session = Depends(get_db)):
    """Return fleet-wide aggregate health statistics."""
    total_stations = db.query(Station).count()
    open_stations = db.query(Station).filter(Station.status_code == "E").count()
    closed_stations = db.query(Station).filter(Station.status_code == "T").count()

    health_stats = db.query(
        func.avg(StationHealth.uptime_rate).label("avg_uptime"),
        func.avg(StationHealth.availability_score).label("avg_availability"),
        func.avg(StationHealth.mtbf_hours).label("avg_mtbf"),
        func.sum(StationHealth.outage_count).label("total_outages"),
    ).first()

    open_alerts = db.query(AnomalyAlert).filter(AnomalyAlert.resolved == False).count()
    high_severity = db.query(AnomalyAlert).filter(
        AnomalyAlert.resolved == False,
        AnomalyAlert.severity == "high"
    ).count()

    return {
        "total_stations": total_stations,
        "open_stations": open_stations,
        "closed_stations": closed_stations,
        "fleet_uptime_rate": round(health_stats.avg_uptime or 0, 4),
        "fleet_avg_availability_score": round(health_stats.avg_availability or 0, 2),
        "fleet_avg_mtbf_hours": round(health_stats.avg_mtbf or 0, 2),
        "total_outages_recorded": int(health_stats.total_outages or 0),
        "open_anomaly_alerts": open_alerts,
        "high_severity_alerts": high_severity,
    }



# Anomaly alerts
@app.get("/alerts")
def list_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity: low | medium | high"),
    alert_type: Optional[str] = Query(None, description="Filter by type: zscore | iqr | rolling"),
    resolved: bool = Query(False),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """Return anomaly alerts with optional filters."""
    query = db.query(AnomalyAlert).filter(AnomalyAlert.resolved == resolved)
    if severity:
        query = query.filter(AnomalyAlert.severity == severity)
    if alert_type:
        query = query.filter(AnomalyAlert.alert_type == alert_type)

    total = query.count()
    alerts = query.order_by(AnomalyAlert.detected_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "alerts": [
            {
                "id": a.id,
                "nrel_id": a.nrel_id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "detected_at": a.detected_at,
                "resolved": a.resolved,
            }
            for a in alerts
        ],
    }


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an anomaly alert as resolved."""
    alert = db.query(AnomalyAlert).filter(AnomalyAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.resolved = True
    db.commit()
    return {"message": f"Alert {alert_id} marked as resolved"}



# Diagnostics
@app.get("/stations/{nrel_id}/diagnosis")
def get_diagnosis(nrel_id: int, db: Session = Depends(get_db)):
    """Return full diagnostic report with root-cause hypothesis for a station."""
    station = db.query(Station).filter(Station.nrel_id == nrel_id).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station {nrel_id} not found")
    return diagnose_station(nrel_id)



# Manual ETL trigger
@app.post("/etl/run")
def trigger_etl():
    """Manually trigger a full ETL run, health recompute, and anomaly detection."""
    total = run_etl()
    health_updated = compute_all_health()
    alert_summary = generate_alerts()
    return {
        "message": "ETL pipeline completed",
        "stations_processed": total,
        "health_records_updated": health_updated,
        "alerts_generated": alert_summary,
    }
