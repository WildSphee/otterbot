from abc import abstractmethod
from typing import Dict, Optional

from schemas import MessagePayload, User
from telegram import (
    KeyboardButton,
    Update,
)
from utils.keyboard_creator import kbcreator


class Page:
    def __init__(self, name, keyboard):
        # initialize a default keyboard obj for each page
        self.name: str = name
        self.keyboard: Optional[Dict[str, str]] = keyboard

        self.reply_markup = kbcreator(
            [[KeyboardButton(display_name) for display_name in self.keyboard]]
        )

    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # triggers when a user enters this page initally
        await self.reply_text(
            update,
            text=f"You are now on {self.name.replace('_', ' ').capitalize()}.",
            reply_markup=self.reply_markup,
        )

    @abstractmethod
    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        pass

    async def reply_text(self, update: Update, text: str, *args, **kwargs) -> None:
        # TODO ADD CUSTOM LOGGING
        await update.message.reply_text(text, *args, **kwargs)
