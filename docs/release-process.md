# Release Process

## Why This Exists

Published deploys need the frontend and backend to stay compatible. The frontend company workspace calls `/api/companies/{ticker}/workspace-bootstrap`, and that route only exists from commit `0ec767b` onward. A newer frontend paired with an older backend would hit a real API incompatibility on the company page.

The default compose file now uses the latest published pair from Docker Hub:

- backend and worker services: `gptvibe/fundamentalterminal:backend-latest`
- frontend: `gptvibe/fundamentalterminal:frontend-latest`

If you want a pinned deploy instead of the moving latest tags, set both `BACKEND_IMAGE` and `FRONTEND_IMAGE` to matching release tags in `.env`.

## Deployment Pattern

Published Docker deploys use:

- backend: `${BACKEND_IMAGE:-gptvibe/fundamentalterminal:backend-latest}`
- data-fetcher: `${BACKEND_IMAGE:-gptvibe/fundamentalterminal:backend-latest}`
- frontend: `${FRONTEND_IMAGE:-gptvibe/fundamentalterminal:frontend-latest}`

To pin a production release, use matching tags such as:

- `BACKEND_IMAGE=gptvibe/fundamentalterminal:backend-v1.0.3`
- `FRONTEND_IMAGE=gptvibe/fundamentalterminal:frontend-v1.0.3`

## Release Steps

1. Create and push a version tag such as `v1.0.3`.
2. Wait for `.github/workflows/publish-images.yml` to publish both images and run the compatibility smoke check.
3. Optional: set matching `BACKEND_IMAGE` and `FRONTEND_IMAGE` values in the deploy environment if you want to pin that release instead of using `latest`.
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
