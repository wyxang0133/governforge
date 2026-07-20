"""Outbox polling worker entrypoint."""
import time
from loguru import logger
from prometheus_client import start_http_server
from governforge.config import AppSettings
from governforge.core.database import SessionFactory
from governforge.core.outbox import process_outbox_batch
from governforge.core.logging import configure_logging
from governforge.core.metrics import OUTBOX_BATCH_ERRORS, OUTBOX_BATCH_SIZE, OUTBOX_LAST_SUCCESS
from governforge.core.agents import sweep_stale_runs

def main():
    settings = AppSettings()
    configure_logging(settings)
    start_http_server(settings.worker_metrics_port)
    logger.info("Outbox worker started")
    while True:
        try:
            with SessionFactory() as session:
                sweep_stale_runs(session)
                result = process_outbox_batch(session)
            OUTBOX_BATCH_SIZE.observe(result["selected"]); OUTBOX_LAST_SUCCESS.set_to_current_time()
            if result["selected"]: logger.info("Outbox batch {}", result)
        except Exception:
            OUTBOX_BATCH_ERRORS.inc()
            logger.exception("Outbox batch failed")
        time.sleep(settings.outbox_poll_seconds)

if __name__ == "__main__": main()
