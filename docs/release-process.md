# Release Process

## Why This Exists

Published deploys used to accept separate `BACKEND_IMAGE` and `FRONTEND_IMAGE` values, and the default compose file pointed at floating `backend-latest` and `frontend-latest` tags. That meant an operator could deploy:

- a newer frontend with an older backend
- a newer backend with an older frontend
- a backend and data-fetcher from one image tag while the frontend came from another

That mismatch was not theoretical. The current frontend company workspace calls `/api/companies/{ticker}/workspace-bootstrap`, and that route only exists from commit `0ec767b` onward. A frontend built after that change paired with an older backend would hit a real API incompatibility on the company page.

## Deployment Guarantee

Published Docker deploys are now locked by one shared image tag suffix:

- backend: `gptvibe/fundamentalterminal:backend-${APP_IMAGE_TAG}`
- data-fetcher: `gptvibe/fundamentalterminal:backend-${APP_IMAGE_TAG}`
- frontend: `gptvibe/fundamentalterminal:frontend-${APP_IMAGE_TAG}`

Use release tags such as `v1.0.3` for production deploys. Commit-pinned tags such as `sha-<gitsha>` are available for smoke verification and rollback-safe staging.

## Release Steps

1. Create and push a version tag such as `v1.0.3`.
2. Wait for `.github/workflows/publish-images.yml` to publish both images and run the compatibility smoke check.
3. Set `APP_IMAGE_TAG=v1.0.3` in the deploy environment.
4. Run `docker compose pull`.
5. Run `docker compose up -d`.
6. Run the post-deploy verification command:

```bash
python scripts/verify_deployment_compat.py --backend-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:3000 --ticker AAPL
```

## What The Verification Checks

The deployment smoke check confirms:

- backend health is green
- `/api/companies/{ticker}/overview` returns the expected top-level payload shape
- `/api/companies/{ticker}/workspace-bootstrap` returns the expected compatibility-critical payload shape
- `/api/companies/{ticker}/brief` returns the expected research-brief payload shape
- the frontend company page responds successfully when a frontend URL is provided
