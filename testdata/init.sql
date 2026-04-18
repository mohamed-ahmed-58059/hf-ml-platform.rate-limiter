-- Tiers
CREATE TABLE tiers (
    id               UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR(20)    NOT NULL UNIQUE,
    capacity         INTEGER        NOT NULL,
    refill_per_sec   NUMERIC(10, 4) NOT NULL,
    requests_per_min INTEGER        NOT NULL,
    version          INTEGER        NOT NULL DEFAULT 1
);

INSERT INTO tiers (id, name, capacity, refill_per_sec, requests_per_min, version) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'free',               25,    0.3333,  20,    1),
    ('c0000000-0000-0000-0000-000000000002', 'basic',              120,   1.6667,  100,   1),
    ('c0000000-0000-0000-0000-000000000003', 'premium',            600,   8.3333,  500,   1),
    ('c0000000-0000-0000-0000-000000000004', 'internal-low',       300,   4.1667,  250,   1),
    ('c0000000-0000-0000-0000-000000000005', 'internal-standard',  1200,  16.6667, 1000,  1),
    ('c0000000-0000-0000-0000-000000000006', 'internal-high',      6000,  83.3333, 5000,  1),
    ('c0000000-0000-0000-0000-000000000007', 'internal-unlimited', 99999, 9999.0,  99999, 1);


