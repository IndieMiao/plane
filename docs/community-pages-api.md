# Community Edition project Pages API

This branch adds API-key access to project Pages on Plane Community Edition.
It is based on Plane `v1.3.1`.

## Endpoints

```text
GET  /api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/
POST /api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/
GET  /api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/{page_id}/
```

Page creation uses the existing `Page` and `ProjectPage` models, project-member
permissions, HTML sanitization, and the existing page transaction task. No
database migration is required.

The branch also registers Plane's external API logging task with Celery and
excludes Celery task arguments from JSON logs so page bodies and API credentials
are not emitted by the worker.

## Build

Build the full backend image:

```bash
docker build \
  --file apps/api/Dockerfile.api \
  --tag plane-backend:community-pages \
  apps/api
```

When the official `makeplane/plane-backend:v1.3.1` image is already available,
the smaller overlay image can be used instead:

```bash
docker build \
  --file apps/api/Dockerfile.pages-overlay \
  --tag plane-backend:v1.3.1-community-pages \
  apps/api
```

## Test

Run the contract tests with Plane's PostgreSQL-backed test environment:

```bash
pytest plane/tests/contract/api/test_pages.py -q
```

## Updating from upstream

Keep `upstream` pointed at `https://github.com/makeplane/plane.git`, fetch the
new official release, and rebase the `community-pages` branch. Review the API
URL registrations first because an official Community Pages API may eventually
replace this patch.
