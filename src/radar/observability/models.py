from datetime import datetime

from pydantic import BaseModel

from radar.llm.usage import LlmUsage
from radar.pipeline import PipelineReport


class RunRecord(BaseModel):
    """Un run radar horodaté, apparié à son rapport et à son usage LLM."""

    at: datetime
    report: PipelineReport
    usage: LlmUsage
