"""Keep report diagnostics in a rotating local log, outside the dashboard UI."""
from functools import lru_cache
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ROOT


@lru_cache(maxsize=4)
def report_logger(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    logger = logging.Logger('fleet_pti.report', level=logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    return logger


@lru_cache(maxsize=128)
def _write_notices(path, notices):
    logger = report_logger(path)
    for notice in notices:
        logger.warning(notice)


def log_report_diagnostics(notices, path=None):
    if not notices:
        return
    try:
        _write_notices(str(path or ROOT / 'logs' / 'dashboard.log'), tuple(notices))
    except OSError:
        for notice in notices:
            logging.getLogger(__name__).warning(notice)
