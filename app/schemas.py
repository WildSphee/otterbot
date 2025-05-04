from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class MessagePayload(BaseModel):
    text: str = ""
    image: Optional[Any] = None
    voice: Optional[Any] = None


class User(BaseModel):
    id: Optional[int] = None
    user_id: int
    user_name: str
    preferred_name: Optional[str] = None
    model: Optional[str] = None
    page: Optional[str] = None
    tokens: Optional[int] = None
    date_joined: Optional[datetime] = None
