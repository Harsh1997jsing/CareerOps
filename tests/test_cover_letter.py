from unittest.mock import patch

import pytest

from app.llm.schemas import GeneratedCoverLetter
from app.services.cover_letter import (
    NoVoiceSamplesError,
    generate_cover_letter,
    load_voice_samples,
)

JOB_DESCRIPTION = "We need a Python engineer with FastAPI and AWS experience."


def test_load_voice_samples_raises_when_missing_directory(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(NoVoiceSamplesError):
        load_voice_samples(str(missing_dir))


def test_load_voice_samples_raises_when_only_readme_present(tmp_path):
    (tmp_path / "README.md").write_text("Drop samples here.")
    with pytest.raises(NoVoiceSamplesError):
        load_voice_samples(str(tmp_path))


def test_load_voice_samples_reads_txt_and_md_files(tmp_path):
    (tmp_path / "README.md").write_text("Drop samples here.")
    (tmp_path / "sample1.txt").write_text("First sample of my writing.")
    (tmp_path / "sample2.md").write_text("Second sample of my writing.")

    samples = load_voice_samples(str(tmp_path))

    assert len(samples) == 2
    assert "First sample of my writing." in samples
    assert "Second sample of my writing." in samples


def _fake_cover_letter(word_count: int) -> GeneratedCoverLetter:
    content = " ".join(["word"] * word_count)
    return GeneratedCoverLetter(content=content, evidence_ids_used=["EXP001"])


def _setup_data_files(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Test Candidate\n")
    voice_dir = tmp_path / "voice_samples"
    voice_dir.mkdir()
    (voice_dir / "sample1.txt").write_text("A sample of my own writing style.")
    return evidence_path, profile_path, voice_dir


def test_generate_cover_letter_within_target_has_no_warning(tmp_path):
    evidence_path, profile_path, voice_dir = _setup_data_files(tmp_path)

    with patch("app.services.cover_letter.structured_call") as mock_call:
        mock_call.return_value = _fake_cover_letter(300)
        result = generate_cover_letter(
            JOB_DESCRIPTION, str(evidence_path), str(profile_path), str(voice_dir)
        )

    assert result.word_count == 300
    assert result.word_count_warning is None
    assert result.evidence_ids_used == ["EXP001"]


def test_generate_cover_letter_too_short_sets_warning(tmp_path):
    evidence_path, profile_path, voice_dir = _setup_data_files(tmp_path)

    with patch("app.services.cover_letter.structured_call") as mock_call:
        mock_call.return_value = _fake_cover_letter(100)
        result = generate_cover_letter(
            JOB_DESCRIPTION, str(evidence_path), str(profile_path), str(voice_dir)
        )

    assert result.word_count == 100
    assert result.word_count_warning is not None


def test_generate_cover_letter_requires_voice_samples(tmp_path):
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text("name: Test Candidate\n")
    empty_voice_dir = tmp_path / "voice_samples"
    empty_voice_dir.mkdir()

    with pytest.raises(NoVoiceSamplesError):
        generate_cover_letter(
            JOB_DESCRIPTION, str(evidence_path), str(profile_path), str(empty_voice_dir)
        )
