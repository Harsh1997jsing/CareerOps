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

CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_default_admin BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT now(),
    UNIQUE (tenant_id, email)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_collected_at ON jobs(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_analysis_job_analyzed ON job_analysis(job_id, analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_gen_docs_job_id ON generated_documents(job_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);


