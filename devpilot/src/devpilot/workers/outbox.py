"""Outbox polling worker entrypoint."""
import time
from loguru import logger
from prometheus_client import start_http_server
from devpilot.config import AppSettings
from devpilot.core.database import SessionFactory
from devpilot.core.outbox import process_outbox_batch
from devpilot.core.logging import configure_logging
from devpilot.core.metrics import OUTBOX_BATCH_ERRORS, OUTBOX_BATCH_SIZE, OUTBOX_LAST_SUCCESS

def main():
    settings = AppSettings()
    configure_logging(settings)
    start_http_server(settings.worker_metrics_port)
    logger.info("Outbox worker started")
    while True:
        try:
            with SessionFactory() as session:
                result = process_outbox_batch(session)
            OUTBOX_BATCH_SIZE.observe(result["selected"]); OUTBOX_LAST_SUCCESS.set_to_current_time()
            if result["selected"]: logger.info("Outbox batch {}", result)
        except Exception:
            OUTBOX_BATCH_ERRORS.inc()
            logger.exception("Outbox batch failed")
        time.sleep(settings.outbox_poll_seconds)

if __name__ == "__main__": main()
