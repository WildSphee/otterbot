"""
Telegram WebApp utilities for displaying game files in-app.
"""

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def create_game_files_button(game_id: int, game_name: str) -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with a WebApp button to view game files.

    Args:
        game_id: The game's database ID
        game_name: The game's name (for button text)

    Returns:
        InlineKeyboardMarkup with a WebApp button
    """
    webapp_url = f"{API_BASE_URL}/games/{game_id}/files"

    keyboard = [
        [
            InlineKeyboardButton(
                text=f"📂 View {game_name} Files", web_app=WebAppInfo(url=webapp_url)
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


def create_games_library_button() -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with a WebApp button to view all games.

    Returns:
        InlineKeyboardMarkup with a WebApp button
    """
    webapp_url = f"{API_BASE_URL}/games"

    keyboard = [
        [
            InlineKeyboardButton(
                text="📚 Browse Game Library", web_app=WebAppInfo(url=webapp_url)
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)
