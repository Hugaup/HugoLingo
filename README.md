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

Open http://localhost:5173 and create an account (or claim the pre-login `default` user's history with `scripts/set_password.py`, see below).

## Tests

```bash
# Backend — needs Postgres running; uses a separate `language_learning_test` DB (auto-created, never your real data)
cd backend && source .venv/bin/activate
pip install -r requirements-dev.txt   # first time only
pytest

# Frontend — Vitest + React Testing Library, backend is mocked
cd frontend && npm test
```

CI runs both suites, plus `alembic upgrade head && alembic check` on a fresh database, on every PR.

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
FastAPI entry point. Registers all routers, adds CORS for `localhost:5173`, exposes `GET /health`. Every router except `auth` is registered with `dependencies=[Depends(get_current_user)]`, so the whole API requires login except `/auth/*` and `/health`.

### `app/dependencies.py`
`get_current_user` — resolves the `hugolingo_session` cookie to a `User` via the `user_sessions` table, or raises 401.

### `app/config.py`
Reads `DATABASE_URL`, `OLLAMA_URL`, `OLLAMA_MODEL` from `.env` via Pydantic Settings.

### `app/database.py`
Async SQLAlchemy engine + `AsyncSessionLocal`. Exports `get_db` FastAPI dependency (yields a session per request).

### `app/models.py`
ORM models and enums:
- `Language` enum — `french | spanish | english | norwegian | galician`
- `ExerciseType` enum — `verb_conjugation | grammar_correction | reading_comprehension`
- `User` — id, username, password_hash (nullable for pre-auth accounts), native_language, target_language, level (1–5, same scale as difficulty), daily_goal, created_at
- `UserSession` — user_id, token_hash (SHA-256 of the cookie token), created_at, expires_at (30 days)
- `Exercise` — id, type, language, difficulty, content (JSON), created_at
- `Progress` — user_id, exercise_id, user_answer, is_correct, created_at
- `Attempt` — one row per conjugation answer from any practice area: user, language, source (`sentence`/`verb_table`/`drill`/`exercise`), verb, mood, tense, person, answer, expected, is_correct
- `ReviewItem` — spaced-repetition (Leitner) box per user × verb × tense: box 0–5, due_at, right/wrong counts
- `VerbConjugation` — 1.68M-row lookup table: language, verb_infinitive, mood, tense, person, form

### `app/schemas.py`
Pydantic request/response schemas for all endpoints, plus `SentenceExerciseItem`, `SentenceCheckRequest/Response`, `ChatRequest/Response`.

### Routers

#### `app/routers/exercises.py`
- `POST /exercises/generate` — calls `exercise_gen.py` to build a prompt, sends it to the LLM, persists the Exercise row, returns the exercise.
- `POST /exercises/check` — grammar/reading answers are checked synchronously via `CHECKERS` dict; conjugation answers go through `check_conjugation` (async DB fallback). The `Progress` row is attributed to the logged-in user.

#### `app/routers/auth.py`
Cookie-session auth (httpOnly, SameSite=Lax; set `COOKIE_SECURE=true` when serving over HTTPS):
- `POST /auth/signup` — create an account (username 3–32 chars of `A-Za-z0-9_.-`, password ≥ 4 chars, no other rules) and log in.
- `POST /auth/login` / `POST /auth/logout` — logout deletes the session row, so the cookie is dead server-side.
- `GET /auth/me` / `PATCH /auth/me` — profile + settings (`target_language`, `level`, `daily_goal`).
- `POST /auth/password` — change password; logs out every other session.

Usernames keep their casing but are unique and matched case-insensitively.

#### `app/routers/progress.py`
- `GET /progress` — the logged-in user's exercise history with correctness stats.

#### `app/routers/verbs.py`
Verb dictionary endpoints backed by the `verb_conjugations` table:
- `GET /verbs/search/{language}?q=` — autocomplete (prefix match on infinitives).
- `GET /verbs/tenses/{language}` — all (mood, tense) pairs for a language.
- `GET /verbs/endings/{language}` — `-er/-ir/-re` etc. for filtering.
- `GET /verbs/random/{language}?mode=random|irregular|endings` — random verbs for exercise seeding.
- `GET /verbs/table/{language}/{infinitive}?moods=` — full conjugation table. For Spanish, resolves compound tenses (e.g. `hablado → he hablado`) using `conjugation_utils.py`.

Also contains `IRREGULAR_VERBS` sets per language used for "irregular" mode.

#### `app/routers/history.py`
Answer history, weak spots and review (logic in `app/services/history.py`):
- `POST /history/attempts` — record answers graded in the browser (verb table only).
- `GET /history/weak-spots/{language}` — weakest verbs, tenses and verb+tense pairs (recency-weighted error rate, mistakes fade with a 14-day half-life) plus how many review items are due.
- `GET /history/drill/{language}?count=` — prompts for the review drill: due items first, then weak spots; persons you got wrong come first.
- `POST /history/drill/check` — grades a drill answer against `verb_conjugations` (compound tenses, both subjunctive spellings) as `correct`/`almost`/`wrong`, records it, and returns a one-line explanation plus the whole tense for mistakes.
- `GET /history/stats?language=&tz=&days=` — totals, accuracy, per-day activity, today's count and streak, in the user's timezone.
- `GET /history/grid/{language}` — accuracy per verb × tense for the most-practised verbs.

