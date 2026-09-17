"""
Confirms a generated DOCX will survive an ATS's parser: no tables, images,
text boxes, or multi-column layout, and its text survives a DOCX -> PDF ->
text round-trip intact. The round-trip uses LibreOffice headless (the
`soffice` binary) to convert, then PyMuPDF to extract text back out — that's
the same path most ATS ingestion pipelines take, so it's a closer proxy than
just inspecting the DOCX alone.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from docx import Document
from docx.oxml.ns import qn

from app.llm.schemas import GeneratedResumeSection
from app.services.docx_writer import SECTION_TITLES


@dataclass
class AtsValidationResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _column_count(section) -> int:
    # python-docx has no public API for column count; w:cols lives on the
    # section's sectPr XML, absent entirely for the (default) single-column case.
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        return 1
    num = cols.get(qn("w:num"))
    return int(num) if num else 1


def check_docx_structure(docx_path: str) -> AtsValidationResult:
    """Confirms the DOCX itself has no ATS-hostile elements."""
    document = Document(docx_path)
    reasons = []

    if document.tables:
        reasons.append(f"contains {len(document.tables)} table(s)")

    if document.inline_shapes:
        reasons.append(f"contains {len(document.inline_shapes)} inline image(s)/shape(s)")

    # Text boxes aren't exposed via python-docx's object model at all —
    # they show up as a distinct drawing element in the raw document XML.
    if "<w:txbxContent" in document.element.xml:
        reasons.append("contains one or more text boxes")

    for section in document.sections:
        columns = _column_count(section)
        if columns > 1:
            reasons.append(f"page section has {columns} columns (expected 1)")

    return AtsValidationResult(passed=len(reasons) == 0, reasons=reasons)


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str:
    """Converts via LibreOffice headless. Requires `soffice` on PATH."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found on PATH. Install LibreOffice (provides "
            "the 'soffice' command) to run ATS PDF round-trip checks."
        )

    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", output_dir, docx_path],
        check=True,
        capture_output=True,
        timeout=60,
    )

    pdf_path = Path(output_dir) / (Path(docx_path).stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not produce {pdf_path}")
    return str(pdf_path)


def extract_pdf_text(pdf_path: str) -> str:
    with pymupdf.open(pdf_path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def check_text_roundtrip(source_text: str, extracted_text: str,
                          required_snippets: list[str]) -> AtsValidationResult:
    """
    Confirms nothing was lost or garbled going DOCX -> PDF -> text, and that
    the required snippets (section headings, contact info) survived intact.
    """
    reasons = []
    normalized_extracted = _normalize(extracted_text)

    for snippet in required_snippets:
        if _normalize(snippet) not in normalized_extracted:
            reasons.append(f"missing after PDF round-trip: '{snippet}'")

    source_words = set(_normalize(source_text).split())
    extracted_words = set(normalized_extracted.split())
    missing_ratio = (len(source_words - extracted_words) / len(source_words)) if source_words else 0.0
    if missing_ratio > 0.1:
        reasons.append(f"{missing_ratio:.0%} of source words missing from extracted PDF text")

    return AtsValidationResult(passed=len(reasons) == 0, reasons=reasons)


def validate_ats(docx_path: str, source_text: str, required_snippets: list[str],
                  workdir: str) -> AtsValidationResult:
    """Full pipeline: structure check first (cheap, no subprocess), then the PDF round-trip."""
    structure_result = check_docx_structure(docx_path)
    if not structure_result.passed:
        return structure_result

    pdf_path = convert_docx_to_pdf(docx_path, workdir)
    extracted_text = extract_pdf_text(pdf_path)
    return check_text_roundtrip(source_text, extracted_text, required_snippets)


def resume_required_snippets(profile: dict, sections: list[GeneratedResumeSection]) -> list[str]:
    snippets = [profile.get("name", ""), profile.get("email", "")]
    snippets += [SECTION_TITLES.get(s.section, s.section.title()) for s in sections]
    return [s for s in snippets if s]


def cover_letter_required_snippets(profile: dict) -> list[str]:
    return [s for s in [profile.get("name", ""), profile.get("email", "")] if s]
