import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { ClientId } from './client_id';
import { Policy, PolicyNotFoundError, resolvePolicy } from './policy_resolver';

const FREE_TIER: Policy = { capacity: 25, refillPerSec: 0.3333 };

const IN_MEMORY_TTL_MS = 2_000;
const REDIS_TTL_SECONDS = 1_800;

interface CacheEntry {
  policy: Policy;
  expiresAt: number;
}

const memoryCache = new Map<string, CacheEntry>();

export function clearMemoryCache(): void {
  memoryCache.clear();
}

function cacheKey(clientId: ClientId, endpoint: string): string {
  return `${clientId.type}:${clientId.id}:${endpoint}`;
}

function readMemory(key: string): Policy | undefined {
  const entry = memoryCache.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiresAt) {
    memoryCache.delete(key);
    return undefined;
  }
  return entry.policy;
}

function writeMemory(key: string, policy: Policy): void {
  memoryCache.set(key, { policy, expiresAt: Date.now() + IN_MEMORY_TTL_MS });
}

async function readRedis(redis: Redis, key: string): Promise<Policy | undefined> {
  const raw = await redis.hgetall(`policy:${key}`);
  if (!raw.capacity || !raw.refillPerSec) return undefined;
  return { capacity: parseFloat(raw.capacity), refillPerSec: parseFloat(raw.refillPerSec) };
}

async function writeRedis(redis: Redis, key: string, policy: Policy): Promise<void> {
  await redis.hset(`policy:${key}`, 'capacity', policy.capacity, 'refillPerSec', policy.refillPerSec);
  await redis.expire(`policy:${key}`, REDIS_TTL_SECONDS);
}

export async function getPolicy(redis: Redis, pool: Pool, clientId: ClientId, endpoint: string): Promise<Policy> {
  const key = cacheKey(clientId, endpoint);

  // 1. In-memory cache
  const fromMemory = readMemory(key);
  if (fromMemory) return fromMemory;

  // 2. Redis cache
  try {
    const fromRedis = await readRedis(redis, key);
    if (fromRedis) {
      writeMemory(key, fromRedis);
      return fromRedis;
    }
  } catch {
    // Redis is down — skip to Postgres
  }

  // 3. Postgres
  try {
    const policy = await resolvePolicy(pool, clientId, endpoint);
    writeMemory(key, policy);
    try {
      await writeRedis(redis, key, policy);
    } catch {
      // Redis write failed — not fatal, in-memory cache still works
    }
    return policy;
  } catch (err) {
    if (err instanceof PolicyNotFoundError) return FREE_TIER;
    throw err;
  }
}
