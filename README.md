# hf-ml-platform.rate-limiter

![CI](https://github.com/mohamed-ahmed-58059/hf-ml-platform.rate-limiter/actions/workflows/ci.yml/badge.svg)

Public entry point for the HuggingFace ML Platform. Sits behind
CloudFront and an Application Load Balancer, identifies clients,
applies tier-based rate limiting, and proxies authorized requests to
upstream services.

## Capabilities

| | Notes |
|---|---|
| **Reverse proxy** | Routes resolved against a Postgres `routes` table cached in memory and refreshed every 30s |
| **Token bucket rate limiting** | Atomic Redis Lua script (lazy refill + decrement); per-client per-endpoint buckets with a 1-hour TTL so abandoned buckets evict |
| **Client identification** | API key (SHA-256 hashed before any cache use), Bearer JWT, `access_token` cookie, or X-Forwarded-For client IP — in that precedence |
| **Three-tier policy cache** | In-memory (2s) → Redis (30 min) → Postgres direct read |
| **Event-driven invalidation** | Long-poll consumer on the cache-invalidation SQS queue evicts stale Redis entries on tier / API key changes |
| **Internal route guard** | `/internal/*` paths blocked at the ALB plus an application-level guard against URL-encoded bypasses (e.g. `/%69nternal/...`) |
| **CloudFront-only origin** | ALB ingress is locked to the AWS-managed CloudFront origin-facing prefix list |
| **CORS** | Configured for `https://editor.swagger.io` for live API-spec demos |

## How it identifies a client

```
X-Api-Key             → sha256(rawKey) hex   → tier from api_keys
Authorization: Bearer → sub claim            → tier from users (if sid claim) or service_clients (if not)
access_token cookie   → same as above
X-Forwarded-For       → trim trusted-proxy-hops trailing IPs → IP-bucket
remoteAddress         → IP-bucket
none of the above     → "unknown" shared bucket
```

## How it rate-limits

The atomic Lua script does lazy refill + decrement in a single Redis
call. Returns the remaining tokens; `-1` means the bucket is empty.
Bucket key shape: `tb:<hashed-client-id>:<endpoint>`. Each access
sets a 1-hour `EXPIRE` so spam from unique fake client IDs cannot
permanently fill Redis.

`X-RateLimit-Limit` and `X-RateLimit-Remaining` are returned on every
proxied response; 429 responses include the same headers.

## Tech stack

- TypeScript + Node 22
- Express 5.2
- `http-proxy-middleware` for upstream routing
- `ioredis` for Redis
- `pg` for direct Postgres reads
- AWS SDK v3 for SQS (cache invalidation)

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `3000` | |
| `TRUSTED_PROXY_HOPS` | `1` | Set to `2` in production (CloudFront + ALB) |
| `REDIS_HOST`, `REDIS_PORT` | from SSM | |
| `POSTGRES_HOST`, `POSTGRES_DB` | from SSM | |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | from Secrets Manager | |
| `POSTGRES_SSL` | `true` | Set to `false` only for local dev |
| `SNS_TOPIC_ARN` | required | Cache invalidation SNS topic |
| `SQS_QUEUE_URL` | required | Cache invalidation SQS queue |

## Failure modes

| Component down | Behavior |
|---|---|
| Postgres | Falls back to free-tier policy; data plane stays up |
| Redis | Fails closed (HTTP 500); rate limiting is the primary defense, fail-open is worse |
| SQS | Cache invalidator logs and continues; cached policies stay until TTL expiry |
