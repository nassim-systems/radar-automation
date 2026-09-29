from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class InboundMessage(BaseModel):
    sender: str
    channel: str  # email / linkedin / form
    subject: str | None
    body: str
    received_at: datetime


# (str, Enum) form required by the spec (same as StrEnum on 3.11+).
class Intent(str, Enum):  # noqa: UP042
    PROSPECT = "prospect"
    SUPPORT = "support"
    BILLING = "billing"
    SPAM = "spam"
    OTHER = "other"
