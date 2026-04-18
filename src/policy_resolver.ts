import { Pool } from 'pg';
import { ClientId } from './client_id';

export interface Policy {
  capacity: number;
  refillPerSec: number;
}

export class PolicyNotFoundError extends Error {
  constructor(clientId: ClientId) {
    super(`no policy found for ${clientId.type}:${clientId.id}`);
    this.name = 'PolicyNotFoundError';
  }
}

export async function resolvePolicy(pool: Pool, clientId: ClientId, endpoint: string): Promise<Policy> {
  let row: { capacity: number; refill_per_sec: number } | undefined;

  if (clientId.type === 'api-key') {
    const result = await pool.query<{ capacity: number; refill_per_sec: number }>(
      `SELECT
         COALESCE(te.capacity,       t.capacity)       AS capacity,
         COALESCE(te.refill_per_sec, t.refill_per_sec) AS refill_per_sec
       FROM api_keys ak
       JOIN tiers t ON ak.tier = t.id
       LEFT JOIN tier_endpoints te ON te.tier_id = t.id AND te.endpoint = $2
       WHERE ak.key_hash = sha256($1::bytea) AND ak.status = 'active'`,
      [clientId.id, endpoint]
    );
    row = result.rows[0];

  } else if (clientId.type === 'user-jwt') {
    const result = await pool.query<{ capacity: number; refill_per_sec: number }>(
      `SELECT
         COALESCE(te.capacity,       t.capacity)       AS capacity,
         COALESCE(te.refill_per_sec, t.refill_per_sec) AS refill_per_sec
       FROM users u
       JOIN tiers t ON u.default_tier = t.id
       LEFT JOIN tier_endpoints te ON te.tier_id = t.id AND te.endpoint = $2
       WHERE u.id = $1`,
      [clientId.id, endpoint]
    );
    row = result.rows[0];

  } else if (clientId.type === 'service-jwt') {
    const result = await pool.query<{ capacity: number; refill_per_sec: number }>(
      `SELECT
         COALESCE(te.capacity,       t.capacity)       AS capacity,
         COALESCE(te.refill_per_sec, t.refill_per_sec) AS refill_per_sec
       FROM service_clients sc
       JOIN tiers t ON sc.tier = t.id
       LEFT JOIN tier_endpoints te ON te.tier_id = t.id AND te.endpoint = $2
       WHERE sc.client_id = $1 AND sc.revoked_at IS NULL`,
      [clientId.id, endpoint]
    );
    row = result.rows[0];

  } else {
    // ip / unknown — no DB lookup, caller falls back to free tier
    throw new PolicyNotFoundError(clientId);
  }

  if (!row) throw new PolicyNotFoundError(clientId);

  return { capacity: row.capacity, refillPerSec: Number(row.refill_per_sec) };
}
