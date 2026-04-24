/**
 * Typed fetch wrapper around the backend API.
 *
 * Base URL is resolved from `NEXT_PUBLIC_API_URL`. On the client this is
 * embedded at build time; on the server it is read at runtime.
 *
 * All errors surface as `ApiError` to give UI code a single type to catch.
 */

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  readonly body?: unknown;
  readonly searchParams?: Readonly<Record<string, string | number | boolean | undefined>>;
  readonly token?: string;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly payload: unknown;

  public constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

function resolveBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (url === undefined || url === '') {
    return '/api';
  }
  return url.replace(/\/$/, '');
}

function buildUrl(
  path: string,
  searchParams?: ApiRequestOptions['searchParams'],
): string {
  const base = resolveBaseUrl();
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const url = `${base}${normalized}`;
  if (searchParams === undefined) {
    return url;
  }
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (value !== undefined) {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query === '' ? url : `${url}?${query}`;
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { body, headers, searchParams, token, ...rest } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set('Accept', 'application/json');
  if (body !== undefined) {
    finalHeaders.set('Content-Type', 'application/json');
  }
  if (token !== undefined && token !== '') {
    finalHeaders.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(buildUrl(path, searchParams), {
    ...rest,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const contentType = response.headers.get('content-type') ?? '';
  const payload: unknown = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}
