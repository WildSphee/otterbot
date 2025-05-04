import logging
import os
from pathlib import Path

from otterrouter import otterhandler
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
)

OTTER_BOT_TOKEN = os.getenv("OTTER_BOT_TOKEN")


def _set_up_logging() -> None:
    # create log at root
    logging_dir = Path(r"./log.log")
    logging_dir.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing handlers (important to avoid duplicate logs)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(logging_dir), logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Otterbot Logging Set Up Successfully at: {logging_dir.resolve()}")


def main():
    """Start the bot. Main entry point when running sh scripts/start.sh"""

    if OTTER_BOT_TOKEN is None:
        print(
            "No token found. Please set OTTER_BOT_TOKEN in your environment variables."
        )
        return

    # set up logging
    _set_up_logging()

    print("OTTERBOT: Starting")

    application = (
        ApplicationBuilder().token(OTTER_BOT_TOKEN).concurrent_updates(True).build()
    )

    # default handlers
    application.add_handler(MessageHandler(filters.ALL, otterhandler, block=False))

    # Start the Telegram chatbot
    application.run_polling()


if __name__ == "__main__":
    main()
