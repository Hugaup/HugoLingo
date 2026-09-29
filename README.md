# HugoLingo

A Duolingo-alternative powered by a local LLM (Qwen2.5 7B via Ollama). Supports **French, Spanish, English, Norwegian, and Galician** with verb conjugation practice, grammar correction, and reading comprehension exercises.

## Quick Start

```bash
# Prerequisites
brew services start postgresql@16
ollama serve
ollama pull qwen2.5:7b   # first time only

# Backend (port 8000)
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload

# Frontend (port 5173)
cd frontend && npm run dev
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching workflow and CI checks.

## Architecture Overview

```
browser → Vite (:5173) → /api proxy → FastAPI (:8000) → PostgreSQL
                                              ↓
                                        Ollama (:11434)
                                        Qwen2.5 7B
```

All API calls go through `/api` prefix (Vite strips it before forwarding). Ollama is used both to generate exercises and to give feedback on answers.

---

## Backend

### `app/main.py`
FastAPI entry point. Registers all routers, adds CORS for `localhost:5173`, exposes `GET /health`.

### `app/config.py`
Reads `DATABASE_URL`, `OLLAMA_URL`, `OLLAMA_MODEL` from `.env` via Pydantic Settings.

### `app/database.py`
Async SQLAlchemy engine + `AsyncSessionLocal`. Exports `get_db` FastAPI dependency (yields a session per request).

### `app/models.py`
ORM models and enums:
- `Language` enum — `french | spanish | english | norwegian | galician`
- `ExerciseType` enum — `verb_conjugation | grammar_correction | reading_comprehension`
- `User` — id, username, native_language, created_at
- `Exercise` — id, type, language, difficulty, content (JSON), created_at
- `Progress` — user_id, exercise_id, user_answer, is_correct, created_at
- `VerbConjugation` — 1.68M-row lookup table: language, verb_infinitive, mood, tense, person, form

### `app/schemas.py`
Pydantic request/response schemas for all endpoints, plus `SentenceExerciseItem`, `SentenceCheckRequest/Response`, `ChatRequest/Response`.

### Routers

#### `app/routers/exercises.py`
- `POST /exercises/generate` — calls `exercise_gen.py` to build a prompt, sends it to the LLM, persists the Exercise row, returns the exercise.
- `POST /exercises/check` — grammar/reading answers are checked synchronously via `CHECKERS` dict; conjugation answers go through `check_conjugation` (async DB fallback).

#### `app/routers/progress.py`
- `GET /progress/{user_id}` — returns exercise history with correctness stats.
- `POST /users` — create a user.
- `GET /users/{user_id}` — fetch user (unused by frontend; `user_id=1` is hardcoded everywhere).

#### `app/routers/verbs.py`
Verb dictionary endpoints backed by the `verb_conjugations` table:
- `GET /verbs/search/{language}?q=` — autocomplete (prefix match on infinitives).
- `GET /verbs/tenses/{language}` — all (mood, tense) pairs for a language.
- `GET /verbs/endings/{language}` — `-er/-ir/-re` etc. for filtering.
- `GET /verbs/random/{language}?mode=random|irregular|endings` — random verbs for exercise seeding.
- `GET /verbs/table/{language}/{infinitive}?moods=` — full conjugation table. For Spanish, resolves compound tenses (e.g. `hablado → he hablado`) using `conjugation_utils.py`.

Also contains `IRREGULAR_VERBS` sets per language used for "irregular" mode.

#### `app/routers/chat.py`
- `POST /chat` — raw LLM chat relay; forwards a `messages` array directly to Ollama. Used by the in-app grammar tutor chat.

#### `app/routers/conjugation_exercises.py`
Sentence-fill-in-the-blank conjugation exercises:
- `POST /conjugation-exercises/sentence/generate` — picks a random DB conjugation row matching requested tenses, asks the LLM to write a sentence using that exact form with `___` as the blank.
- `POST /conjugation-exercises/sentence/check` — compares user's form + tense identification against the DB answer, then asks the LLM for a 2–3 sentence explanation.

### Services

#### `app/services/llm.py`
`LLMClient` singleton wrapping `POST /api/chat` on Ollama. Two methods: `chat(messages)` → string, `chat_json(messages)` → parsed dict. The only file that knows about Ollama — swap provider here only.

#### `app/services/exercise_gen.py`
- `LANGUAGE_NAMES` — display names map.
- `TENSES_BY_DIFFICULTY` — maps A1–C1 difficulty to allowed tenses (only place difficulty semantics live).
- `GENERATORS` dict — prompt-builder functions per exercise type.
- `CHECKERS` dict — answer-check functions for grammar and reading (sync).
- `check_conjugation` — async checker: if LLM's `correct_answer` doesn't match, falls back to querying `verb_conjugations` to accept any valid form.

#### `app/services/conjugation_utils.py`
Spanish compound tense resolution, plus tense-name canonicalization used across all languages:
- `COMPOUND_AUX_MAP` — maps compound tense names to their `haber` auxiliary tense.
- `FORM_ALTERNATES` — interchangeable forms (e.g. `hay ↔ ha`).
- `load_haber_forms(db, language, needed)` — batch-loads `haber` conjugations.
- `resolve_compound_form(db, language, tense, person, participle)` — returns `"he hablado"` from `"hablado"` for compound tenses.
- `canonical_tense(tense)` / `variant_tense_names(canonical)` — collapse Spanish subjunctive imperfecto/pluscuamperfecto "(1)"/"(2)" spelling variants (hablara/hablase) into one selectable tense everywhere except the raw DB rows.

### Database / Migrations

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

**Gotcha:** When adding a table referencing an existing PG enum (`language`, `exercisetype`), autogenerate emits a `CREATE TYPE` that fails. Fix by replacing `sa.Enum(...)` with a raw `op.execute("CREATE TABLE ...")`. See migration `7805ad5fd2c8` for the pattern.

#### `alembic/versions/1754923d9766_initial_tables.py`
Creates `users`, `exercises`, `progress` tables plus the `language` and `exercisetype` enums.

#### `alembic/versions/7805ad5fd2c8_add_verb_conjugations_table.py`
Creates `verb_conjugations` table using raw SQL to avoid enum re-creation conflict.

#### `scripts/seed_conjugations.py`
One-time seeding from mlconjug3's bundled JSON files (no ML model loaded). Reads `verbs-{lang}.json` + `conjugation-{lang}.json`, computes `root + suffix` for each form, bulk-inserts into `verb_conjugations`. Run once after migrations.

---

## Frontend

### Routing (`src/App.jsx`)
```
/                          → Welcome
/practice/:language        → Practice  (exercise type picker)
/practice/:language/conjugation → Conjugation  (verb drill hub)
/exercise                  → Exercise  (grammar/reading answer screen)
```

### `src/api.js`
Single module for all backend calls. All paths prefixed with `/api`. Methods: `generateExercise`, `checkAnswer`, `getProgress`, `searchVerbs`, `getVerbTenses`, `getVerbEndings`, `getRandomVerbs`, `getVerbTable`, `chat`, `generateSentences`, `checkSentence`.

### Pages

#### `src/pages/Welcome.jsx`
Landing page with language selector chips. Navigates to `/practice/:language`.

#### `src/pages/Practice.jsx`
Exercise-type picker for a given language (verb conjugation, grammar correction, reading comprehension). Calls `api.generateExercise()` then navigates to `/exercise` with the exercise in `location.state`.

#### `src/pages/Exercise.jsx`
Answer screen for grammar/reading exercises. Reads exercise from `useLocation().state`, submits via `api.checkAnswer()`, shows `FeedbackPanel`.

#### `src/pages/Conjugation.jsx`
Verb drill hub. Contains tabs/modes for: verb table lookup, sentence-completion exercises, tense guide, and chat panel.

### Components

#### `src/components/FeedbackPanel.jsx`
Shared feedback display (correct/incorrect + LLM explanation) used by Exercise and Conjugation pages.

#### `src/components/conjugation/VerbTableExercise.jsx`
Fill-in-the-blank table: shows a verb's full conjugation grid with some cells blanked out for the user to complete.

#### `src/components/conjugation/SentenceCompletion.jsx`
Renders sentence-fill exercises from `conjugation_exercises` router. User types the conjugated form and identifies the tense; submits to `/conjugation-exercises/sentence/check`.

#### `src/components/conjugation/VerbLookup.jsx`
Autocomplete search + full conjugation table display. Calls `api.searchVerbs` and `api.getVerbTable`.

#### `src/components/conjugation/TenseChipSelector.jsx`
Tense picker used by `VerbTableExercise` and `SentenceCompletion` — renders a mood-grouped table (one section header row per mood, tenses as checkboxes) instead of a flat chip list. Non-personal forms (gerundio/infinitivo/participio, etc.) get their own trailing "Other" section.

#### `src/components/conjugation/TenseGuide.jsx`
Reference panel listing tenses with usage descriptions, filtered by language. For Spanish, also includes a "moods at a glance" overview (when to use indicativo vs subjuntivo vs imperativo) and "vs" comparison call-outs for commonly confused tense pairs (imperfecto vs indefinido, etc.).

#### `src/components/conjugation/ChatPanel.jsx`
Free-form chat with the LLM tutor. Calls `api.chat()` directly.

#### `src/components/conjugation/CharPicker.jsx`
Accent character insertion helper (é, ñ, ø, etc.) for input fields.

### Styling
No CSS framework. Each component has a `const styles = { ... }` object at the bottom. Design tokens: primary `#4f46e5`, card background `#f8f9fa`, border-radius 8–12px, font `system-ui`. Toggle buttons use a `chip/chipActive` pattern.

