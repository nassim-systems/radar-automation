from datetime import datetime

from pydantic import BaseModel


class RawItem(BaseModel):
    source: str
    external_id: str
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
