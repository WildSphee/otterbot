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