### `vite.config.js`
Proxies `/api/*` → `http://localhost:8000/*` (strips `/api` prefix).

---

## Docker

`docker-compose.yml` runs three services: `postgres:16-alpine` (port 5433), FastAPI backend (port 8000), and React/nginx frontend (port 5173). `backend/entrypoint.sh` runs `alembic upgrade head`, then `scripts/seed_conjugations.py` (idempotent — a fast no-op once already seeded), then starts uvicorn. Ollama stays on the host at `host.docker.internal:11434`.

`frontend/nginx.conf` — nginx config for the production frontend container; proxies `/api/` to the backend service.

---

## Adding a New Language

1. Add to `Language` enum in `backend/app/models.py`
2. Add display name to `LANGUAGE_NAMES` in `backend/app/services/exercise_gen.py`
3. Add to `LANGUAGES` array in `frontend/src/pages/Welcome.jsx` — **not** `pages/Home.jsx`, which is dead code no longer imported by `App.jsx`
4. Run migration: `alembic revision --autogenerate -m "add language X" && alembic upgrade head`
5. If mlconjug3 supports it, add to `LANG_CODES` in `scripts/seed_conjugations.py` and re-seed

See [CLAUDE.md](CLAUDE.md#adding-a-new-language) for the full mlconjug3 data-quality checklist (person-index quirks, phantom list entries, etc.) — every item on it caused a real, silent bug for Spanish or French and is worth checking before trusting a new language's seeded data.
