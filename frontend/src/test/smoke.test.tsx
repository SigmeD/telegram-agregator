import { render, screen } from '@testing-library/react';
import type { JSX } from 'react';
import { describe, expect, it } from 'vitest';

function Hello(): JSX.Element {
  return <h1>Telegram Lead Aggregator — Admin</h1>;
}

describe('smoke', () => {
  it('renders the admin heading', () => {
    render(<Hello />);
    expect(
      screen.getByRole('heading', { name: /Telegram Lead Aggregator — Admin/i }),
    ).toBeInTheDocument();
  });
});
