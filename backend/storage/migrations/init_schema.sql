CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    city            TEXT,
    district        TEXT,
    salary_min      INTEGER,
    salary_max      INTEGER,
    education       TEXT,
    experience      TEXT,
    industry        TEXT,
    skills          TEXT,
    description     TEXT,
    url             TEXT,
    contact_email   TEXT,
    company_size    TEXT,
    posted_date     TEXT,
    scraped_at      TEXT NOT NULL,
    is_active       INTEGER DEFAULT 1,
    is_retained     INTEGER DEFAULT 0,
    UNIQUE(platform, job_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_jobs_platform ON jobs(platform);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);

CREATE TABLE IF NOT EXISTS user_resumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    parsed_data     TEXT,
    avatar_path     TEXT,
    is_primary      INTEGER DEFAULT 0,
    uploaded_at     TEXT NOT NULL,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS tailored_resumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    base_resume_id  INTEGER NOT NULL,
    job_id          INTEGER NOT NULL,
    file_name       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    changes_json    TEXT,
    status          TEXT DEFAULT 'draft',
    created_at      TEXT NOT NULL,
    FOREIGN KEY (base_resume_id) REFERENCES user_resumes(id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER,
    tailored_resume_id INTEGER,
    method          TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    error_message   TEXT,
    job_url         TEXT,
    job_title       TEXT,
    applied_at      TEXT,
    updated_at      TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id),
    FOREIGN KEY (tailored_resume_id) REFERENCES tailored_resumes(id)
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_applied_at ON applications(applied_at);

CREATE TABLE IF NOT EXISTS daily_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL UNIQUE,
    jobs_scraped    INTEGER DEFAULT 0,
    jobs_matched    INTEGER DEFAULT 0,
    jobs_applied    INTEGER DEFAULT 0,
    jobs_responded  INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    city            TEXT,
    jobs_found      INTEGER DEFAULT 0,
    status          TEXT,
    error_message   TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL UNIQUE,
    mode            TEXT NOT NULL DEFAULT 'text',
    topic           TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_sec    INTEGER DEFAULT 0,
    messages        TEXT,
    score           INTEGER,
    feedback_json   TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_created_at ON interview_sessions(created_at);

CREATE TABLE IF NOT EXISTS match_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id       INTEGER NOT NULL,
    job_id          INTEGER NOT NULL,
    match_score     REAL DEFAULT 0,
    skill_score     REAL DEFAULT 0,
    fit_score       REAL DEFAULT 0,
    salary_score    REAL DEFAULT 0,
    matched_skills  TEXT,
    missing_skills  TEXT,
    ai_analysis     TEXT,
    ai_strengths    TEXT,
    ai_suggestions  TEXT,
    jd_missing      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE(resume_id, job_id),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_match_results_job_id ON match_results(job_id);
CREATE INDEX IF NOT EXISTS idx_match_results_score ON match_results(match_score DESC);
