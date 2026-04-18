import express from 'express';
import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { registerProxy } from './proxy';
import { rateLimitMiddleware } from './rate_limit';

export function createApp(redis: Redis, pool: Pool): express.Application {
  const app = express();

  app.get('/health', (req, res) => {
    res.json({ status: 'ok' });
  });

  app.use(rateLimitMiddleware(redis, pool));
  registerProxy(app);

  return app;
}
