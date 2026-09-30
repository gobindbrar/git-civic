-- Development schema source of truth. Apply to Replit development PostgreSQL;
-- Publish promotes the resulting schema to the managed production database.
CREATE TABLE IF NOT EXISTS app_users (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    public_passport INTEGER NOT NULL DEFAULT 0,
    share_slug TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    organizer TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT NOT NULL,
    city TEXT NOT NULL,
    zip_code TEXT NOT NULL DEFAULT '',
    starts_at TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    accessibility TEXT NOT NULL DEFAULT '',
    jurisdiction TEXT NOT NULL DEFAULT 'City',
    topics TEXT NOT NULL DEFAULT '[]',
    agenda_url TEXT NOT NULL DEFAULT '',
    is_demo INTEGER NOT NULL DEFAULT 0,
    source_status TEXT NOT NULL DEFAULT 'unverified',
    source_checked_at TEXT NOT NULL DEFAULT '',
    source_record_id TEXT NOT NULL DEFAULT '',
    time_zone TEXT NOT NULL DEFAULT '',
    source_provider TEXT NOT NULL DEFAULT '',
    source_revision TEXT NOT NULL DEFAULT '',
    agenda_status TEXT NOT NULL DEFAULT '',
    body_id INTEGER,
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    owner_id TEXT REFERENCES app_users(id) ON DELETE SET NULL,
    cancelled_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rsvps (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL,
    PRIMARY KEY (event_id, participant_id)
);

CREATE TABLE IF NOT EXISTS check_ins (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL,
    receipt TEXT NOT NULL UNIQUE,
    verified_at TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'organizer_code',
    is_demo INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, participant_id)
);

CREATE TABLE IF NOT EXISTS checkin_attempts (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    window_started_at DOUBLE PRECISION NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS generated_briefs (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    brief_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (event_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS brief_rate_limits (
    user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    window_start BIGINT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, window_start)
);

CREATE TABLE IF NOT EXISTS brief_generation_locks (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    locked_until BIGINT NOT NULL,
    PRIMARY KEY (event_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS rsvps_participant_idx ON rsvps(participant_id);
CREATE INDEX IF NOT EXISTS checkins_participant_idx ON check_ins(participant_id);
CREATE INDEX IF NOT EXISTS events_owner_idx ON events(owner_id);