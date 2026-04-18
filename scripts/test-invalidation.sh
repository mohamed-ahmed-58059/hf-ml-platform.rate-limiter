#!/bin/bash
# Test cache invalidation end-to-end against a running docker compose stack.
# Run from the repo root: ./hf-ml-platform.rate-limiter/scripts/test-invalidation.sh

set -euo pipefail

RATE_LIMITER_URL="http://localhost:3000"
TOPIC_ARN="arn:aws:sns:us-east-1:000000000000:tier-policy-changed"
REDIS_KEY="policy:api-key:test-key-free-carol:/v1/downstream"

REDIS=$(docker ps --filter "ancestor=redis:7-alpine" --format "{{.ID}}" | head -1)
LOCALSTACK=$(docker ps --filter "ancestor=localstack/localstack:3" --format "{{.ID}}" | head -1)

# ── helpers ───────────────────────────────────────────────────────────────────

pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; exit 1; }

redis_get() {
  docker exec "$REDIS" redis-cli hget "$REDIS_KEY" "$1"
}

redis_exists() {
  docker exec "$REDIS" redis-cli exists "$REDIS_KEY"
}

wait_for_eviction() {
  local timeout=10
  local elapsed=0
  while [ "$(redis_exists)" = "1" ]; do
    if [ "$elapsed" -ge "$timeout" ]; then
      fail "Key was not evicted within ${timeout}s"
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
}

# ── tests ─────────────────────────────────────────────────────────────────────

echo ""
echo "=== Cache Invalidation Test ==="
echo ""

# 1. Seed the cache via a real request
echo "1. Sending request to cache carol's policy..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RATE_LIMITER_URL/v1/downstream/hello" \
  -H "X-API-Key: test-key-free-carol")
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
pass "Request returned 200"

# 2. Assert key is in Redis with version 1
echo "2. Checking Redis for cached policy..."
VERSION=$(redis_get version)
[ "$VERSION" = "1" ] || fail "Expected version=1 in Redis, got '$VERSION'"
CAPACITY=$(redis_get capacity)
[ "$CAPACITY" = "10" ] || fail "Expected capacity=10 in Redis, got '$CAPACITY'"
pass "Policy cached in Redis (capacity=$CAPACITY, version=$VERSION)"

# 3. Publish invalidation event
echo "3. Publishing SNS invalidation event (newVersion=2)..."
docker exec "$LOCALSTACK" awslocal sns publish \
  --region us-east-1 \
  --topic-arn "$TOPIC_ARN" \
  --message '{"clientType":"api-key","clientId":"test-key-free-carol","newVersion":2}' \
  > /dev/null
pass "Event published"

# 4. Wait for key to be evicted
echo "4. Waiting for Redis key to be evicted..."
wait_for_eviction
pass "Key evicted from Redis"

# 5. Make another request — triggers re-fetch from Postgres
echo "5. Sending request to re-populate cache from Postgres..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$RATE_LIMITER_URL/v1/downstream/hello" \
  -H "X-API-Key: test-key-free-carol")
[ "$STATUS" = "200" ] || fail "Expected 200, got $STATUS"
pass "Request returned 200"

# 6. Assert key is back in Redis
echo "6. Checking Redis is re-populated..."
VERSION=$(redis_get version)
[ "$VERSION" = "1" ] || fail "Expected version=1 after re-fetch, got '$VERSION'"
CAPACITY=$(redis_get capacity)
[ "$CAPACITY" = "10" ] || fail "Expected capacity=10 after re-fetch, got '$CAPACITY'"
pass "Policy re-cached in Redis (capacity=$CAPACITY, version=$VERSION)"

# 7. Publish stale event (newVersion=1, same as cached) — should be ignored
echo "7. Publishing stale event (newVersion=1, same as cached)..."
docker exec "$LOCALSTACK" awslocal sns publish \
  --region us-east-1 \
  --topic-arn "$TOPIC_ARN" \
  --message '{"clientType":"api-key","clientId":"test-key-free-carol","newVersion":1}' \
  > /dev/null
sleep 3
EXISTS=$(redis_exists)
[ "$EXISTS" = "1" ] || fail "Key was evicted by a stale event — it should have been ignored"
pass "Stale event ignored, key still in Redis"

echo ""
echo "=== All tests passed ==="
echo ""
