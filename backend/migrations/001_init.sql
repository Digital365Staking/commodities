-- Layer 1: what the source said, byte for byte. Stored only when the table changes.
CREATE TABLE IF NOT EXISTS raw_payloads (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status  INT,
    content_hash TEXT        NOT NULL,
    table_hash   TEXT,
    headers      JSONB,
    content      TEXT        NOT NULL,
    parse_ok     BOOLEAN,
    parse_error  TEXT
);
CREATE INDEX IF NOT EXISTS raw_payloads_source_idx ON raw_payloads (source, id DESC);

-- Layer 2a: Nansha timetable rows parsed from a raw payload (append-only).
CREATE TABLE IF NOT EXISTS schedule_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    raw_id        BIGINT      NOT NULL REFERENCES raw_payloads(id),
    source        TEXT        NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL,
    row_index     INT         NOT NULL,
    liners        TEXT[],
    service_codes TEXT[],
    yard_closing  TEXT,
    ports         TEXT[],
    inbound_days  TEXT[],
    outbound_days TEXT[],
    raw_cells     JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS schedule_snapshots_raw_idx ON schedule_snapshots (raw_id);

-- Layer 2b: per-sailing state, one row per sailing per day (filled once Step 0 source is chosen).
CREATE TABLE IF NOT EXISTS sailing_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    raw_id         BIGINT REFERENCES raw_payloads(id),
    source         TEXT        NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL,
    service        TEXT,
    vessel         TEXT,
    imo            TEXT,
    voyage         TEXT,
    port           TEXT,
    scheduled_eta  TIMESTAMPTZ,
    estimated_eta  TIMESTAMPTZ,
    actual_arrival TIMESTAMPTZ,
    status         TEXT
);
CREATE INDEX IF NOT EXISTS sailing_snapshots_idx ON sailing_snapshots (source, service, voyage, port, fetched_at);

-- Proof that the history has no holes: one row per source per run.
CREATE TABLE IF NOT EXISTS run_log (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    ok           BOOLEAN,
    changed      BOOLEAN,
    http_status  INT,
    table_hash   TEXT,
    rows_parsed  INT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS run_log_source_idx ON run_log (source, started_at DESC);
