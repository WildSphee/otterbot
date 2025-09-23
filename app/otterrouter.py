import logging
import re
import traceback

from llms.prompt import default_prompt
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from db.sqlite_db import DB
from tools import ResearchTool, QueryTool, slugify

logger = logging.getLogger(__name__)
db = DB()
research_tool = ResearchTool()
query_tool = QueryTool()


def _mentioned_otter(text: str) -> bool:
    msg_extract = (text or "")[:32].lower()
    return (any(i in msg_extract for i in ["hi", "hey", "yo"]) and "otter" in msg_extract)


def _parse_research_intent(text: str) -> str | None:
    """
    Returns the game name if this looks like a research command, else None.
    Examples: "hi otter, research Catan", "yo otter research: Ticket to Ride"
    """
    # Strip mention prefix to avoid false positives
    lowered = text.lower()
    if not _mentioned_otter(text):
        return None
    m = re.search(r"\b(research|study|learn)\b[:\s,]*(.+)$", lowered)
    if not m:
        return None
    game_raw = text[m.start(2):].strip()
    # remove trailing punctuation
    game_raw = re.sub(r"[.\s]+$", "", game_raw)
    # Title-case as a display; slugging happens later
    return game_raw


async def otterhandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = update.message
        if not message or not message.text:
            return

        text = message.text.strip()
        if not _mentioned_otter(text):
            logger.info("message does not mention otter, disregarding")
            return

        chat = message.chat
        chat_id = chat.id
        chat_type = chat.type
        user = message.from_user
        user_id = user.id if user else None
        user_name = (user.username if user and user.username else (user.full_name if user else None))

        await message.chat.send_action(action=ChatAction.TYPING)

        # Log user message
        db.add_chat_message(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name,
            message=text,
            role="user",
        )

        research_game = _parse_research_intent(text)
        if research_game:
            # Check if we already have it; ResearchTool handles both cases
            reply = research_tool.research(research_game)

            # Tag this chat with the game for future inference
            db.add_chat_message(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=user_id,
                user_name=user_name,
                message=f"[system] tagged game: {slugify(research_game)}",
                role="system",
                game_slug=slugify(research_game),
            )

            await message.reply_text(reply)
            db.add_chat_message(
                chat_id=chat_id, chat_type=chat_type,
                user_id=None, user_name="OtterBot",
                message=reply, role="assistant",
                game_slug=slugify(research_game),
            )
            return

        # Otherwise, treat as a rules question. Try to answer using QueryTool (which infers the game).
        answer = query_tool.answer(chat_id=chat_id, user_text=text, explicit_game=None)
        await message.reply_text(answer)

        # Log assistant answer; try to attach inferred game if answer contains a known slug
        maybe_game = None
        for g in db.list_games():
            if g["name"].lower() in answer.lower():
                maybe_game = g["slug"]
                break

        db.add_chat_message(
            chat_id=chat_id, chat_type=chat_type,
            user_id=None, user_name="OtterBot",
            message=answer, role="assistant",
            game_slug=maybe_game,
        )

    except Exception as e:
        logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
