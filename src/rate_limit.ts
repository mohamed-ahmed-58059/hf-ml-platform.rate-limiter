import { Request, Response, NextFunction } from 'express';
import { Redis } from 'ioredis';
import { Pool } from 'pg';
import { getClientId } from './client_id';
import { consumeToken } from './token_bucket';
import { getPolicy } from './policy_cache';
import { matchEndpoint } from './route_table';

export function rateLimitMiddleware(redis: Redis, pool: Pool) {
  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const clientId  = getClientId(req);
    const endpoint  = matchEndpoint(req.path);
    const policy    = await getPolicy(redis, pool, clientId, endpoint);
    const bucketKey = `${clientId.id}:${endpoint}`;
    const remaining = await consumeToken(redis, bucketKey, policy.capacity, policy.refillPerSec);

    res.setHeader('X-RateLimit-Limit',     policy.capacity);
    res.setHeader('X-RateLimit-Remaining', Math.max(0, remaining));

    if (remaining < 0) {
      res.status(429).json({ error: 'rate limit exceeded' });
      return;
    }

    next();
  };
}
