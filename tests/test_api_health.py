"""Audit finding F9: check_database_health() existed but nothing called it."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health_reports_ok_when_database_is_reachable():
    with patch("app.api.routes.health.check_database_health", return_value=True):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_degraded_when_database_is_unreachable():
    with patch("app.api.routes.health.check_database_health", return_value=False):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "unreachable"}


def test_health_does_not_require_authentication():
    # No dependency override for get_current_user needed here — /health
    # is deliberately unauthenticated, unlike every other route (F1).
    with patch("app.api.routes.health.check_database_health", return_value=True):
        response = client.get("/health")

    assert response.status_code == 200
