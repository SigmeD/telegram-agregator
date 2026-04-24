/**
 * PostCSS config for Tailwind 4.
 *
 * Tailwind 4 ships its own PostCSS plugin (`@tailwindcss/postcss`).
 * With Next.js 15 + Tailwind 4 you may instead use the dedicated
 * `@tailwindcss/postcss` or the new `@import "tailwindcss"` pipeline.
 */
const config = {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};

export default config;
