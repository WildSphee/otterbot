import logging
import os
import traceback

from db.sqlite_db import DB
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from tools import GamesListTool, QueryTool, ResearchTool, classify_user_intent
from utils import is_private_chat, mentioned_otter, schola_reply
from webapp import create_game_files_button

logger = logging.getLogger(__name__)
db = DB()
research_tool = ResearchTool()
query_tool = QueryTool()
games_list_tool = GamesListTool()


async def otterhandler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = update.message
        if not message or not message.text:
            return

        text = message.text.strip()
        chat = message.chat
        chat_id = chat.id
        chat_type = chat.type

        # In group chats, require "otter" mention
        # In private chats, respond to all messages
        if not is_private_chat(chat_type) and not mentioned_otter(text):
            logger.info(
                f"Group message does not mention otter, disregarding (chat_type: {chat_type})"
            )
            return
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

        # Use OpenAI to classify intent
        available_games = [g["name"] for g in db.list_games()]
        intent = classify_user_intent(text, available_games)

        # Route based on intent type
        if intent.intent_type == "list_games":
            # User wants to see available games
            reply = games_list_tool.list_available_games()

            # Create URL buttons for ready games (works in both groups and private chats)
            games = db.list_games()
            ready_games = [g for g in games if g["status"] == "ready"]

            reply_markup = None
            if ready_games:
                # Create inline keyboard with URL buttons (2 per row)
                api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
                keyboard = []
                for i in range(0, len(ready_games), 2):
                    row = []
                    for game in ready_games[i : i + 2]:
                        game_id = game["id"]
                        game_name = game["name"]
                        file_url = f"{api_base}/games/{game_id}/files"
                        row.append(
                            InlineKeyboardButton(
                                text=f"📂 {game_name}",
                                url=file_url,
                            )
                        )
                    keyboard.append(row)
                reply_markup = InlineKeyboardMarkup(keyboard)

            await schola_reply(update, reply, reply_markup=reply_markup)
            db.add_chat_message(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=None,
                user_name="OtterBot",
                message=reply,
                role="assistant",
            )
            return

        elif intent.intent_type == "research_game":
            # User wants to research a new game
            research_game = intent.game_name
            if not research_game:
                reply = "I'd love to research a game for you! Please specify which game you'd like me to research. 🦦"
                await schola_reply(update, reply)
                return

            # Send initial "on it!" message
            initial_msg = f"On it! 🦦 Researching <b>{research_game}</b>..."
            await schola_reply(update, initial_msg)

            try:
                # Check if we already have it; ResearchTool handles both cases
                reply = research_tool.research(research_game)
            except Exception as e:
                logger.error(f"Research failed for {research_game}: {e}")
                reply = f"😿 Oops! Research failed for <b>{research_game}</b>. Please try again later or check the game name. 🦦"

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

            # Send reply with URL button if we have game_id
            reply_markup = None
            if game_id:
                reply_markup = create_game_files_button(game_id, research_game)

            await schola_reply(update, reply, reply_markup=reply_markup)
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

        elif intent.intent_type == "query_game":
            # User is asking about game rules/mechanics
            explicit_game = intent.game_name if intent.game_name else None
            answer = query_tool.answer(
                chat_id=chat_id, user_text=text, explicit_game=explicit_game
            )
            await schola_reply(update, answer)

            # Log assistant answer; try to attach inferred game
            maybe_game_id = None
            if explicit_game:
                game_data = db.get_game_by_name(explicit_game)
                maybe_game_id = game_data["id"] if game_data else None
            else:
                # Try to infer from answer
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
            return

        else:
            # general_chat or unknown intent - friendly response
            reply = "Hey there! 🦦 I'm OtterBot, your board game assistant! I can help you:\n\n• Research new games: 'otter research Catan'\n• Answer rules questions: 'otter how do you win in Catan?'\n• Show available games: 'otter what games do you have?'\n\nWhat would you like to know?"
            await schola_reply(update, reply)
            db.add_chat_message(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=None,
                user_name="OtterBot",
                message=reply,
                role="assistant",
            )
            return

    except Exception as e:
        logger.error("".join(traceback.format_exception(type(e), e, e.__traceback__)))
