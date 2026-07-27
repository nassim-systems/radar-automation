from pydantic import BaseModel

from radar.domain import RawItem


class ScoredItem(BaseModel):
    """Un ``RawItem`` accompagné de son score de pertinence (0-10).

    Sortie du scoring (module 1.4), entrée de la sélection et du drafting.
    """

    item: RawItem
    score: int
