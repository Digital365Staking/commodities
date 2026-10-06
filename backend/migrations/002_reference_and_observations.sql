-- 001 created sailing_snapshots but nothing writes to it; replaced by voyage_observations below.
DROP TABLE IF EXISTS sailing_snapshots;

-- ---------- Reference layer (normalized from the Nansha page) ----------
CREATE TABLE ports (
    id      SERIAL PRIMARY KEY,
    name    TEXT   NOT NULL UNIQUE,            -- canonical name
    aliases TEXT[] NOT NULL DEFAULT '{}'       -- spelling variants seen at sources
);
INSERT INTO ports (name, aliases) VALUES
    ('Nansha', '{Guangzhou Nansha,Nansha Port}'),
    ('Southampton', '{Southhampton}');

CREATE TABLE services (
    id         SERIAL PRIMARY KEY,
    row_key    TEXT NOT NULL UNIQUE,           -- service codes joined with '|', as published
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Which carrier sells which service code. Derived BY POSITION from the page, so flagged.
CREATE TABLE service_carriers (
    service_id           INT  NOT NULL REFERENCES services(id),
    carrier_code         TEXT NOT NULL,
    carrier_service_code TEXT NOT NULL,
    mapping_status       TEXT NOT NULL DEFAULT 'by_position'
                         CHECK (mapping_status IN ('by_position', 'verified')),
    PRIMARY KEY (service_id, carrier_code, carrier_service_code)
);

-- Port rotation and nominal transit days, one version per raw payload (append-only).
-- Meaning of inbound/outbound is NOT defined on the page: kept as published.
CREATE TABLE service_port_calls (
    raw_id                BIGINT NOT NULL REFERENCES raw_payloads(id),
    service_id            INT    NOT NULL REFERENCES services(id),
    seq                   INT    NOT NULL,
    port_id               INT    NOT NULL REFERENCES ports(id),
    port_as_published     TEXT   NOT NULL,
    nominal_inbound_days  INT,
    nominal_outbound_days INT,
    inbound_status        TEXT   NOT NULL CHECK (inbound_status  IN ('by_position', 'suspect', 'missing')),
    outbound_status       TEXT   NOT NULL CHECK (outbound_status IN ('by_position', 'suspect', 'missing')),
    PRIMARY KEY (raw_id, service_id, seq)
);

-- Manual corrections after you checked a value against the carrier. Wins over parsed values.
CREATE TABLE port_call_overrides (
    id           SERIAL PRIMARY KEY,
    service_id   INT  NOT NULL REFERENCES services(id),
    port_id      INT  NOT NULL REFERENCES ports(id),
    direction    TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    nominal_days INT  NOT NULL,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (service_id, port_id, direction)
);

-- ---------- Observation layer (what actually happens; append-only) ----------
CREATE TABLE voyage_observations (
    id                   BIGSERIAL PRIMARY KEY,
    observed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    source               TEXT NOT NULL,        -- 'manual-maersk', 'manual-msc', later a connector name
    service_id           INT  REFERENCES services(id),
    carrier_code         TEXT,
    carrier_service_code TEXT,
    vessel               TEXT,
    imo                  TEXT,
    voyage               TEXT,
    origin_port_id       INT  NOT NULL REFERENCES ports(id),
    dest_port_id         INT  NOT NULL REFERENCES ports(id),
    cutoff_at            TIMESTAMPTZ,          -- container cut-off at the origin port
    scheduled_departure  TIMESTAMPTZ,
    estimated_departure  TIMESTAMPTZ,
    actual_departure     TIMESTAMPTZ,
    scheduled_arrival    TIMESTAMPTZ,
    estimated_arrival    TIMESTAMPTZ,
    actual_arrival       TIMESTAMPTZ,
    route_variant        TEXT NOT NULL DEFAULT 'unknown'
                         CHECK (route_variant IN ('suez', 'cape', 'other', 'unknown')),
    note                 TEXT,
    raw_id               BIGINT REFERENCES raw_payloads(id)
);
CREATE INDEX voyage_observations_idx ON voyage_observations (service_id, voyage, observed_at);

-- ---------- Views ----------
-- Latest nominal values per service, overrides applied.
CREATE VIEW current_nominal AS
SELECT s.id AS service_id, s.row_key, spc.seq, p.id AS port_id, p.name AS port,
       COALESCE(oi.nominal_days,  spc.nominal_inbound_days)  AS inbound_days,
       COALESCE(oo.nominal_days,  spc.nominal_outbound_days) AS outbound_days,
       CASE WHEN oi.id IS NOT NULL THEN 'verified' ELSE spc.inbound_status  END AS inbound_status,
       CASE WHEN oo.id IS NOT NULL THEN 'verified' ELSE spc.outbound_status END AS outbound_status
FROM service_port_calls spc
JOIN (SELECT service_id, MAX(raw_id) AS raw_id FROM service_port_calls GROUP BY service_id) latest
     ON latest.service_id = spc.service_id AND latest.raw_id = spc.raw_id
JOIN services s ON s.id = spc.service_id
JOIN ports p    ON p.id = spc.port_id
LEFT JOIN port_call_overrides oi ON oi.service_id = spc.service_id AND oi.port_id = spc.port_id AND oi.direction = 'inbound'
LEFT JOIN port_call_overrides oo ON oo.service_id = spc.service_id AND oo.port_id = spc.port_id AND oo.direction = 'outbound';

-- Theory (Nansha page) against practice (observations). direction: 'outbound' = leaves Nansha,
-- 'inbound' = arrives at Nansha, using the page's own column names.
CREATE VIEW theory_vs_practice AS
WITH obs AS (
    SELECT o.*, po.name AS origin, pd.name AS destination,
           COALESCE(o.actual_departure, o.estimated_departure, o.scheduled_departure) AS dep,
           COALESCE(o.actual_arrival,   o.estimated_arrival,   o.scheduled_arrival)   AS arr,
           CASE WHEN o.actual_arrival IS NOT NULL THEN 'actual'
                WHEN o.estimated_arrival IS NOT NULL THEN 'estimated' ELSE 'scheduled' END AS arrival_basis,
           CASE WHEN po.name = 'Nansha' THEN 'outbound' WHEN pd.name = 'Nansha' THEN 'inbound' END AS direction,
           CASE WHEN po.name = 'Nansha' THEN pd.id ELSE po.id END AS far_port_id
    FROM voyage_observations o
    JOIN ports po ON po.id = o.origin_port_id
    JOIN ports pd ON pd.id = o.dest_port_id
), joined AS (
    SELECT obs.id, obs.observed_at, obs.origin, obs.destination, obs.carrier_code, obs.carrier_service_code,
           obs.vessel, obs.voyage, obs.route_variant, obs.direction, obs.arrival_basis, obs.cutoff_at,
           CASE obs.direction WHEN 'outbound' THEN n.outbound_days WHEN 'inbound' THEN n.inbound_days END AS nominal_days,
           CASE obs.direction WHEN 'outbound' THEN n.outbound_status WHEN 'inbound' THEN n.inbound_status END AS nominal_status,
           (obs.arr::date - obs.dep::date) AS observed_days
    FROM obs
    LEFT JOIN current_nominal n ON n.service_id = obs.service_id AND n.port_id = obs.far_port_id
)
SELECT joined.*,
       observed_days - nominal_days AS gap_days,
       ROUND(100.0 * (observed_days - nominal_days) / NULLIF(nominal_days, 0), 1) AS gap_pct,
       (observed_days > nominal_days * 1.10) AS over_threshold
FROM joined;
