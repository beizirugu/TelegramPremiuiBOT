from __future__ import annotations

import logging

from .bot import PremiumBot
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    PremiumBot(settings).run()


if __name__ == "__main__":
    main()
