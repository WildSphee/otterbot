import logging
import re
import traceback

from db.sqlite_db import DB
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from tools import QueryTool, ResearchTool

logger = logging.getLogger(__name__)
db = DB()
research_tool = ResearchTool()
query_tool = QueryTool()


def _mentioned_otter(text: str) -> bool:
    msg_extract = (text or "")[:32].lower()
    return any(i in msg_extract for i in ["hi", "hey", "yo"]) and "otter" in msg_extract


def _parse_research_intent(text: str) -> str | None:
    """
    Returns the game name if this looks like a research command, else None.
    Handles phrasing like: "hi otter, research Catan", "research about Catan", "can you research on Azul?"
    """
    if not _mentioned_otter(text):
        return None
    m = re.search(r"\b(research|study|learn)\b[:\s,]*(.+)$", text, flags=re.IGNORECASE)
    if not m:
        return None
    tail = text[m.start(2) :].strip()

    # Remove leading filler/prepositions/articles and trailing punctuation
    tail = re.sub(
        r"^(about|on|for|into|regarding|re:?|the game|game)\s+",
        "",
        tail,
        flags=re.IGNORECASE,
    )
    tail = re.sub(r"^(the|a|an)\s+", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"[.\s]+$", "", tail)

    # If something like "Catan please", trim polite suffixes
    tail = re.sub(r"\s*(please|thanks|thank you)$", "", tail, flags=re.IGNORECASE)

    return tail if tail else None


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
        user_name = (
            user.username
            if user and user.username
            else (user.full_name if user else None)
        )

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

            # Get game ID to tag this chat
            game_data = db.get_game_by_name(research_game)
            game_id = game_data["id"] if game_data else None

            # Tag this chat with the game for future inference
            db.add_chat_message(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=user_id,
                user_name=user_name,
                message=f"[system] tagged game: {research_game}",
                role="system",
                game_id=game_id,
            )

            await message.reply_text(reply)
            db.add_chat_message(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=None,
                user_name="OtterBot",
                message=reply,
                role="assistant",
                game_id=game_id,
            )
            return

        # Otherwise, treat as a rules question. Try to answer using QueryTool (which infers the game).
        answer = query_tool.answer(chat_id=chat_id, user_text=text, explicit_game=None)
        await message.reply_text(answer)

        # Log assistant answer; try to attach inferred game if answer contains a known game name
        maybe_game_id = None
        for g in db.list_games():
            if g["name"].lower() in answer.lower():
                maybe_game_id = g["id"]
                break

        db.add_chat_message(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=None,
            user_name="OtterBot",
            message=answer,
            role="assistant",
            game_id=maybe_game_id,
        )

    except Exception as e:
        logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
