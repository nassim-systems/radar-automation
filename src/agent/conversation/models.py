from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class Role(StrEnum):
    CLIENT = "client"
    AGENT = "agent"


class Turn(BaseModel):
    role: Role
    text: str
    at: datetime


class Conversation(BaseModel):
    conversation_id: str
    turns: list[Turn]
