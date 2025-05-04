import asyncio
import logging
import time
import traceback
from pathlib import Path

from db import db
from models import Model, model_dict
from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import KeyboardButton, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from utils.keyboard_creator import kbcreator
from utils.stt import transcribe_voice

logger = logging.getLogger(__name__)


class GenerationPage(Page):
    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        chosen_model: Model = model_dict.get(user.model)

        await self.reply_text(
            update,
            text=(
                f"You are now on 🎨<b> Generation Page</b>"
                f", type a prompt an generate away!\nCurrent Model: <i>{user.model}</i>\n"
                f"Token Per Image: <b>{chosen_model.token_cost}</b>"
                "\n<i>"
                + f"{chosen_model.model_note if chosen_model.model_note else ''}"
                + "</i>"
            ),
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )

    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # check if the user's token count is valid
        if user.tokens is None or not isinstance(user.tokens, int):
            await self.reply_text(
                update,
                "Error Retrieving your tokens, please contact a developer.",
                reply_markup=self.reply_markup,
                parse_mode="HTML",
            )
            return

        # getting the correct image create function
        model: Model | None = model_dict.get(user.model, None)

        # if cant find model return Error
        if not model:
            await self.reply_text(
                update,
                "Error Retrieving your selected model, please contact a developer.",
                reply_markup=self.reply_markup,
            )
            return

        # check if the user have sufficient tokens
        if user.tokens - model.token_cost <= 0:
            await self.reply_text(
                update,
                "You do not have sufficient tokens.\n Please top up to continue using <b>Sanguin AI</b>",
                reply_markup=self.reply_markup,
                parse_mode="HTML",
            )
            return

        # occasional token reminders
        next_token_count = user.tokens - model.token_cost
        if next_token_count <= 15 <= user.tokens:
            await self.reply_text(
                update,
                f"You have <b>{next_token_count}</b> Tokens remaining",
                parse_mode="HTML",
            )

        # at this point user have valid tokens and chosen model, if its a voice message transcribe it.
        prompt: str = msgpayload.text
        if msgpayload.voice:
            msgpayload.voice = await transcribe_voice(update.message.voice)
            await self.reply_text(
                update,
                f"<b>Transcribed Text</b>: \n<i>{msgpayload.voice}</i>",
                reply_markup=self.reply_markup,
                parse_mode="HTML",
            )
            prompt = msgpayload.voice

        start_time = time.perf_counter()

        image_path: Path = ""
        # Start Image Generation
        try:
            await self.reply_text(
                update,
                "<b>Sanguin</b>: Generating Image...",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML",
            )

            image: bytes = await asyncio.wait_for(model.generate(prompt), timeout=180)

            await update.message.chat.send_action(action=ChatAction.UPLOAD_PHOTO)

            await update.message.reply_photo(image, reply_markup=self.reply_markup)

        except asyncio.TimeoutError:
            await self.reply_text(
                update,
                text=(
                    f"<b>Sanguin</b>: Model <i>{user.model}</i> timeout🥲\nyou have not been"
                    " charged. Please try again with another model."
                ),
                reply_markup=kbcreator([[KeyboardButton("🤖 Change Model")]]),
                parse_mode="HTML",
            )
            logger.error(f"Image model {user.model} timed out after 3 minutes.")

        except Exception as e:
            await self.reply_text(
                update,
                "<b>Sanguin</b>: Error Generating Image, you have not been charged, please try again another model.",
                reply_markup=self.reply_markup,
                parse_mode="HTML",
            )
            logger.error(
                "".join(traceback.format_exception(type(e), e, e.__traceback__))
            )

        # Calculate the total time taken
        end_time = time.perf_counter()
        time_taken = end_time - start_time

        # deduct token
        db.update_user_tokens(user.user_id, -model.token_cost)
        # log generation entry
        db.add_generation_entry(
            user.user_id, prompt, user.model, image_path, model.token_cost, time_taken
        )
