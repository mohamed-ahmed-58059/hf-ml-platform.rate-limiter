import { Pool } from 'pg';
import { updateRoutes, Route } from './route_table';

export async function loadRoutes(pool: Pool): Promise<void> {
  const result = await pool.query<Route>(
    'SELECT path, upstream FROM routes WHERE active = true'
  );
  updateRoutes(result.rows);
  console.log(`[route-loader] loaded ${result.rows.length} routes`);
}

export function startRoutePolling(pool: Pool, intervalMs = 30_000): NodeJS.Timeout {
  return setInterval(async () => {
    try {
      await loadRoutes(pool);
    } catch (err) {
      console.error('[route-loader] failed to refresh routes:', err);
    }
  }, intervalMs);
}
