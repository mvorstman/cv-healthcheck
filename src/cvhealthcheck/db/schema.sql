CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS engagements (
    engagement_id TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    commcell_id   TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engagements_customer_id ON engagements (customer_id);

CREATE TABLE IF NOT EXISTS staged_artifacts (
    stage_id        TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL,
    source_file     TEXT,
    source_type     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    artifact_json   TEXT NOT NULL,
    ai_notes        TEXT,
    created_at      TEXT NOT NULL,
    reviewed_at     TEXT,
    reviewed_by     TEXT,
    engagement_id   TEXT,
    customer_id     TEXT,
    FOREIGN KEY (engagement_id) REFERENCES engagements (engagement_id),
    FOREIGN KEY (customer_id)   REFERENCES customers (customer_id)
);

CREATE INDEX IF NOT EXISTS idx_staged_artifacts_status
    ON staged_artifacts (status);

CREATE INDEX IF NOT EXISTS idx_staged_artifacts_subject
    ON staged_artifacts (subject_id);
