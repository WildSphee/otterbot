import asyncio

from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import (
    Update,
)
from telegram.constants import ChatAction


class StartPage(Page):
    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        await self.reply_text(
            update,
            "Welcome to <b>Sanguin AI!</b>",
            parse_mode="HTML",
        )

        await update.message.chat.send_action(action=ChatAction.TYPING)
        await asyncio.sleep(1)

        await self.reply_text(
            update,
            text=f""
            f"We are a open platform aims for providing the best image generation models at low price.\n"
            f"As its open beta, please enjoy <b>{user.tokens} FREE tokens</b>!",
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )
