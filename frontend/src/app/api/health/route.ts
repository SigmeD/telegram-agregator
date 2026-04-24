import { NextResponse } from 'next/server';

interface HealthResponse {
  readonly status: 'ok';
  readonly service: 'admin';
  readonly timestamp: string;
}

export function GET(): NextResponse<HealthResponse> {
  return NextResponse.json({
    status: 'ok',
    service: 'admin',
    timestamp: new Date().toISOString(),
  });
}
