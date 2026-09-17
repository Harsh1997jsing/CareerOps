# CareerOps

Human-approval job application assistant. See project chat history for the
full phased plan — this repo contains the Phase 0–1 starting point.

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your real ANTHROPIC_API_KEY

docker compose up -d          # starts Postgres
psql postgresql://careerops:careerops@localhost:5432/careerops -f schema.sql
```

## Fill in your data

Edit these before running anything — the system is only as accurate as
what's in here:

- `data/profile.yaml`
- `data/skills.yaml`
- `data/constraints.yaml`
- `data/evidence.yaml`

## Run tests (no API key needed for these)

```bash
pytest tests/test_hard_filters.py -v
```

## Try the job scorer (needs ANTHROPIC_API_KEY set)

```python
from app.services.job_scorer import score_job, decide

analysis = score_job(
    job_description="We need a Python engineer with FastAPI and AWS experience...",
    skills_path="data/skills.yaml",
    evidence_path="data/evidence.yaml",
    constraints_path="data/constraints.yaml",
)
print(analysis)
print(decide(analysis))
```

## What's built vs. what's next

Built: hard filters, company cooldown check, job scorer with structured
output, schemas for screening answers and claim checking.

Not yet built: resume/cover-letter generator, claim validator execution,
ATS validator (DOCX→PDF round trip), dashboard, job ingestion adapters.
Build these next, in that order — each has a test-gate described in the
project plan before moving to the next one.
