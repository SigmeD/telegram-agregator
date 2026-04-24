/**
 * JWT verification stub.
 *
 * Real implementation will verify the access token issued by the backend
 * (HS256 / RS256 — decided in FEATURE-09 auth sub-task) using `jose`.
 */
import { jwtVerify, type JWTPayload } from 'jose';

export interface AdminSession {
  readonly userId: string;
  readonly email: string;
  readonly role: 'admin' | 'viewer';
  readonly expiresAt: number;
}

function resolveSecret(): Uint8Array {
  const secret = process.env.JWT_SECRET;
  if (secret === undefined || secret === '') {
    throw new Error('JWT_SECRET is not configured');
  }
  return new TextEncoder().encode(secret);
}

function isAdminPayload(payload: JWTPayload): payload is JWTPayload & {
  sub: string;
  email: string;
  role: 'admin' | 'viewer';
  exp: number;
} {
  return (
    typeof payload.sub === 'string' &&
    typeof (payload as { email?: unknown }).email === 'string' &&
    ((payload as { role?: unknown }).role === 'admin' ||
      (payload as { role?: unknown }).role === 'viewer') &&
    typeof payload.exp === 'number'
  );
}

export async function verifySession(token: string): Promise<AdminSession | null> {
  try {
    const { payload } = await jwtVerify(token, resolveSecret());
    if (!isAdminPayload(payload)) {
      return null;
    }
    return {
      userId: payload.sub,
      email: payload.email,
      role: payload.role,
      expiresAt: payload.exp * 1000,
    };
  } catch {
    return null;
  }
}