The sentence-completion check and the old conjugation exercise check record their answers server-side.

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

#### `app/services/grading.py`
`grade(answer, accepted)` → `correct`, `almost` (only accents differ — still logged as a mistake, with `attempts.is_almost`), or `wrong`. Used by the drill, sentence completion and the classic exercise check; `frontend/src/utils/grading.js` mirrors it for the verb table.

#### `app/services/explain.py`
Rule-based (no LLM) one-line explanations: accent slip, another person's form, a form from another tense, irregular vs a model regular verb (hablar/comer/vivir, parler/finir/vendre) with the new stem, or the regular pattern itself.

#### `app/services/auth.py`
Pure helpers, no DB: `hash_password`/`verify_password` (stdlib scrypt, self-describing `scrypt$n$r$p$salt$hash` format), `new_session_token`, `hash_token`.

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

#### `alembic/versions/a1c3e5f7b9d2_add_auth.py`
Adds password/settings columns to `users` and creates `user_sessions` (raw SQL, reuses the `language` enum).

#### `alembic/versions/b2d4f6a8c0e1_add_history.py`
Creates `attempts` and `review_items` (raw SQL, reuses the `language` enum).

#### `alembic/versions/c3e5a7b9d1f2_add_attempts_is_almost.py`
Adds `attempts.is_almost` (accent-only slips, default false).

#### `scripts/set_password.py`
Set or reset a user's password, optionally renaming them. Use it to claim the pre-auth `default` user (id 1) so its history is kept:
```bash
python scripts/set_password.py default mypassword --rename hugo
```

#### `scripts/seed_conjugations.py`
One-time seeding from mlconjug3's bundled JSON files (no ML model loaded). Reads `verbs-{lang}.json` + `conjugation-{lang}.json`, computes `root + suffix` for each form, bulk-inserts into `verb_conjugations`. Run once after migrations.

---

## Frontend

### Routing (`src/App.jsx`)
```
/login, /signup            → Auth  (public)
── behind <RequireAuth> (redirects to /login, then back) ──
/                          → Welcome
/practice/:language        → Practice  (exercise type picker)
/practice/:language/conjugation → Conjugation  (verb drill hub)
/exercise                  → Exercise  (grammar/reading answer screen)
/settings                  → Settings  (learning prefs, change password)
```

### Auth (`src/auth/`)
`AuthProvider` loads `/auth/me` on startup and exposes `{ user, loading, login, signup, logout, setUser }` via `useAuth()`. Any 401 from the API (expired session) clears the user, which sends them to `/login`.

### `src/api.js`
Single module for all backend calls. All paths prefixed with `/api`; the session cookie rides along automatically. Methods: `signup`, `login`, `logout`, `me`, `updateSettings`, `changePassword`, `generateExercise`, `checkAnswer`, `getProgress`, `searchVerbs`, `getVerbTenses`, `getVerbEndings`, `getRandomVerbs`, `getVerbTable`, `recordAttempts`, `getWeakSpots`, `getDrill`, `checkDrill`, `getStats`, `getGrid`, `chat`, `generateSentences`, `checkSentence`. Errors are thrown as `ApiError` (with `.status`).

### Pages

#### `src/pages/Review.jsx` (`/practice/:language/review`)
Weak-spot drill: one verb + tense + person at a time, graded by the server, keyboard-only flow (Enter to check, Enter for next), summary of mistakes at the end.

#### `src/pages/Progress.jsx` (`/progress`)
Per-language stats: answer/accuracy/streak/daily-goal tiles, 30-day activity chart, "Work on this", and a verbs × tenses accuracy heatmap (`components/charts/`).

#### `src/components/MistakeExplanation.jsx` / `SessionSummary.jsx`
Compact feedback after a mistake (one line, all forms behind a toggle) and the end-of-session recap (score, mistakes with accent slips marked, "Review these now") shared by the drill, sentence completion and the classic exercise flow.

#### `src/components/WorkOnThis.jsx`
Compact panel (on `Practice` and `Progress`) listing the user's weakest verb + tenses with a "Practise these" button into the drill.

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
3. Add to `LANGUAGES` array in `frontend/src/constants.js` (used by `Welcome` and `Settings`) — **not** `pages/Home.jsx`, which is dead code no longer imported by `App.jsx`
4. Run migration: `alembic revision --autogenerate -m "add language X" && alembic upgrade head`
5. If mlconjug3 supports it, add to `LANG_CODES` in `scripts/seed_conjugations.py` and re-seed

See [CLAUDE.md](CLAUDE.md#adding-a-new-language) for the full mlconjug3 data-quality checklist (person-index quirks, phantom list entries, etc.) — every item on it caused a real, silent bug for Spanish or French and is worth checking before trusting a new language's seeded data.
