import { QueryClient } from '@tanstack/react-query';

/**
 * Factory for the TanStack Query client.
 *
 * A factory (rather than a module-level singleton) keeps SSR and tests
 * isolated: each render / each test gets a fresh client.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
