import http from 'http';
import fs from 'fs';
import path from 'path';
import { AddressInfo } from 'net';
import request from 'supertest';
import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { RedisContainer, StartedRedisContainer } from '@testcontainers/redis';
import { PostgreSqlContainer, StartedPostgreSqlContainer } from '@testcontainers/postgresql';
import { createApp } from './app';
import { clearMemoryCache } from './policy_cache';
import { updateRoutes } from './route_table';

type App = ReturnType<typeof createApp>;

jest.setTimeout(120_000);

// ── helpers ──────────────────────────────────────────────────────────────────

function makeJwt(payload: object): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const body   = Buffer.from(JSON.stringify(payload)).toString('base64url');
  return `${header}.${body}.fakesignature`;
}

// ── shared state ──────────────────────────────────────────────────────────────

let redisContainer: StartedRedisContainer;
let pgContainer: StartedPostgreSqlContainer;
let redis: Redis;
let pool: Pool;
let app: App;
let stubServer: http.Server;

// ── setup / teardown ──────────────────────────────────────────────────────────

beforeAll(async () => {
  [redisContainer, pgContainer] = await Promise.all([
    new RedisContainer('redis:7-alpine').start(),
    new PostgreSqlContainer('postgres:16').start(),
  ]);

  redis = new Redis({
    host: redisContainer.getHost(),
    port: redisContainer.getPort(),
  });

  pool = new Pool({
    host:     pgContainer.getHost(),
    port:     pgContainer.getPort(),
    database: pgContainer.getDatabase(),
    user:     pgContainer.getUsername(),
    password: pgContainer.getPassword(),
  });

  const initSql = fs.readFileSync(
    path.join(__dirname, '../testdata/init.sql'),
    'utf8'
  );
  await pool.query(initSql);

  stubServer = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
  });
  await new Promise<void>(resolve => stubServer.listen(0, resolve));
  const stubPort = (stubServer.address() as AddressInfo).port;

  updateRoutes([{ path: '/v1/downstream', upstream: `http://localhost:${stubPort}` }]);
  app = createApp(redis, pool);
}, 120_000);

afterAll(async () => {
  await redis.quit();
  await pool.end();
  await new Promise<void>((resolve, reject) =>
    stubServer.close(err => (err ? reject(err) : resolve()))
  );
  await redisContainer.stop();
  await pgContainer.stop();
});

beforeEach(async () => {
  await redis.flushall();
  clearMemoryCache();
});

// ── tests ─────────────────────────────────────────────────────────────────────

it('health endpoint returns ok', async () => {
  const res = await request(app).get('/health');
  expect(res.status).toBe(200);
  expect(res.body).toEqual({ status: 'ok' });
});

it('carol (free tier, api-key) gets 200 with limit 10 (tier_endpoints for /v1/downstream)', async () => {
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-free-carol');

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('10');
  expect(res.headers['x-ratelimit-remaining']).toBe('9');
});

it('bob (basic tier, api-key) gets 200 with limit 50 (tier_endpoints for /v1/downstream)', async () => {
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-basic-bob');

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('50');
  expect(res.headers['x-ratelimit-remaining']).toBe('49');
});

it('alice (premium tier, api-key) gets 200 with limit 200 (tier_endpoints for /v1/downstream)', async () => {
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-premium-alice');

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('200');
  expect(res.headers['x-ratelimit-remaining']).toBe('199');
});

it('alice (premium tier, user-jwt) gets 200 with limit 200 (tier_endpoints for /v1/downstream)', async () => {
  const token = makeJwt({ sub: 'a0000000-0000-0000-0000-000000000001', sid: 'test-session-id' });
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('Authorization', `Bearer ${token}`);

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('200');
});

it('carol (free tier, user-jwt) gets 200 with limit 10 (tier_endpoints for /v1/downstream)', async () => {
  const token = makeJwt({ sub: 'a0000000-0000-0000-0000-000000000003', sid: 'test-session-id' });
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('Authorization', `Bearer ${token}`);

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('10');
});

it('inference-service (internal-standard, service-jwt) gets 200 with limit 400 (tier_endpoints for /v1/downstream)', async () => {
  const token = makeJwt({ sub: 'inference-service' }); // no sid → service-jwt
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('Authorization', `Bearer ${token}`);

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('400');
});

it('carol (free tier, api-key) gets 429 after exhausting the bucket', async () => {
  const statuses: number[] = [];
  for (let i = 0; i < 11; i++) {
    const res = await request(app)
      .get('/v1/downstream/hello')
      .set('X-API-Key', 'test-key-free-carol');
    statuses.push(res.status);
  }

  expect(statuses.filter(s => s === 200).length).toBe(10);
  expect(statuses.filter(s => s === 429).length).toBe(1);
});

it('revoked api-key (dave) falls back to free tier', async () => {
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-revoked-dave');

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('25');
});

it('revoked service client falls back to free tier', async () => {
  const token = makeJwt({ sub: 'revoked-service' }); // no sid → service-jwt
  const res = await request(app)
    .get('/v1/downstream/hello')
    .set('Authorization', `Bearer ${token}`);

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('25');
});

it('unknown client (no credentials) falls back to free tier', async () => {
  const res = await request(app).get('/v1/downstream/hello');

  expect(res.status).toBe(200);
  expect(res.headers['x-ratelimit-limit']).toBe('25');
});

it('policy is written to Redis with endpoint in the key', async () => {
  await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-free-carol');

  const cached = await redis.hgetall('policy:api-key:test-key-free-carol:/v1/downstream');
  expect(cached.capacity).toBe('10');
  expect(cached.refillPerSec).toBe('0.1667');
});

it('token bucket key includes the matched endpoint', async () => {
  await request(app)
    .get('/v1/downstream/hello')
    .set('X-API-Key', 'test-key-free-carol');

  const bucket = await redis.hgetall('tb:test-key-free-carol:/v1/downstream');
  expect(bucket.tokens).toBeDefined();
});
