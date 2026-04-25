import { Redis } from 'ioredis';

const BUCKET_TTL_SECONDS = 3600;

const SCRIPT = `
local key          = KEYS[1]
local capacity     = tonumber(ARGV[1])
local refill_rate  = tonumber(ARGV[2])
local now          = tonumber(ARGV[3])
local ttl          = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'lastRefill')
local tokens      = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
  tokens      = capacity
  last_refill = now
end

local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HSET', key, 'tokens', tokens, 'lastRefill', now)
  redis.call('EXPIRE', key, ttl)
  return tokens
else
  redis.call('HSET', key, 'tokens', tokens, 'lastRefill', now)
  redis.call('EXPIRE', key, ttl)
  return -1
end
`;

export async function consumeToken(
  redis: Redis,
  bucketKey: string,
  capacity: number,
  refillPerSec: number
): Promise<number> {
  const key = `tb:${bucketKey}`;
  const now = Date.now() / 1000;
  const result = await redis.eval(SCRIPT, 1, key, capacity, refillPerSec, now, BUCKET_TTL_SECONDS);
  return result as number;
}
