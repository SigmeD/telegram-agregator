import type { JSX } from 'react';

export const metadata = {
  title: 'Источники — Telegram Lead Aggregator',
};

export default function SourcesPage(): JSX.Element {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Источники</h1>
        <p className="text-sm text-muted-foreground">
          CRUD для Telegram-чатов, статистика, массовый импорт. TODO.
        </p>
      </header>
      <section className="rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Placeholder: список источников.</p>
      </section>
    </main>
  );
}
