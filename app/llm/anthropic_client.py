"""
Single wrapper around the Anthropic SDK. Every service module imports
from here rather than calling anthropic.Anthropic() directly, so the
model string lives in exactly one place. No retry logic is implemented
here — this relies entirely on the SDK's own default retry behavior
(audit finding F11: an earlier version of this docstring claimed retry
logic lived here; it never did).
"""

import anthropic
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError, LLMServiceError

_client: Anthropic | None = None


def get_client() -> Anthropic:
    """Retrieve or initialize the singleton Anthropic client.

    Instantiates the Anthropic client using `anthropic_api_key` from centralized
    application settings on first call, then reuses the cached client.

    Returns:
        Anthropic: Configured Anthropic SDK client.

    Raises:
        ConfigurationError: If `anthropic_api_key` is not configured in settings.
    """
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is not set. Please configure it in your .env file."
            )
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def structured_call(prompt: str, output_schema: type[BaseModel], max_tokens: int = 1024) -> BaseModel:
    """Call Claude with a Pydantic schema and return a validated instance of that schema.

    Uses the model specified in `ANTHROPIC_MODEL` (defaulting to `claude-sonnet-4-6`).
    Calls `messages.parse()` with `output_format=output_schema` to guarantee that
    the model's response matches the requested structure.

    A failed API call (timeout, rate limit, connection error) or a response
    that doesn't validate against `output_schema` is wrapped into
    `LLMServiceError` — one clear, catchable type every caller can let
    propagate up to `app/api/main.py`'s registered handler (503 JSON)
    rather than needing its own try/except (previously: none of this
    function's 8 call sites caught anything, so any of these failures fell
    through to a bare, undifferentiated 500).

    Args:
        prompt: User prompt text sent to Claude.
        output_schema: Pydantic model class defining the expected response structure.
        max_tokens: Maximum tokens allowed for the generated completion (default 1024).

    Returns:
        BaseModel: An instance of `output_schema` populated with Claude's structured response.

    Raises:
        LLMServiceError: If the Anthropic API request fails, times out, or
            its response can't be parsed into `output_schema`.
    """
    client = get_client()
    model = get_settings().anthropic_model

    try:
        response = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            output_format=output_schema,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        raise LLMServiceError(f"Claude API call failed: {exc}") from exc
    except ValidationError as exc:
        raise LLMServiceError(f"Claude's response didn't match the expected structure: {exc}") from exc
    return response.parsed_output
