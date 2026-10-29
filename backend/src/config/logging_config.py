import logging


def configure_logging(level: str) -> None:
    """Wired once per entrypoint; app code only calls ``logging.getLogger(__name__)``."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
