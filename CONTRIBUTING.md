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
   (frontend lint/build, backend install/import check, Docker build
   validation — see `.github/workflows/ci.yml`).
5. Merge only once all checks are green. `main` is protected — direct
   pushes and merges with failing checks are blocked.
6. Delete the feature branch after merge.

## Running checks locally before pushing

```bash
# Frontend
cd frontend && npm run lint && npm run build

# Backend
cd backend && python -c "import app.main"
```

No automated test suite exists yet (backend or frontend) — CI is
lint/build/import validation only, by design, until a testing strategy is
adopted separately.