-- Routes
-- Single source of truth for registered endpoints.
-- tier_endpoints.endpoint is a FK to routes.path — you cannot define a rate limit
-- policy for an endpoint that does not exist as a route.
CREATE TABLE routes (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    path       VARCHAR(255) NOT NULL UNIQUE,
    upstream   VARCHAR(255) NOT NULL,
    active     BOOLEAN      NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

INSERT INTO routes (id, path, upstream, active) VALUES
    ('e0000000-0000-0000-0000-000000000001', '/v1/infer',      'http://stub:4000', true),
    ('e0000000-0000-0000-0000-000000000002', '/v1/models',     'http://stub:4000', true),
    ('e0000000-0000-0000-0000-000000000003', '/v1/downstream', 'http://stub:4000', true);


-- Tier Endpoints
-- Per-endpoint rate limit overrides per tier.
-- Falls back to global tier limits (tiers.capacity / tiers.refill_per_sec) when no row exists.
CREATE TABLE tier_endpoints (
    id             UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_id        UUID           NOT NULL REFERENCES tiers(id),
    endpoint       VARCHAR(255)   NOT NULL REFERENCES routes(path),
    capacity       INTEGER        NOT NULL,
    refill_per_sec NUMERIC(10, 4) NOT NULL,
    UNIQUE (tier_id, endpoint)
);

-- /v1/infer: GPU inference, expensive — ~20% of global tier capacity
-- /v1/models: cheap read — ~2x global tier capacity
-- /v1/downstream: local dev stub
INSERT INTO tier_endpoints (tier_id, endpoint, capacity, refill_per_sec) VALUES
    ('c0000000-0000-0000-0000-000000000001', '/v1/infer',       5,     0.0833),
    ('c0000000-0000-0000-0000-000000000002', '/v1/infer',       25,    0.4167),
    ('c0000000-0000-0000-0000-000000000003', '/v1/infer',       100,   1.6667),
    ('c0000000-0000-0000-0000-000000000004', '/v1/infer',       50,    0.8333),
    ('c0000000-0000-0000-0000-000000000005', '/v1/infer',       200,   3.3333),
    ('c0000000-0000-0000-0000-000000000006', '/v1/infer',       1000,  16.6667),
    ('c0000000-0000-0000-0000-000000000007', '/v1/infer',       99999, 9999.0),
    ('c0000000-0000-0000-0000-000000000001', '/v1/models',      50,    0.8333),
    ('c0000000-0000-0000-0000-000000000002', '/v1/models',      240,   4.0000),
    ('c0000000-0000-0000-0000-000000000003', '/v1/models',      1200,  20.0000),
    ('c0000000-0000-0000-0000-000000000004', '/v1/models',      600,   10.0000),
    ('c0000000-0000-0000-0000-000000000005', '/v1/models',      2400,  40.0000),
    ('c0000000-0000-0000-0000-000000000006', '/v1/models',      12000, 200.0000),
    ('c0000000-0000-0000-0000-000000000007', '/v1/models',      99999, 9999.0),
    ('c0000000-0000-0000-0000-000000000001', '/v1/downstream',  10,    0.1667),
    ('c0000000-0000-0000-0000-000000000002', '/v1/downstream',  50,    0.8333),
    ('c0000000-0000-0000-0000-000000000003', '/v1/downstream',  200,   3.3333),
    ('c0000000-0000-0000-0000-000000000004', '/v1/downstream',  100,   1.6667),
    ('c0000000-0000-0000-0000-000000000005', '/v1/downstream',  400,   6.6667),
    ('c0000000-0000-0000-0000-000000000006', '/v1/downstream',  2000,  33.3333),
    ('c0000000-0000-0000-0000-000000000007', '/v1/downstream',  99999, 9999.0);


-- Users
CREATE TABLE users (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    default_tier  UUID         NOT NULL REFERENCES tiers(id),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- password_hash values are bcrypt hashes of 'password123'
INSERT INTO users (id, email, password_hash, default_tier, created_at) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'alice@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYpR0JRY1yCn7Ky', 'c0000000-0000-0000-0000-000000000003', now()),
    ('a0000000-0000-0000-0000-000000000002', 'bob@example.com',   '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYpR0JRY1yCn7Ky', 'c0000000-0000-0000-0000-000000000002', now()),
    ('a0000000-0000-0000-0000-000000000003', 'carol@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYpR0JRY1yCn7Ky', 'c0000000-0000-0000-0000-000000000001', now()),
    ('a0000000-0000-0000-0000-000000000004', 'dave@example.com',  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewYpR0JRY1yCn7Ky', 'c0000000-0000-0000-0000-000000000002', now());


-- Sessions
CREATE TABLE sessions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ,
    revoke_reason TEXT,
    ip            INET,
    user_agent    TEXT
);

CREATE INDEX idx_sessions_user_active
    ON sessions(user_id, last_seen_at ASC)
    WHERE revoked_at IS NULL;


-- Refresh Tokens
CREATE TABLE refresh_tokens (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash    BYTEA       NOT NULL UNIQUE,
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    parent_id     UUID        REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    redeemed_at   TIMESTAMPTZ,
    grace_until   TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ,
    revoke_reason TEXT
);

CREATE INDEX idx_refresh_tokens_session
    ON refresh_tokens(session_id)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_refresh_tokens_user
    ON refresh_tokens(user_id)
    WHERE revoked_at IS NULL;


-- Service Clients
CREATE TABLE service_clients (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id          VARCHAR(255) NOT NULL UNIQUE,
    client_secret_hash VARCHAR(255) NOT NULL,
    name               VARCHAR(255) NOT NULL,
    tier               UUID         NOT NULL REFERENCES tiers(id),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    revoked_at         TIMESTAMPTZ
);


-- API Keys
CREATE TABLE api_keys (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash   BYTEA       NOT NULL UNIQUE,
    tier       UUID        NOT NULL REFERENCES tiers(id),
    name       VARCHAR(100),
    status     VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);

-- Test API keys
-- Raw keys (for local testing only, never stored):
--   alice:   test-key-premium-alice  (premium tier, active)
--   bob:     test-key-basic-bob      (basic tier, active)
--   carol:   test-key-free-carol     (free tier, active)
--   dave:    test-key-revoked-dave   (basic tier, revoked)
-- key_hash = SHA-256 of the raw key, stored as bytea
INSERT INTO api_keys (id, user_id, key_hash, tier, name, status, created_at, revoked_at) VALUES
    (
        'b0000000-0000-0000-0000-000000000001',
        'a0000000-0000-0000-0000-000000000001',
        sha256('test-key-premium-alice'::bytea),
        'c0000000-0000-0000-0000-000000000003',
        'Test key (alice)',
        'active',
        now(),
        NULL
    ),
    (
        'b0000000-0000-0000-0000-000000000002',
        'a0000000-0000-0000-0000-000000000002',
        sha256('test-key-basic-bob'::bytea),
        'c0000000-0000-0000-0000-000000000002',
        'Test key (bob)',
        'active',
        now(),
        NULL
    ),
    (
        'b0000000-0000-0000-0000-000000000003',
        'a0000000-0000-0000-0000-000000000003',
        sha256('test-key-free-carol'::bytea),
        'c0000000-0000-0000-0000-000000000001',
        'Test key (carol)',
        'active',
        now(),
        NULL
    ),
    (
        'b0000000-0000-0000-0000-000000000004',
        'a0000000-0000-0000-0000-000000000004',
        sha256('test-key-revoked-dave'::bytea),
        'c0000000-0000-0000-0000-000000000002',
        'Test key (dave)',
        'revoked',
        now(),
        now()
    );

-- Test service clients
-- inference-service: active, internal-standard tier
-- revoked-service:   revoked, internal-standard tier
INSERT INTO service_clients (id, client_id, client_secret_hash, name, tier, created_at, revoked_at) VALUES
    (
        'd0000000-0000-0000-0000-000000000001',
        'inference-service',
        'placeholder-hash',
        'ML Inference Service',
        'c0000000-0000-0000-0000-000000000005',
        now(),
        NULL
    ),
    (
        'd0000000-0000-0000-0000-000000000002',
        'revoked-service',
        'placeholder-hash',
        'Revoked Service',
        'c0000000-0000-0000-0000-000000000005',
        now(),
        now()
    );
