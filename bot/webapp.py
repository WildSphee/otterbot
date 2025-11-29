"""
Telegram button utilities for displaying game files.
"""

import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def create_game_files_button(game_id: int, game_name: str) -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with a URL button to view game files.

    Args:
        game_id: The game's database ID
        game_name: The game's name (for button text)

    Returns:
        InlineKeyboardMarkup with a URL button

    Note:
        Uses regular URL buttons that work in both private chats and groups.
        Opens the mobile-optimized file browser in the user's default browser.
    """
    file_url = f"{API_BASE_URL}/games/{game_id}/files"

    button = InlineKeyboardButton(text=f"📂 View {game_name} Files", url=file_url)

    keyboard = [[button]]
    return InlineKeyboardMarkup(keyboard)


def create_games_library_button() -> InlineKeyboardMarkup:
    """
    Create an inline keyboard with a URL button to view all games.

    Returns:
        InlineKeyboardMarkup with a URL button
    """
    library_url = f"{API_BASE_URL}/games"

    keyboard = [[InlineKeyboardButton(text="📚 Browse Game Library", url=library_url)]]

    return InlineKeyboardMarkup(keyboard)
