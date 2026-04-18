import { getClientId } from './client_id';
import { Request } from 'express';

function makeReq(overrides: object): Request {
  return {
    headers: {},
    cookies: {},
    socket: { remoteAddress: '1.2.3.4' },
    ...overrides,
  } as unknown as Request;
}

function makeJwt(payload: object): string {
  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const body   = Buffer.from(JSON.stringify(payload)).toString('base64url');
  return `${header}.${body}.fakesignature`;
}

describe('getClientId', () => {
  it('returns api-key type when X-API-Key header is present', () => {
    const req = makeReq({ headers: { 'x-api-key': 'test-key-premium-alice' } });
    expect(getClientId(req)).toEqual({ type: 'api-key', id: 'test-key-premium-alice' });
  });

  it('returns user-jwt type when Bearer JWT has sid claim', () => {
    const token = makeJwt({ sub: 'a0000000-0000-0000-0000-000000000001', sid: 'some-session-id' });
    const req = makeReq({ headers: { authorization: `Bearer ${token}` } });
    expect(getClientId(req)).toEqual({ type: 'user-jwt', id: 'a0000000-0000-0000-0000-000000000001' });
  });

  it('returns service-jwt type when Bearer JWT has no sid claim', () => {
    const token = makeJwt({ sub: 'my-inference-service' });
    const req = makeReq({ headers: { authorization: `Bearer ${token}` } });
    expect(getClientId(req)).toEqual({ type: 'service-jwt', id: 'my-inference-service' });
  });

  it('returns user-jwt type when access_token cookie JWT has sid claim', () => {
    const token = makeJwt({ sub: 'a0000000-0000-0000-0000-000000000002', sid: 'some-session-id' });
    const req = makeReq({ cookies: { access_token: token } });
    expect(getClientId(req)).toEqual({ type: 'user-jwt', id: 'a0000000-0000-0000-0000-000000000002' });
  });

  it('returns ip type with last IP from X-Forwarded-For', () => {
    const req = makeReq({ headers: { 'x-forwarded-for': '203.0.113.1, 10.0.0.1, 10.0.0.2' } });
    expect(getClientId(req)).toEqual({ type: 'ip', id: '10.0.0.2' });
  });

  it('returns ip type from remoteAddress when no other identifier is present', () => {
    const req = makeReq({});
    expect(getClientId(req)).toEqual({ type: 'ip', id: '1.2.3.4' });
  });

  it('returns unknown type when remoteAddress is undefined', () => {
    const req = makeReq({ socket: { remoteAddress: undefined } });
    expect(getClientId(req)).toEqual({ type: 'unknown', id: 'unknown' });
  });

  it('prefers X-API-Key over JWT', () => {
    const token = makeJwt({ sub: 'some-user-id', sid: 'sid' });
    const req = makeReq({
      headers: {
        'x-api-key': 'test-key-premium-alice',
        authorization: `Bearer ${token}`,
      },
    });
    expect(getClientId(req)).toEqual({ type: 'api-key', id: 'test-key-premium-alice' });
  });

  it('prefers Authorization header JWT over cookie JWT', () => {
    const headerToken = makeJwt({ sub: 'user-from-header', sid: 'sid' });
    const cookieToken = makeJwt({ sub: 'user-from-cookie', sid: 'sid' });
    const req = makeReq({
      headers: { authorization: `Bearer ${headerToken}` },
      cookies: { access_token: cookieToken },
    });
    expect(getClientId(req)).toEqual({ type: 'user-jwt', id: 'user-from-header' });
  });

  it('prefers JWT over X-Forwarded-For', () => {
    const token = makeJwt({ sub: 'some-user-id', sid: 'sid' });
    const req = makeReq({
      headers: {
        authorization: `Bearer ${token}`,
        'x-forwarded-for': '203.0.113.1',
      },
    });
    expect(getClientId(req)).toEqual({ type: 'user-jwt', id: 'some-user-id' });
  });
});
