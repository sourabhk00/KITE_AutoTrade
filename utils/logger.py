"""
utils/logger.py — Colored console + file logging
"""

import logging
import sys
from datetime import date
from pathlib import Path


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    Path(log_dir).mkdir(exist_ok=True)
    log_file = Path(log_dir) / f"bot_{date.today():%Y%m%d}.log"

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    try:
        import colorlog
        handler = colorlog.StreamHandler(sys.stdout)
        handler.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(name)s: %(message)s",
            log_colors={"DEBUG":"cyan","INFO":"white","WARNING":"yellow",
                        "ERROR":"red","CRITICAL":"bold_red"},
        ))
    except ImportError:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt))

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(fmt))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler, file_handler],
    )
