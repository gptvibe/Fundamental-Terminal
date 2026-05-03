# Frontend Dependency Reproducibility

## Current Setup

`frontend/package.json` uses caret (`^`) ranges for all dependencies.
`frontend/package-lock.json` (lockfile version 3) is committed to the
repository.  The `frontend/Dockerfile` installs dependencies with `npm ci`,
which completely ignores the ranges in `package.json` and installs the exact
versions recorded in the lockfile.

## Why the Lockfile Is Sufficient for CI/CD

`npm ci`:
- reads `package-lock.json` exclusively for version resolution
- fails if `package-lock.json` is missing or out of sync with `package.json`
- produces a byte-for-byte reproducible `node_modules` across every Docker build

The Docker image build, which is the production artifact, therefore installs
identical package versions regardless of when it is built.  The resolved
versions as of the last `npm install` run are:

| Package | Range in package.json | Resolved version |
|---|---|---|
| `next` | `^14.2.0` | `14.2.35` |
| `react` | `^18.2.0` | `18.3.1` |
| `react-dom` | `^18.2.0` | `18.3.1` |
| `typescript` | `^5.7.2` | `5.9.3` |
| `vitest` | `^2.1.8` | `2.1.9` |
| `@playwright/test` | `^1.54.2` | `1.58.2` |

## Residual Risk: Local `npm install`

Running `npm install` locally (rather than `npm ci`) resolves within the caret
ranges and can update the lockfile.  This means a developer who runs
`npm install` could silently bump a package to a newer patch or minor version
and commit a changed lockfile, which then changes what CI/CD builds.

Caret ranges never permit a **major** version upgrade (e.g., `^14.2.0` cannot
resolve to Next.js 15), so the blast radius of any individual lockfile drift is
limited to minor/patch changes within the same major version.

## Recommendation

- **No immediate change required.**  Docker image builds use `npm ci` and are
  reproducible.
- **Always use `npm ci` for local installs** in development environments that
  must match production exactly:

  ```bash
  npm ci        # install exactly what's in the lockfile
  ```

  Use `npm install` only when the intent is to update the lockfile (e.g., when
  intentionally upgrading a package).

- **Treat a changed `package-lock.json` as a significant diff** in code review.
  Confirm the diff is intentional before merging.

- If stricter pinning becomes necessary in the future, exact-pin only the
  critical framework packages in `package.json`:

  ```json
  "next": "14.2.35",
  "react": "18.3.1",
  "react-dom": "18.3.1"
  ```

  Minor tooling packages (`vitest`, `eslint`, `@types/*`) benefit less from
  exact pinning since their APIs are more stable across patches.
