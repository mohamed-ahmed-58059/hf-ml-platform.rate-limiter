import { Redis } from 'ioredis';
import { RedisContainer, StartedRedisContainer } from '@testcontainers/redis';
import { consumeToken } from './token_bucket';

describe('consumeToken', () => {
  let container: StartedRedisContainer;
  let redis: Redis;

  beforeAll(async () => {
    container = await new RedisContainer('redis:7-alpine').start();
    redis = new Redis({ host: container.getHost(), port: container.getPort() });
  }, 30000);

  afterAll(async () => {
    await redis.quit();
    await container.stop();
  });

  beforeEach(async () => {
    await redis.flushall();
  });

  it('allows a request when the bucket is full', async () => {
    const remaining = await consumeToken(redis, 'test-client', 10, 1);
    expect(remaining).toBeGreaterThanOrEqual(0);
  });

  it('rejects a request when the bucket is empty', async () => {
    for (let i = 0; i < 10; i++) {
      await consumeToken(redis, 'test-client', 10, 1);
    }
    const remaining = await consumeToken(redis, 'test-client', 10, 1);
    expect(remaining).toBe(-1);
  });

  it('refills tokens over time', async () => {
    for (let i = 0; i < 10; i++) {
      await consumeToken(redis, 'test-client', 10, 1);
    }

    // simulate 5 seconds elapsed by backdating lastRefill
    const key = 'tb:test-client';
    const lastRefill = Date.now() / 1000 - 5;
    await redis.hset(key, 'lastRefill', lastRefill);

    const remaining = await consumeToken(redis, 'test-client', 10, 1);
    expect(remaining).toBeGreaterThanOrEqual(0);
  });

  it('does not exceed capacity when refilling', async () => {
    // bucket starts full (capacity 5), simulate 100 seconds elapsed
    const key = 'tb:test-client';
    await redis.hset(key, 'tokens', 5, 'lastRefill', Date.now() / 1000 - 100);

    await consumeToken(redis, 'test-client', 5, 1);

    const tokens = parseFloat(await redis.hget(key, 'tokens') ?? '0');
    expect(tokens).toBeLessThanOrEqual(4);
  });
});
