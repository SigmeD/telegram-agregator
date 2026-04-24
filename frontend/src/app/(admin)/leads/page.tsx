import type { JSX } from 'react';

export const metadata = {
  title: 'Лиды — Telegram Lead Aggregator',
};

export default function LeadsPage(): JSX.Element {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Лиды</h1>
        <p className="text-sm text-muted-foreground">
          Таблица лидов с фильтрами (статус, score, источник, дата). TODO: TanStack Table.
        </p>
      </header>
      <section className="rounded-lg border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">Placeholder: список лидов.</p>
      </section>
    </main>
  );
}
