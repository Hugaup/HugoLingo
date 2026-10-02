# Contributing

This project follows **GitHub Flow**: a single long-lived `main` branch that
is always deployable/stable, with short-lived feature branches merged via
pull request.

## Branch naming

- `feature/<short-description>` — new functionality (e.g. `feature/reading-comprehension-hints`)
- `fix/<short-description>` — bug fixes (e.g. `fix/conjugation-lookup-crash`)
- `chore/<short-description>` — tooling, deps, docs, CI (e.g. `chore/add-ci-workflow`)

## Workflow

1. Branch off `main`.
2. Commit as you go; push early and often.
3. Open a PR targeting `main` once ready for review (or ready to merge, solo).
4. CI runs automatically on every push to the PR and on `main` itself
   (frontend lint/test/build, backend pytest + migration check against a
   Postgres service, Docker build validation — see `.github/workflows/ci.yml`).
5. Merge only once all checks are green. `main` is protected — direct
   pushes and merges with failing checks are blocked.
6. Delete the feature branch after merge.

## Running checks locally before pushing

```bash
# Frontend
cd frontend && npm run lint && npm test && npm run build

# Backend (Postgres must be running; tests use a separate *_test database)
cd backend && pytest
```

Every feature branch should add tests for what it changes:

- **Backend** — `backend/tests/`, pytest + httpx against the real FastAPI app
  and a throwaway Postgres DB. Fixtures in `conftest.py`: `client`,
  `new_client` (independent cookie jars), `logged_in(username, password)`, `db`.
- **Frontend** — `frontend/src/test/`, Vitest + React Testing Library.
  `mockBackend({...})` fakes `fetch`; `renderAppAt(path)` renders the full app
  with routing and auth.