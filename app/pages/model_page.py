import asyncio

from db import db
from models import model_dict
from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import (
    KeyboardButton,
    Update,
)
from utils.keyboard_creator import kbcreator


class ModelPage(Page):
    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # fetch available models
        await self.reply_text(
            update,
            text=(
                "<b>Sanguin Model Viewer</b>\n"
                "<b>**********************</b>\n"
                "Loading available models..."
            ),
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )

        await asyncio.sleep(0.2)

        # give a list of available models for user to chose from as buttons
        model_markup = kbcreator(
            [
                [KeyboardButton(name) for name in model_dict.keys()],
                [KeyboardButton(display_name) for display_name in self.keyboard],
            ]
        )
        model_display_txt: str = ""
        for model in model_dict.values():
            model_display_txt += (
                f"<b>Model: </b><i>{model.name}</i>\n"
                f"<b>Token Per Image: </b>{model.token_cost}\n"
                f"<b>Desc: </b>{model.description}\n\n"
            )

        await self.reply_text(
            update,
            text=model_display_txt,
            reply_markup=model_markup,
            parse_mode="HTML",
        )

    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # detect if a user chose a model

        if msgpayload.text in model_dict.keys():
            chosen_model: str = msgpayload.text
            db.update_user_model(user.user_id, chosen_model)

            await self.reply_text(
                update,
                text="Model Changed successfully!",
                reply_markup=self.reply_markup,
                parse_mode="HTML",
            )
            return

        await self.reply_text(
            update,
            text="Didn't quite get that, if you want to generate an image, please return to the Generation Page :)",
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )
