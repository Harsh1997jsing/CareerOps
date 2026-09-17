from unittest.mock import patch

from app.llm.schemas import GeneratedResumeSection
from app.services.resume_generator import (
    SECTIONS,
    check_keyword_density,
    generate_resume,
)

JOB_DESCRIPTION = (
    "We need a Python engineer with FastAPI and AWS experience to design "
    "and build scalable backend services for our growing platform team."
)


def test_check_keyword_density_flags_long_verbatim_overlap():
    generated = (
        "I helped design and build scalable backend services for our "
        "growing platform team using Python."
    )
    flagged = check_keyword_density(generated, JOB_DESCRIPTION)
    assert flagged
    assert "design and build scalable backend services" in flagged


def test_check_keyword_density_ignores_short_natural_overlap():
    generated = "Experienced with Python, FastAPI, and AWS for backend APIs."
    flagged = check_keyword_density(generated, JOB_DESCRIPTION)
    assert flagged == []


def test_check_keyword_density_handles_short_inputs():
    assert check_keyword_density("Python", "short") == []


def _fake_section(section: str, content: str) -> GeneratedResumeSection:
    return GeneratedResumeSection(section=section, content=content, evidence_ids_used=["EXP001"])


def test_generate_resume_returns_all_sections_in_order(tmp_path):
    skills_path = tmp_path / "skills.yaml"
    skills_path.write_text("programming:\n  - Python\n")
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")

    with patch("app.services.resume_generator.structured_call") as mock_call:
        mock_call.side_effect = [
            _fake_section(section, f"content for {section}") for section in SECTIONS
        ]
        result = generate_resume(JOB_DESCRIPTION, str(skills_path), str(evidence_path))

    assert [s.section for s in result.sections] == SECTIONS
    assert mock_call.call_count == len(SECTIONS)
    assert result.keyword_density_warnings == {}


def test_generate_resume_flags_mirrored_section(tmp_path):
    skills_path = tmp_path / "skills.yaml"
    skills_path.write_text("programming:\n  - Python\n")
    evidence_path = tmp_path / "evidence.yaml"
    evidence_path.write_text("- id: EXP001\n  claim: Built things\n")

    mirrored_content = (
        "I helped design and build scalable backend services for our "
        "growing platform team."
    )
    sections = [_fake_section(section, "unrelated content") for section in SECTIONS]
    sections[SECTIONS.index("summary")] = _fake_section("summary", mirrored_content)

    with patch("app.services.resume_generator.structured_call") as mock_call:
        mock_call.side_effect = sections
        result = generate_resume(JOB_DESCRIPTION, str(skills_path), str(evidence_path))

    assert "summary" in result.keyword_density_warnings
