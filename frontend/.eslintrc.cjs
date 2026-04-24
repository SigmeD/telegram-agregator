/** @type {import('eslint').Linter.Config} */
module.exports = {
  root: true,
  extends: ['next/core-web-vitals', 'prettier'],
  rules: {
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/consistent-type-imports': [
      'warn',
      { prefer: 'type-imports' },
    ],
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
  ignorePatterns: ['.next/', 'node_modules/', 'dist/'],
};
