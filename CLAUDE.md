# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A language learning web app (alternative to Duolingo) powered by a local LLM (Qwen2.5 7B via Ollama). Supports French, Spanish, English, Norwegian, and Galician with three exercise types: verb conjugation, grammar correction, and reading comprehension. Includes a pre-seeded `verb_conjugations` table (1.68M rows) used to validate conjugation answers independently of the LLM.

## Running the app

**Prerequisites — start these first:**
```bash
brew services start postgresql@16
ollama serve          # if not already running as a service
ollama pull qwen2.5:7b   # first time only
```

**Backend** (FastAPI, port 8000):
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

**Frontend** (React+Vite, port 5173):
```bash
cd frontend
npm run dev
```

## Database

**Migrations:**
```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "description"
alembic upgrade head
```

**Alembic gotcha:** When adding a table that references an existing PostgreSQL enum (e.g. `language`, `exercisetype`), autogenerate will emit a `CREATE TYPE` that fails because the type already exists. Fix the generated migration by replacing the `sa.Enum(...)` column with a raw-SQL `op.execute("CREATE TABLE ...")` that references the enum by name directly. See `7805ad5fd2c8` for an example.

**Seeding conjugation data** (one-time, run after migrations):
```bash
cd backend && source .venv/bin/activate
python scripts/seed_conjugations.py
```
This reads mlconjug3's bundled JSON files (`data/conjug_manager/verbs-{lang}.json` + `conjugation-{lang}.json`) directly — no ML model is loaded. Each verb entry has a `root` string and a `template` name; the conjugated form is `root + suffix` from the template.

## Architecture

```
backend/app/
├── main.py          — FastAPI app, CORS (allows localhost:5173), router registration
├── config.py        — Settings from .env: DATABASE_URL, OLLAMA_URL, OLLAMA_MODEL
├── database.py      — Async SQLAlchemy engine + AsyncSessionLocal + get_db dependency
├── models.py        — ORM models: User, Exercise, Progress, VerbConjugation (+ enums)
├── schemas.py       — Pydantic request/response schemas
├── routers/
│   ├── exercises.py            — POST /exercises/generate, POST /exercises/check
│   ├── progress.py             — GET /progress/{user_id}, POST /users, GET /users/{user_id}
│   ├── verbs.py                — GET /verbs/search|tenses|endings|random/{language}, GET /verbs/table/{language}/{infinitive} — reads verb_conjugations directly, no LLM
│   ├── chat.py                 — POST /chat, freeform passthrough to the LLM
│   └── conjugation_exercises.py — POST /conjugation-exercises/sentence/generate|check — LLM-written fill-in-the-blank sentences built around a random verb_conjugations row
└── services/
    ├── llm.py               — LLMClient singleton wrapping Ollama /api/chat
    ├── exercise_gen.py      — Prompt templates, answer checkers, GENERATORS/CHECKERS dicts
    └── conjugation_utils.py — Spanish compound-tense resolution (pairs a participle row with the matching haber row, e.g. tense "pretérito perfecto compuesto" + person "1s" → "he hablado") and FORM_ALTERNATES (interchangeable forms, e.g. "hay"/"ha")
```

`GET /health` is defined directly in `main.py`, not a router.

**Key design decisions:**

- **LLM abstraction:** `LLMClient` in `services/llm.py` is the only file that knows about Ollama. It is instantiated once at module level (`llm_client = LLMClient()`). To swap providers, change only this file.

- **Conjugation answer checking is async; grammar and reading are sync.** `check_conjugation` in `exercise_gen.py` is `async` because it does a DB fallback lookup — if the LLM's `correct_answer` doesn't match, it queries `verb_conjugations` to accept any valid form of the verb. The router special-cases this with `await check_conjugation(..., db, exercise.language)` rather than going through the `CHECKERS` dict (which only contains grammar and reading).

- **Exercises are persisted on generation** as a cache and for progress attribution. The `content` column is JSON and stores the full LLM response.

- **Frontend Vite proxy:** `fetch('/api/exercises/generate')` → Vite strips `/api` → hits `localhost:8000/exercises/generate`. All API calls go through `/api` prefix. The `api.js` module is the only place that constructs fetch calls.

- **React Router state-passing:** `Welcome` (`/`) → `Practice` (`/practice/:language`) → either `Exercise` (`/exercise`, for grammar/reading/conjugation-quiz) or `Conjugation` (`/practice/:language/conjugation`, the verb-table/sentence-completion/chat area). `Practice` calls `api.generateExercise()` then navigates to `/exercise` with the exercise object in `location.state`; `Exercise` reads it back via `useLocation().state`. **`pages/Home.jsx` is dead code** — it predates this flow and is no longer imported by `App.jsx`.

- **Two parallel conjugation-practice paths:** the original `ExerciseType.conjugation` flow (`exercises.py` + `exercise_gen.py`, single LLM-generated fill-in-the-blank, DB-validated) still exists and is reachable via the "Conjugation" card on `Practice`. Separately, `pages/Conjugation.jsx` (routed at `/practice/:language/conjugation`) is a richer practice area — verb lookup/tables (`verbs.py`, pure DB reads, no LLM), sentence completion (`conjugation_exercises.py`, LLM-generated), and freeform chat (`chat.py`) — built directly on `verb_conjugations` rather than going through `Exercise`/`ExerciseType`. The two paths don't share code beyond the DB table and `LLMClient`.

