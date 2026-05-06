# Release Checklist

This checklist is the source of truth for cutting a release. Follow it in order.

## Scope

- Repository: Fundamental-Terminal
- Current baseline release: `v0.1.0`
- Tag policy: increment patch (`+0.0.1`) from latest `vX.Y.Z` unless explicitly choosing a different version.
- Image tags must stay aligned with Git tag, for example: `v1.0.3`, `backend-v1.0.3`, `frontend-v1.0.3`.

## Preflight

1. Sync local branch and ensure `main` is green.
2. Verify required tooling is installed: Python, Node.js, Docker, Git, curl, bash.
3. Start local stack (or ensure staging stack is already running):

```bash
docker compose up -d
```

## Quality Gates (CI Or Manual)

Run these locally before tagging, even if CI already runs them.

1. Backend tests:

```bash
python -m pytest
```

2. Frontend tests:

```bash
cd frontend
npm test
cd ..
```

3. Lint and typecheck:

```bash
cd frontend
npm run lint
npm run build
cd ..
```

4. Smoke test (fails non-zero on any route failure):

```bash
bash scripts/smoke_release.sh --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

5. Performance regression gate:

```bash
python scripts/run_performance_regression_gate.py \
  --baseline-file scripts/performance_regression_baseline.json \
  --fail-on-regression \
  --json-out artifacts/performance/backend-performance-summary.json \
  --markdown-out artifacts/performance/backend-performance-summary.md
```

## Release Preparation

1. Update `CHANGELOG.md` with release notes.
2. Review `KNOWN_LIMITATIONS.md` and ensure it reflects current behavior.
3. Confirm Docker publish workflow secrets exist:
   - `DOCKERHUB_USERNAME`
   - `DOCKERHUB_TOKEN`

## Tag And Publish

1. Choose next version by patch increment from latest tag.
2. Compute and create annotated tag:

```bash
LATEST_TAG="$(git tag --list 'v*' --sort=version:refname | tail -n 1)"
LATEST_TAG="${LATEST_TAG:-v0.0.0}"
IFS='.' read -r MAJOR MINOR PATCH <<< "${LATEST_TAG#v}"
NEXT_VERSION="v${MAJOR}.${MINOR}.$((PATCH + 1))"
echo "Releasing ${NEXT_VERSION}"
git tag -a "${NEXT_VERSION}" -m "Release ${NEXT_VERSION}"
git push origin "${NEXT_VERSION}"
```

3. Wait for image publish workflow to complete:
   - backend image `backend-${NEXT_VERSION}`
   - frontend image `frontend-${NEXT_VERSION}`

## Post-Release Verification

1. Pull and run published images (or deploy environment).
2. Run compatibility verification:

```bash
python scripts/verify_deployment_compat.py \
  --backend-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1:3000 \
  --ticker AAPL
```

3. Confirm key routes load from the deployed release:
   - `/`
   - `/watchlist`
   - `/data-sources`
   - `/company/AAPL`

## Rollback Reference

If a release must be rolled back, pin both image variables to the previous known-good matching pair:

```bash
BACKEND_IMAGE=gptvibe/fundamentalterminal:backend-vX.Y.Z
FRONTEND_IMAGE=gptvibe/fundamentalterminal:frontend-vX.Y.Z
```

Then:

```bash
docker compose pull
docker compose up -d
```
