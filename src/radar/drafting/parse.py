from pydantic import BaseModel


class Draft(BaseModel):
    text: str


def parse_draft(response: str) -> Draft:
    """Clean and structure the draft returned by the LLM.

    Pure function: strips extra whitespace, removes blank lines and
    normalizes line endings, then wraps the text in a ``Draft``.
    """
    lines = [line.strip() for line in response.strip().splitlines()]
    text = "\n".join(line for line in lines if line)
    return Draft(text=text)
