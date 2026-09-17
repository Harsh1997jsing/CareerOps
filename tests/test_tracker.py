from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.tracker import (
    APPLIED_STATUS,
    ApplicationNotConfirmedError,
    mark_applied,
    open_job_url,
)


def test_open_job_url_calls_webbrowser_open():
    with patch("app.services.tracker.webbrowser.open") as mock_open:
        open_job_url("https://example.com/job/1")

    mock_open.assert_called_once_with("https://example.com/job/1")


def _make_mock_engine():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    return mock_engine, mock_conn


def test_mark_applied_refuses_without_confirmation():
    mock_engine, _ = _make_mock_engine()

    with pytest.raises(ApplicationNotConfirmedError):
        mark_applied(mock_engine, application_id=1, job_id=1, company="Acme", confirmed=False)

    mock_engine.begin.assert_not_called()


def test_mark_applied_updates_status_and_history_when_confirmed():
    mock_engine, mock_conn = _make_mock_engine()
    applied_at = datetime(2026, 1, 15, 9, 0, 0)

    mark_applied(
        mock_engine, application_id=1, job_id=2, company="Acme",
        confirmed=True, applied_at=applied_at,
    )

    assert mock_conn.execute.call_count == 2

    update_call, insert_call = mock_conn.execute.call_args_list
    update_params = update_call[0][1]
    insert_params = insert_call[0][1]

    assert update_params == {
        "status": APPLIED_STATUS, "applied_at": applied_at, "application_id": 1,
    }
    assert insert_params == {"company": "Acme", "job_id": 2, "applied_at": applied_at}


def test_mark_applied_defaults_applied_at_to_now():
    mock_engine, mock_conn = _make_mock_engine()
    before = datetime.now()

    mark_applied(mock_engine, application_id=1, job_id=2, company="Acme", confirmed=True)

    after = datetime.now()
    update_params = mock_conn.execute.call_args_list[0][0][1]
    assert before <= update_params["applied_at"] <= after
