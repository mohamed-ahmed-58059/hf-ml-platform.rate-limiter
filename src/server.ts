import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { config } from './config';
import { loadRoutes, startRoutePolling } from './route_loader';
import { createApp } from './app';
import { startCacheInvalidator } from './cache_invalidator';

async function start(): Promise<void> {
  const redis = new Redis({
    host: config.redis.host,
    port: config.redis.port,
  });

  const pool = new Pool({
    host:     config.postgres.host,
    port:     config.postgres.port,
    user:     config.postgres.user,
    password: config.postgres.password,
    database: config.postgres.database,
    ssl:      config.postgres.ssl ? { rejectUnauthorized: false } : false,
  });

  await loadRoutes(pool);
  startRoutePolling(pool);

  const app = createApp(redis, pool);

  app.listen(config.port, () => {
    console.log(`[rate-limiter] running on port ${config.port}`);
    startCacheInvalidator(redis, {
      queueUrl:    config.aws.queueUrl,
      region:      config.aws.region,
      endpointUrl: config.aws.endpointUrl || undefined,
    });
  });
}

start().catch(err => {
  console.error('[server] failed to start:', err);
  process.exit(1);
});
