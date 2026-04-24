import type { JSX } from 'react';

export const metadata = {
  title: 'Триггеры — Telegram Lead Aggregator',
};

export default function TriggersPage(): JSX.Element {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Триггеры</h1>
        <p className="text-sm text-muted-foreground">
          CRUD ключевых слов, A/B-тесты, аналитика эффективности. TODO.
        </p>
      </header>
      <section className="rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Placeholder: список триггеров.</p>
      </section>
    </main>
  );
}
