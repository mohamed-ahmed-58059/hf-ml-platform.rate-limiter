import { Request } from 'express';

export type ClientId =
  | { type: 'api-key';     id: string }
  | { type: 'user-jwt';    id: string }  // JWT with sid claim (user session)
  | { type: 'service-jwt'; id: string }  // JWT without sid claim (service token)
  | { type: 'ip';          id: string }
  | { type: 'unknown';     id: string }

function decodeJwt(token: string): { sub: string; hasSid: boolean } {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('invalid jwt format');
  const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  if (typeof payload.sub !== 'string') throw new Error('missing sub claim');
  return { sub: payload.sub, hasSid: typeof payload.sid === 'string' };
}

export function getClientId(req: Request): ClientId {
  // 1. API key
  const apiKey = req.headers['x-api-key'];
  if (typeof apiKey === 'string' && apiKey.length > 0) {
    return { type: 'api-key', id: apiKey };
  }

  // 2. Authorization: Bearer <jwt>
  try {
    const authHeader = req.headers['authorization'];
    if (typeof authHeader === 'string' && authHeader.startsWith('Bearer ')) {
      const { sub, hasSid } = decodeJwt(authHeader.slice(7));
      return { type: hasSid ? 'user-jwt' : 'service-jwt', id: sub };
    }
  } catch { /* fall through to next option */ }

  // 3. Cookie: access_token=<jwt>
  try {
    const cookieToken = req.cookies?.access_token;
    if (typeof cookieToken === 'string') {
      const { sub, hasSid } = decodeJwt(cookieToken);
      return { type: hasSid ? 'user-jwt' : 'service-jwt', id: sub };
    }
  } catch { /* fall through to next option */ }

  // 4. X-Forwarded-For — use last IP (ALB always appends real client IP last)
  const forwarded = req.headers['x-forwarded-for'];
  if (typeof forwarded === 'string' && forwarded.length > 0) {
    const ips = forwarded.split(',').map(ip => ip.trim());
    return { type: 'ip', id: ips[ips.length - 1] };
  }

  // 5. Fallback — unknown clients share a single bucket and rate limit each other
  const remoteAddr = req.socket.remoteAddress;
  if (remoteAddr) return { type: 'ip', id: remoteAddr };
  return { type: 'unknown', id: 'unknown' };
}
