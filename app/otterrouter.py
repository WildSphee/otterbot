import logging
import traceback
from typing import Dict, Optional

from app.db import db
from telegram import (
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
)
from app.llms import openai

logger = logging.getLogger(__name__)


async def otterhandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:

        # validate whether the message should be responded to
        # only when the message starts with "hey otter" or "hi otter"

        msg_extract = update.message.text[:12].lower()
        if not (any(i in msg_extract for i in ["hi", "hey", "yo"]) and "otter" in msg_extract):
            logger.info("message does not mention otter, disregarding")
            return
        

        await update.message.chat.send_action(action=ChatAction.TYPING)

        res = await openai.call_openai([], update.message.text)

        update.message.reply_text(res)


    except Exception as e:
        # master exception catcher
        logger.error(
            f"<b>Otter</b> Error\n{str(e)}"
        )
