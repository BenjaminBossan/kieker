import logging
import sys

logger = logging.getLogger("sql-over-code")
logger.addHandler(logging.NullHandler())


def configure_logger(verbosity: int) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(handler)
    if verbosity <= 0:
        level = logging.ERROR
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    root.setLevel(level)
