from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import (
    Update,
)


class AccountPage(Page):
    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # triggers when a user enters this page initally
        await self.reply_text(
            update,
            text=(
                f"<b>Sanguin AI Profile</b>\n"
                "<b>**********************</b>\n"
                # f"User: <b>{user.user_name}</b>\n"
                f"User ID: <b>{user.user_id}</b>\n"
                f"Remaining Tokens: <b>{user.tokens}</b>\n"
                f"Current Model: <i>{user.model}</i>\n"
            ),
            reply_markup=self.reply_markup,

        )

    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        await self.reply_text(
            update,
            "If you want to generate an image, please return to the Generation Page :)",
        )
