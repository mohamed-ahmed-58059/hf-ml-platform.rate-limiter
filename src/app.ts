import express from 'express';
import cookieParser from 'cookie-parser';
import cors from 'cors';
import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { registerProxy } from './proxy';
import { rateLimitMiddleware } from './rate_limit';

export function createApp(redis: Redis, pool: Pool): express.Application {
  const app = express();

  app.use(cors({
    origin: ['https://editor.swagger.io'],
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Api-Key'],
    exposedHeaders: ['X-RateLimit-Limit', 'X-RateLimit-Remaining'],
  }));

  app.get('/health', (req, res) => {
    res.json({ status: 'ok' });
  });

  app.use(cookieParser());
  app.use(rateLimitMiddleware(redis, pool));
  registerProxy(app);

  return app;
}
