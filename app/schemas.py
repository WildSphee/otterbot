from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    id: Optional[int] = None
    user_id: int
    user_name: str
    preferred_name: Optional[str] = None
    model: Optional[str] = None
    page: Optional[str] = None
    tokens: Optional[int] = None
    date_joined: Optional[datetime] = None


class Game(BaseModel):
    id: Optional[int] = None
    name: str
    slug: str
    description: Optional[str] = None
    status: Optional[str] = None
    store_dir: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_researched_at: Optional[datetime] = None


class GameSource(BaseModel):
    id: Optional[int] = None
    game_id: int
    source_type: str  # pdf|html|link|video|txt|other
    url: Optional[str] = None
    title: Optional[str] = None
    local_path: Optional[str] = None
    added_at: Optional[datetime] = None


class ChatLog(BaseModel):
    id: Optional[int] = None
    chat_id: int
    chat_type: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    message: str
    role: str  # user|assistant|system
    game_slug: Optional[str] = None
    created_at: Optional[datetime] = None
