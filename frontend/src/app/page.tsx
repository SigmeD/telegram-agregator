import type { JSX } from 'react';

interface KpiCard {
  readonly id: string;
  readonly label: string;
  readonly placeholder: string;
}

const kpiCards: readonly KpiCard[] = [
  { id: 'leads-today', label: 'Лидов сегодня', placeholder: '—' },
  { id: 'leads-week', label: 'Лидов за неделю', placeholder: '—' },
  { id: 'leads-month', label: 'Лидов за месяц', placeholder: '—' },
  { id: 'hot-leads', label: 'Горячих лидов (Warm+)', placeholder: '—' },
];

export default function DashboardPage(): JSX.Element {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          KPI и динамика лидов. Подключение к backend API — TODO.
        </p>
      </header>

      <section
        aria-label="KPI cards"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {kpiCards.map((card) => (
          <article
            key={card.id}
            className="rounded-lg border border-border bg-card p-4 shadow-sm"
          >
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {card.label}
            </p>
            <p className="mt-2 text-3xl font-bold text-card-foreground">
              {card.placeholder}
            </p>
          </article>
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <article className="rounded-lg border border-border bg-card p-4">
          <h2 className="text-lg font-medium">Динамика лидов</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            TODO: график по дням (recharts / TanStack chart).
          </p>
        </article>
        <article className="rounded-lg border border-border bg-card p-4">
          <h2 className="text-lg font-medium">Топ-10 источников</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            TODO: таблица конверсии по источникам.
          </p>
        </article>
      </section>
    </main>
  );
}