- **Spanish compound tenses need two DB rows:** `verb_conjugations` only stores the participle for compound tenses (e.g. "pretérito perfecto compuesto" stores "hablado", not "he hablado"). `conjugation_utils.COMPOUND_AUX_MAP` + `load_haber_forms`/`resolve_compound_form` look up the matching `haber` conjugation and prepend it. Used by both `verbs.py` (table display) and `conjugation_exercises.py` (marking the correct answer). Only applies to Spanish — French/English compounds aren't in the seed data.

- **Single user:** Auth is not implemented. `user_id=1` is hardcoded as default throughout. The `users` table and `POST /users` endpoint exist but are unused by the frontend.

- **Difficulty maps to tenses:** `TENSES_BY_DIFFICULTY` in `exercise_gen.py` controls which tenses the LLM is allowed to pick at each level (A1–C1). This is the only place difficulty semantics are defined. It only governs the `exercises.py` flow — the `Conjugation` practice area picks tenses via `verbs.py`'s `get_tenses`/`get_random_verbs` instead, with no difficulty concept.

## Environment

Backend `.env` (auto-loaded by `config.py`):
```
DATABASE_URL=postgresql+asyncpg://localhost/language_learning
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

## Frontend styling

No CSS framework. All components use inline CSS objects defined at the bottom of each file (e.g. `const styles = { ... }`). The established design tokens: primary color `#4f46e5` (indigo), card background `#f8f9fa`, border radius 8–12px, font `system-ui, sans-serif`. The chip/chipActive pattern (`borderColor + background: '#4f46e5', color: white`) is used throughout for toggle-style buttons.

## Docker

A full three-service stack is defined in `docker-compose.yml` (postgres:16-alpine on port 5433, backend on 8000, frontend/nginx on 5173). The backend `entrypoint.sh` runs `alembic upgrade head`, then `scripts/seed_conjugations.py` (idempotent — skips if `verb_conjugations` already has rows, so this is a fast no-op after the first run), then starts uvicorn. Ollama is expected at `host.docker.internal:11434` (i.e. still running on the host).

## Adding a new language

1. Add the value to `Language` enum in `backend/app/models.py`
2. Add its display name to `LANGUAGE_NAMES` in `backend/app/services/exercise_gen.py`
3. Add it to the `LANGUAGES` array in `frontend/src/pages/Welcome.jsx` (**not** `Home.jsx` — that file is dead code, see React Router note above)
4. Run `alembic revision --autogenerate -m "add language X"` and `alembic upgrade head`
5. If mlconjug3 supports the language (fr/es/en/it/pt/ro), add it to `LANG_CODES` in `backend/scripts/seed_conjugations.py` and re-run the seed script
6. **Before trusting the seeded data, audit it for these mlconjug3 quirks** — every one of these caused a real, silent bug for Spanish and/or French (see the git history around the conjugation-data PRs) and is worth checking for any new language before calling the seed "done":
   - **Mixed-case tense-name duplicates.** Some templates (e.g. Spanish's defective-verb templates) spell a tense name with different capitalization than the regular templates use for that same tense. `SELECT mood, tense, count(*) FROM verb_conjugations WHERE language=... GROUP BY mood, tense` and scan for near-duplicates differing only in case.
   - **Non-standard person indexing.** Don't assume every list-type tense uses the plain 6-slot index (0=1s…5=3p). The imperative mood usually has no 1st-person-singular slot, so it's indexed compactly starting at 0 instead (Spanish: 5 slots, French: 3 slots) — dump the raw template JSON for a well-known verb and cross-check every resulting person against a real conjugation table (one regular verb, one irregular) before trusting the mapping.
   - **Phantom extra list entries.** Some non-personal moods (infinitive, gerund) list a second entry that's actually just the past participle again (internal bookkeeping), not a real second form. Survey list *lengths* per (mood, tense) across ALL templates, not just one verb — a mood that's "supposed" to have 1 entry but sometimes has 2 is the tell.
   - **Non-person list entries.** Some list-type tenses encode grammatical agreement rather than person (e.g. French Participe Passé: masculine/feminine × singular/plural). If the persons don't line up with a real conjugation table, check whether they're agreement variants instead.
   - **Compound tenses need a per-language auxiliary map.** `conjugation_utils.COMPOUND_AUX_MAP`/`resolve_compound_form` are currently Spanish-only (`if language != Language.spanish: return participle`). Most Romance languages have compound tenses (Italian avere/essere, Portuguese ter/haver) — if the new language does, the seed data will store the bare participle unless this gets extended per-language.
   - **Fix at the source, then backfill.** `insert_rows` uses `on_conflict_do_nothing()`, so re-running the seed script after fixing `build_rows()` does **not** correct already-seeded bad rows — delete the affected `(language, mood)` rows and re-insert.
7. **Wire the new language into the frontend's tense organization** (`frontend/src/utils/conjugationUtils.js`) — `MOOD_ORDER`, `TENSE_ORDER_IN_MOOD`, `SECTION_MOODS`, and `TENSE_LABEL_OVERRIDES` are all keyed per language. Without an entry, tenses still work but sort into an unordered bucket and show raw/awkward DB labels instead of clean ones.

Note: the `Language` enum already has `norwegian` and `galician`, but `Welcome.jsx` currently only lists French/Spanish/English — Norwegian and Galician aren't reachable from the UI and have no seeded `verb_conjugations` data (mlconjug3 doesn't support them).
