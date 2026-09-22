from unittest.mock import MagicMock, patch

import httpx
import pytest
from anthropic import APIConnectionError
from pydantic import BaseModel, ValidationError

from app.core.exceptions import LLMServiceError
from app.llm.anthropic_client import structured_call


class _Echo(BaseModel):
    value: str


def _patched(client):
    return (
        patch("app.llm.anthropic_client.get_client", return_value=client),
        patch("app.llm.anthropic_client.get_settings"),
    )


def test_structured_call_returns_parsed_output_on_success():
    response = MagicMock(parsed_output=_Echo(value="ok"))
    client = MagicMock()
    client.messages.parse.return_value = response

    with patch("app.llm.anthropic_client.get_client", return_value=client), \
         patch("app.llm.anthropic_client.get_settings") as mock_settings:
        mock_settings.return_value.anthropic_model = "claude-test"
        result = structured_call("prompt", _Echo)

    assert result == _Echo(value="ok")


def test_structured_call_wraps_an_anthropic_api_error():
    client = MagicMock()
    client.messages.parse.side_effect = APIConnectionError(
        message="connection reset", request=httpx.Request("POST", "https://api.anthropic.com")
    )

    with patch("app.llm.anthropic_client.get_client", return_value=client), \
         patch("app.llm.anthropic_client.get_settings") as mock_settings:
        mock_settings.return_value.anthropic_model = "claude-test"
        with pytest.raises(LLMServiceError):
            structured_call("prompt", _Echo)


def test_structured_call_wraps_a_validation_error_from_malformed_structured_output():
    try:
        _Echo.model_validate({})  # missing required "value" field
    except ValidationError as exc:
        validation_error = exc

    client = MagicMock()
    client.messages.parse.side_effect = validation_error

    with patch("app.llm.anthropic_client.get_client", return_value=client), \
         patch("app.llm.anthropic_client.get_settings") as mock_settings:
        mock_settings.return_value.anthropic_model = "claude-test"
        with pytest.raises(LLMServiceError):
            structured_call("prompt", _Echo)
