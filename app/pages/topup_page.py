import asyncio
import os
from typing import Literal, Optional

import stripe
from pages.base_page import Page
from schemas import MessagePayload, User
from telegram import (
    KeyboardButton,
    ReplyKeyboardRemove,
    Update,
)
from utils.keyboard_creator import kbcreator

ENVIRONMENT: Optional[Literal["TEST", "PROD"]] = os.getenv("ENVIRONMENT", None)
if not ENVIRONMENT:
    raise EnvironmentError(
        "ENVIRONMENT var not set properly, please run start.sh script with correct args"
    )

if ENVIRONMENT == "PROD":
    stripe.api_key = os.getenv("STRIPE_LIVE_KEY")
else:
    stripe.api_key = os.getenv("STRIPE_TEST_KEY")

stripe.api_version = os.getenv("STRIPE_API_VERSION")


PRODUCTS = {
    "Sanguin 200 Tokens": {
        # "live_price_id": "price_1QzFf1KBJUKPxGuoLMhtMnNn",
        "live_price_id": "price_1R169CKBJUKPxGuonSiwD1Zb",
        "test_price_id": "price_1Qzs1GKBJUKPxGuoatELFGeL",
        "price": 4,
        "tokens": 200,
    },
    "Sanguin 400 + 100 Tokens": {
        # "live_price_id": "price_1QzFiYKBJUKPxGuoEC6BlOS2",
        "live_price_id": "price_1R169wKBJUKPxGuolwKSvYrW",
        "test_price_id": "price_1QzrS9KBJUKPxGuorfam0i3D",
        "price": 8,
        "tokens": 500,  # 400 + 100
    },
    "Sanguin 800 + 400 Tokens": {
        # "live_price_id": "price_1QzFjqKBJUKPxGuoCU4b8fZl",
        "live_price_id": "price_1R1686KBJUKPxGuovewsdmRJ",
        "test_price_id": "price_1QzrRsKBJUKPxGuogUhIjkfs",
        "price": 15,
        "tokens": 1200,  # 800 + 400
    },
    "Sanguin 2000 + 1000 Token": {
        # "live_price_id": "price_1QzTI0KBJUKPxGuodeBAVHCE",
        "live_price_id": "price_1R166yKBJUKPxGuoSvMJf3Td",
        "test_price_id": "price_1QzrRbKBJUKPxGuogwkDc1DW",
        "price": 40,
        "tokens": 3000,  # 2000 + 1000
    },
}


async def create_stripe_session(
    price_id: str, user_id: int, tokens: int
) -> stripe.checkout.Session:
    """Create a Stripe Checkout Session with user metadata"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url=f"{os.getenv('CUSTOM_CDN')}/success",
            cancel_url=f"{os.getenv('CUSTOM_CDN')}/cancel",
            allow_promotion_codes=True,
            metadata={
                "telegram_user_id": str(user_id),
                "price_id": price_id,
                "tokens": tokens,
            },
        )
        return session
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        raise


class TopUpPage(Page):
    async def landing(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        # Initial landing page logic
        await self.reply_text(
            update,
            text=(
                "<b>Sanguin Top Up Page</b>\n"
                "<b>**********************</b>\n"
                "Loading packages..."
            ),
            parse_mode="HTML",
        )

        # Generate product buttons
        topup_markup = kbcreator(
            [[KeyboardButton(name)] for name in PRODUCTS.keys()]
            + [[KeyboardButton(display_name)] for display_name in self.keyboard]
        )

        topup_display_txt: str = ""
        for package_name, price in PRODUCTS.items():
            topup_display_txt += (
                f"<b>Package: </b><i>{package_name}</i>\n"
                f"<b>Price (USD): </b>{price.get('price')}\n\n"
            )

        await self.reply_text(
            update, text=topup_display_txt, reply_markup=topup_markup, parse_mode="HTML"
        )

    async def respond(
        self, update: Update, user: User, msgpayload: MessagePayload
    ) -> None:
        if msgpayload.text in PRODUCTS:
            try:
                product = PRODUCTS[msgpayload.text]
                price_id: str = ""
                if ENVIRONMENT == "PROD":
                    price_id = product["live_price_id"]
                else:
                    price_id = product["test_price_id"]

                session = await create_stripe_session(
                    price_id, user.user_id, product["tokens"]
                )

                await self.reply_text(
                    update,
                    text="<b>Sanguin:</b> Please wait while we create a payment session...",
                    reply_markup=ReplyKeyboardRemove(),
                    parse_mode="HTML",
                )

                await asyncio.sleep(2)

                await self.reply_text(
                    update,
                    text=f"After successful payment, tokens will be added automatically:\n\n<b><a href='{session.url}'>💳{msgpayload.text}💳</a></b>",
                    reply_markup=self.reply_markup,
                    parse_mode="HTML",
                )

            except Exception as e:
                await self.reply_text(
                    update,
                    text="⚠️ Payment system error. Please try again later.",
                    reply_markup=self.reply_markup,
                )
                print(f"Payment error: {str(e)}")
            return

        await self.reply_text(
            update,
            text="Please select a valid package from the menu:",
            reply_markup=self.reply_markup,
            parse_mode="HTML",
        )
        await self.landing(update, user, msgpayload)
