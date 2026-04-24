import type { Metadata } from 'next';
import type { JSX, ReactNode } from 'react';

import './globals.css';
import { Providers } from '@/components/providers';

export const metadata: Metadata = {
  title: 'Telegram Lead Aggregator — Admin',
  description:
    'Admin panel for the Telegram Lead Aggregator: manage leads, sources, triggers, and analytics.',
};

interface RootLayoutProps {
  readonly children: ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps): JSX.Element {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
