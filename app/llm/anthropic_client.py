"""
Single wrapper around the Anthropic SDK. Every service module imports
from here rather than calling anthropic.Anthropic() directly, so the
model string and retry logic live in exactly one place.
"""

import os
from anthropic import Anthropic
from pydantic import BaseModel

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def structured_call(prompt: str, output_schema: type[BaseModel], max_tokens: int = 1024) -> BaseModel:
    """
    Calls Claude with a Pydantic schema and returns a validated instance
    of that schema. Raises if the API call fails — callers should catch
    and log, never silently swallow a failed analysis.
    """
    client = get_client()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        output_format=output_schema,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.parsed_output
