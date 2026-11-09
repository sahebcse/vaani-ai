CREATE TABLE IF NOT EXISTS call_warehouse (
    call_id TEXT PRIMARY KEY,
    tenant TEXT NOT NULL,
    frames_received INT NOT NULL,
    frames_dropped INT NOT NULL,
    errors INT NOT NULL,
    transcript_chars INT NOT NULL,
    escalated BOOLEAN NOT NULL
);
