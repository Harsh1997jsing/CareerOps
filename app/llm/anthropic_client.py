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
    """Retrieve or initialize the singleton Anthropic client.

    Instantiates the Anthropic client using the `ANTHROPIC_API_KEY` environment
    variable on first call, then reuses the cached client.

    Returns:
        Anthropic: Configured Anthropic SDK client.

    Raises:
        KeyError: If `ANTHROPIC_API_KEY` is not set in the environment.
    """
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def structured_call(prompt: str, output_schema: type[BaseModel], max_tokens: int = 1024) -> BaseModel:
    """Call Claude with a Pydantic schema and return a validated instance of that schema.

    Uses the model specified in `ANTHROPIC_MODEL` (defaulting to `claude-sonnet-4-6`).
    Calls `messages.parse()` with `output_format=output_schema` to guarantee that
    the model's response matches the requested structure. Raises if the API call fails
    or validation cannot be completed — callers should catch and log, never silently
    swallow a failed analysis.

    Args:
        prompt: User prompt text sent to Claude.
        output_schema: Pydantic model class defining the expected response structure.
        max_tokens: Maximum tokens allowed for the generated completion (default 1024).

    Returns:
        BaseModel: An instance of `output_schema` populated with Claude's structured response.

    Raises:
        anthropic.APIError: If the Anthropic API request fails or times out.
        pydantic.ValidationError: If the response cannot be parsed into `output_schema`.
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
