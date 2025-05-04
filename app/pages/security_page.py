from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import (
    Update,
)


class SecurityPage(Page):
    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        await self.reply_text(
            update,
            text=(
                "<b>Sanguin AI Security Disclaimer</b>\n"
                "<b>**********************</b>\n"
                "Sanguin AI keep only the necessary and minimal "
                "information to keep the AI bot running, we do not "
                "retain customer generation history under any circumstances. "
                "We do not store any customer personal identifiable information (PII) "
                "except telegram ID, which is used to keep track of tokens.\n"
                "All models are hosted on-prem and secured. And are not sent out to "
                "external services."
            ),
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )
        await self.reply_text(
            update,
            "For bugs, refunds, and assistance, please contact developer team sanguinaibot@gmail.com",
        )

    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        await self.reply_text(
            update,
            "For bugs, refunds, and assistance, please contact developer team sanguinaibot@gmail.com",
        )
