from datetime import datetime

from pydantic import BaseModel

from core.usage import LlmUsage
from radar.pipeline import PipelineReport


class RunRecord(BaseModel):
    """A timestamped radar run, paired with its report and its LLM usage."""

    at: datetime
    report: PipelineReport
    usage: LlmUsage
