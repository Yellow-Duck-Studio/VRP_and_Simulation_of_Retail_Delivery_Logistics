import logging
import sys
import os
from typing import Optional

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

class Formatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: str = None, use_colors: bool = True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and sys.stdout.isatty() and not os.getenv("NO_COLOR")

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_colors:
            return super().format(record)

        level_colors = {
            logging.DEBUG: Colors.DIM,
            logging.INFO: Colors.GREEN,
            logging.WARNING: Colors.YELLOW,
            logging.ERROR: Colors.RED,
            logging.CRITICAL: Colors.RED + Colors.BOLD,
        }
        color = level_colors.get(record.levelno, Colors.RESET)

        orig_levelname = record.levelname
        record.levelname = f"{color}{orig_levelname}{Colors.RESET}"

        result = super().format(record)

        record.levelname = orig_levelname

        return result


def get_logger(name: str, level: Optional[str] = None, use_colors: bool = True) -> logging.Logger:
    """
    Returns a configured logger instance.

    Args:
        name: Logger name (typically module name)
        level: Log level as string (DEBUG, INFO, etc.). If None, reads from LOG_LEVEL env.
        use_colors: Enable/disable colored output. Defaults to True.

    Environment variables:
        LOG_LEVEL: Sets the logging level (default: INFO)
        NO_COLOR: If set (any value), disables colored output
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)

        formatter = Formatter(LOG_FORMAT, DATE_FORMAT, use_colors)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger