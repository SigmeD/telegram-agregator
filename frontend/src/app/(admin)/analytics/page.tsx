import type { JSX } from 'react';

export const metadata = {
  title: 'Аналитика — Telegram Lead Aggregator',
};

export default function AnalyticsPage(): JSX.Element {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Аналитика</h1>
        <p className="text-sm text-muted-foreground">
          Воронка лидов, стоимость лида, качество LLM, cost tracking. TODO.
        </p>
      </header>
      <section className="rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Placeholder: аналитика.</p>
      </section>
    </main>
  );
}
