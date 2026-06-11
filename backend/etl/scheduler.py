import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

from backend.etl.fetch_stations import run_etl

log = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", 3600))

scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(
        run_etl,
        trigger="interval",
        seconds=POLL_INTERVAL,
        id="etl_job",
        replace_existing=True,
    )
    scheduler.start()
    log.info(f"Scheduler started — ETL will run every {POLL_INTERVAL}s")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        log.info("Scheduler stopped")


if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    log.info("Running ETL once immediately...")
    run_etl()

    log.info("Starting scheduler...")
    start_scheduler()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_scheduler()
        log.info("Exited cleanly")
