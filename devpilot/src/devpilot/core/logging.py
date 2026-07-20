"""Single structured logging configuration for API and workers."""
import sys
from loguru import logger
from devpilot.config import AppSettings

def configure_logging(settings: AppSettings) -> None:
    logger.remove()
    logger.add(sys.stdout, level=settings.log_level.upper(), serialize=settings.log_json or settings.environment == "production", backtrace=False, diagnose=False, enqueue=True)
