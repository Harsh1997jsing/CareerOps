"""
Generates a cover letter strictly from data/evidence.yaml, matched to the
candidate's own tone via writing samples in data/voice_samples/.
"""

from dataclasses import dataclass
from pathlib import Path

from app.llm.anthropic_client import structured_call
from app.llm.prompts import COVER_LETTER_PROMPT
from app.llm.schemas import GeneratedCoverLetter

MIN_WORDS = 250
MAX_WORDS = 400
MIN_VOICE_SAMPLES = 1
RECOMMENDED_VOICE_SAMPLES = 3


class NoVoiceSamplesError(RuntimeError):
    """Raised when data/voice_samples/ has no writing samples to match tone against."""


def load_voice_samples(voice_samples_dir: str = "data/voice_samples") -> list[str]:
    directory = Path(voice_samples_dir)
    samples = []
    if directory.is_dir():
        paths = sorted(directory.glob("*.txt")) + sorted(directory.glob("*.md"))
        for path in paths:
            if path.stem.lower() == "readme":
                continue
            text = path.read_text(encoding="utf-8").strip()
            if text:
                samples.append(text)

    if len(samples) < MIN_VOICE_SAMPLES:
        raise NoVoiceSamplesError(
            f"No writing samples found in {voice_samples_dir}/. Add "
            f"{RECOMMENDED_VOICE_SAMPLES}-5 samples of your own past writing "
            "(.txt or .md files) so the cover letter can match your tone."
        )
    return samples


@dataclass
class CoverLetterResult:
    content: str
    word_count: int
    evidence_ids_used: list[str]
    word_count_warning: str | None = None


def generate_cover_letter(job_description: str, evidence_path: str, profile_path: str,
                           voice_samples_dir: str = "data/voice_samples") -> CoverLetterResult:
    with open(evidence_path) as f:
        evidence_yaml = f.read()
    with open(profile_path) as f:
        profile_yaml = f.read()

    voice_samples = load_voice_samples(voice_samples_dir)

    prompt = COVER_LETTER_PROMPT.format(
        job_description=job_description,
        profile_yaml=profile_yaml,
        evidence_yaml=evidence_yaml,
        voice_samples="\n\n---\n\n".join(voice_samples),
        min_words=MIN_WORDS,
        max_words=MAX_WORDS,
    )
    result = structured_call(prompt, GeneratedCoverLetter, max_tokens=1536)

    # Word count is computed here, not trusted from the model's own count.
    word_count = len(result.content.split())
    warning = None
    if not (MIN_WORDS <= word_count <= MAX_WORDS):
        warning = f"cover letter is {word_count} words, outside the {MIN_WORDS}-{MAX_WORDS} target"

    return CoverLetterResult(
        content=result.content,
        word_count=word_count,
        evidence_ids_used=result.evidence_ids_used,
        word_count_warning=warning,
    )
