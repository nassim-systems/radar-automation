from pydantic import BaseModel

from radar.domain import RawItem


class ScoredItem(BaseModel):
    """A ``RawItem`` together with its relevance score (0-10).

    Output of scoring (module 1.4), input of selection and drafting.
    """

    item: RawItem
    score: int
