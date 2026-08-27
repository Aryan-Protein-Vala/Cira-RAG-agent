// Flat config for Next 16. The previous `"lint": "eslint ."` script was broken
// outright — eslint was not a dependency, so it exited 127 (`eslint: not found`)
// and nobody noticed because CI did not exist.
import coreWebVitals from 'eslint-config-next/core-web-vitals'
import typescript from 'eslint-config-next/typescript'

export default [
  ...coreWebVitals,
  ...typescript,
  {
    ignores: ['.next/**', 'out/**', 'node_modules/**', 'next-env.d.ts'],
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' },
      ],
      'react-hooks/exhaustive-deps': 'warn',
      '@next/next/no-img-element': 'warn',
      // React Compiler rules: this app is not compiled with the compiler, and the
      // codebase deliberately reads localStorage/theme + session state in an
      // init effect. Keep them visible as warnings, not build-blocking errors.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/preserve-manual-memoization': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/incompatible-library': 'warn',
      'react-hooks/immutability': 'warn',
    },
  },
]
