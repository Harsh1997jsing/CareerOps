from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from app.sources.targets import fetch_all_targets, ingest_all, load_company_targets

COMPANIES_YAML = """
greenhouse:
  - board_token: acme
    company: Acme
lever:
  - company_slug: beta-co
    company: Beta Co
"""

GH_JOB = {"source": "greenhouse", "company": "Acme"}
LEVER_JOB = {"source": "lever", "company": "Beta Co"}


def test_load_company_targets_parses_yaml():
    with patch("builtins.open", mock_open(read_data=COMPANIES_YAML)):
        targets = load_company_targets()

    assert targets["greenhouse"][0]["board_token"] == "acme"
    assert targets["lever"][0]["company_slug"] == "beta-co"


def test_load_company_targets_handles_empty_file():
    with patch("builtins.open", mock_open(read_data="")):
        targets = load_company_targets()
    assert targets == {}


def test_fetch_all_targets_pulls_from_both_sources():
    with patch("builtins.open", mock_open(read_data=COMPANIES_YAML)), \
         patch("app.sources.targets.greenhouse.fetch_jobs", return_value=[GH_JOB]) as gh_fetch, \
         patch("app.sources.targets.lever.fetch_jobs", return_value=[LEVER_JOB]) as lever_fetch:
        jobs = fetch_all_targets()

    assert jobs == [GH_JOB, LEVER_JOB]
    gh_fetch.assert_called_once_with("acme", "Acme")
    lever_fetch.assert_called_once_with("beta-co", "Beta Co")


def test_fetch_all_targets_skips_a_failing_target_without_aborting():
    with patch("builtins.open", mock_open(read_data=COMPANIES_YAML)), \
         patch("app.sources.targets.greenhouse.fetch_jobs", side_effect=RuntimeError("boom")), \
         patch("app.sources.targets.lever.fetch_jobs", return_value=[LEVER_JOB]):
        jobs = fetch_all_targets()

    assert jobs == [LEVER_JOB]


async def test_ingest_all_inserts_fetched_jobs():
    mock_session = MagicMock()
    with patch("app.sources.targets.fetch_all_targets", return_value=[GH_JOB, LEVER_JOB]), \
         patch("app.sources.targets.insert_jobs", AsyncMock(return_value=2)) as mock_insert:
        inserted = await ingest_all(mock_session)

    assert inserted == 2
    mock_insert.assert_called_once_with(mock_session, [GH_JOB, LEVER_JOB])
