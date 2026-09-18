"""
Review dashboard: browse scored jobs, preview generated documents next to
the evidence they're built from, and approve/reject with an explicit click.
This is the only place a human decision gets recorded — nothing here
submits anything anywhere; Approve just marks the application package
reviewed (see app/services/tracker.py, Phase 6, for the manual-submit step).
"""

import os

import streamlit as st
import yaml
from docx import Document

from app.db import get_engine
from app.services.dashboard_data import (
    approve_application,
    check_cooldown_for_company,
    get_application_for_job,
    list_generated_documents,
    list_jobs,
    reject_application,
)

CONSTRAINTS_PATH = "data/constraints.yaml"
EVIDENCE_PATH = "data/evidence.yaml"

STATUS_OPTIONS = ["All", "DISCOVERED", "REVIEW_REQUIRED", "READY_FOR_REVIEW", "REJECT"]


def load_constraints(path: str = CONSTRAINTS_PATH) -> dict:
    """Load candidate constraints from a YAML file.

    Args:
        path: Filepath to the constraints YAML file (defaults to `data/constraints.yaml`).

    Returns:
        dict: Parsed constraints dictionary containing allowed locations,
            cooldown periods, excluded keywords, etc.
    """
    with open(path) as f:
        return yaml.safe_load(f)


def load_evidence_yaml(path: str = EVIDENCE_PATH) -> str:
    """Read candidate evidence YAML file as raw text.

    Args:
        path: Filepath to the evidence YAML file (defaults to `data/evidence.yaml`).

    Returns:
        str: Raw text contents of the candidate's evidence file.
    """
    with open(path) as f:
        return f.read()


def read_docx_text(file_path: str) -> str:
    """Extract plain text from all paragraphs of a DOCX file.

    Args:
        file_path: Absolute or relative filesystem path to the DOCX file.

    Returns:
        str: Extracted document paragraphs joined by newlines, or a not-found
            message if the file does not exist.
    """
    if not os.path.exists(file_path):
        return f"(file not found: {file_path})"
    document = Document(file_path)
    return "\n".join(p.text for p in document.paragraphs)


def render_job(engine, job, cooldown_days: int) -> None:
    """Render a single job's interactive review card in the Streamlit UI.

    Displays fit scores, match summaries, missing skills, risks, company cooldown
    warnings, generated documents (with side-by-side evidence preview), and approval
    or rejection buttons.

    Args:
        engine: SQLAlchemy Engine instance for database access.
        job: JobListItem instance containing details and analysis results for the job.
        cooldown_days: Number of days required between applications to the same company.
    """
    with st.expander(f"{job.company} — {job.title}", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Fit score", job.fit_score if job.fit_score is not None else "—")
            st.write(f"**Confidence:** {job.confidence or '—'}")
            st.write(f"**Status:** {job.status}")
            st.write(f"[Job posting]({job.url})")
        with col2:
            st.write("**Strong matches**")
            st.write(job.strong_matches or "—")
            st.write("**Missing / gaps**")
            st.write(job.missing_skills or "—")
            if job.risks:
                st.write("**Risks**")
                st.write(job.risks)

        cooldown = check_cooldown_for_company(engine, job.company, cooldown_days)
        if not cooldown.passed:
            for reason in cooldown.reasons:
                st.warning(f"⚠️ Company cooldown: {reason}")

        docs = list_generated_documents(engine, job.job_id)
        if docs:
            st.subheader("Generated documents vs. evidence")
            doc_col, evidence_col = st.columns(2)
            with doc_col:
                for doc in docs:
                    st.write(
                        f"**{doc.type} (v{doc.version})** — "
                        f"claim check: {'✅' if doc.claim_check_passed else '❌'}, "
                        f"ATS check: {'✅' if doc.ats_check_passed else '❌'}"
                    )
                    st.text_area(
                        f"{doc.type} v{doc.version}",
                        read_docx_text(doc.file_path),
                        height=200,
                        key=f"doc_{doc.id}",
                    )
            with evidence_col:
                st.text_area(
                    "data/evidence.yaml", load_evidence_yaml(), height=460, key=f"evidence_{job.job_id}"
                )
        else:
            st.info("No generated documents yet for this job.")

        application = get_application_for_job(engine, job.job_id)
        if application is None:
            st.caption("No application record yet for this job.")
            return

        st.write(f"**Application status:** {application.status}")
        approve_col, reject_col = st.columns(2)
        with approve_col:
            if st.button("Approve", key=f"approve_{application.application_id}"):
                approve_application(engine, application.application_id)
                st.rerun()
        with reject_col:
            if st.button("Reject", key=f"reject_{application.application_id}"):
                reject_application(engine, application.application_id)
                st.rerun()


def main() -> None:
    """Run the CareerOps Streamlit review dashboard application.

    Initializes the wide layout dashboard, loads candidate constraints to
    retrieve company cooldown policies, presents status filter controls, and
    queries and renders matching jobs along with their generated documents
    and human decision approval buttons.
    """
    st.set_page_config(page_title="CareerOps", layout="wide")
    st.title("CareerOps")

    constraints = load_constraints()
    cooldown_days = constraints.get("company_cooldown_days", 30)

    engine = get_engine()

    status_choice = st.sidebar.selectbox("Filter by status", STATUS_OPTIONS)
    status_filter = None if status_choice == "All" else status_choice

    jobs = list_jobs(engine, status_filter)

    if not jobs:
        st.info("No jobs found for this filter.")
        return

    for job in jobs:
        render_job(engine, job, cooldown_days)


if __name__ == "__main__":
    main()
