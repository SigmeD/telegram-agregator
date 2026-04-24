'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import { useState, type JSX, type ReactNode } from 'react';

import { createQueryClient } from '@/lib/query-client';

interface ProvidersProps {
  readonly children: ReactNode;
}

export function Providers({ children }: ProvidersProps): JSX.Element {
  const [queryClient] = useState(() => createQueryClient());

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
