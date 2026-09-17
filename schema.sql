-- Run once against your Postgres DB to bootstrap the schema.
-- Once you're past the POC stage, switch to Alembic migrations
-- (alembic init migrations) instead of hand-editing this file.

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    source_job_id TEXT,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL,
    description TEXT NOT NULL,
    description_hash TEXT UNIQUE,
    posted_at TIMESTAMP,
    collected_at TIMESTAMP DEFAULT now(),
    employment_type TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    status TEXT DEFAULT 'DISCOVERED'
);

CREATE TABLE IF NOT EXISTS job_analysis (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    fit_score INTEGER,
    confidence TEXT,
    eligible BOOLEAN,
    strong_matches JSONB,
    missing_skills JSONB,
    risks JSONB,
    analyzed_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    claim TEXT NOT NULL,
    category TEXT,
    source TEXT,
    verified BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS generated_documents (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    type TEXT,
    file_path TEXT,
    version INTEGER DEFAULT 1,
    claim_check_passed BOOLEAN,
    ats_check_passed BOOLEAN,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    status TEXT DEFAULT 'READY_FOR_REVIEW',
    applied_at TIMESTAMP,
    resume_version INTEGER,
    cover_letter_version INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS company_application_history (
    id SERIAL PRIMARY KEY,
    company TEXT NOT NULL,
    job_id INTEGER REFERENCES jobs(id),
    applied_at TIMESTAMP,
    UNIQUE (company, job_id)
);
