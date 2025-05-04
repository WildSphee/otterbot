import logging

from llms import openai
from llms.prompt import default_prompt
from telegram import (
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ContextTypes,
)
import traceback

logger = logging.getLogger(__name__)


async def otterhandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # validate whether the message should be responded to
        # only when the message starts with "hey otter" or "hi otter"

        msg_extract = update.message.text[:12].lower()
        if not (
            any(i in msg_extract for i in ["hi", "hey", "yo"])
            and "otter" in msg_extract
        ):
            logger.info("message does not mention otter, disregarding")
            return

        await update.message.chat.send_action(action=ChatAction.TYPING)

        res = openai.call_openai([], default_prompt.format(query=update.message.text))

        await update.message.reply_text(res)

    except Exception as e:
        # master exception catcher
        logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
