# HugoLingo

A free, self-hosted app for learning **Spanish**, an alternative to Duolingo. The practice material is curated data (1.68M verb forms, a frequency-ranked word list, hand-written exercises); a local LLM (Qwen2.5 7B via Ollama) plays the conversation partner and writes extra practice sentences and reading passages.

What you can practise:
- **Conjugation** — look up any verb's full table, fill in tables, complete sentences, and a tense guide (indicativo / subjuntivo / imperativo, with the commonly confused pairs explained).
- **Vocabulary** — ~250 common words in 11 topics and ~40 everyday phrases, with flashcards, multiple choice, typing, fill-the-gap and dictation, on a spaced-review schedule.
- **Conversation** — role-play everyday situations (café, hotel, asking the way…) with the AI; each of your messages is checked and corrected.
- **Grammar** — organised like lingua.com: 50 topics by level (A1–B2) and category (articles, pronouns, *ser y estar*, *por o para*, the subjunctive…), each with the rule in a few lines and sheets of gap sentences with four options, marked as you click. ~860 hand-written questions, plus a "find the mistake" topic where you retype a sentence corrected. No AI involved.
- **Reading** — short passages where every word can be clicked for its meaning.
- **Review** — every mistake is kept. "Work on this" shows what needs work, it turns to "getting there" once you get it right, and to "fixed" after you pass the 1-day and 3-day check-ups; Progress → "My mistakes" has the whole history.

Spanish is the only language offered for now. The code and data for French and English are still there (verb tables for both, French vocabulary), just hidden — see [Languages](#languages).

## Quick Start

```bash
ollama pull qwen2.5:7b   # first time only
./dev.sh                 # starts Postgres, Ollama, backend and frontend, opens the browser
```

Ctrl+C stops all of it (backend, frontend, Ollama and Postgres). `./dev.sh stop` does the same if the terminal was closed; `./dev.sh --no-open` skips opening the browser. The script runs pending migrations and reloads the vocabulary from `backend/data/vocabulary/*.json` on start, and refuses to launch if port 8000 or 5173 is already taken.

To start the pieces by hand instead:

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

### Running with Docker

Docker runs the database, backend and frontend, but **not Ollama**. For the AI features, install Ollama and have it running on your machine:

```bash
ollama serve             # in its own terminal (or open the Ollama app)
ollama pull qwen2.5:7b   # first time only
docker compose up --build
```

Then open http://localhost:5173. The first start takes a minute or two while the verb tables are loaded into the database; later starts skip that step.

**The app also runs without Ollama**, just without the AI. Still available: accounts, verb tables and verb practice, all of grammar, vocabulary (flashcards, quizzes, typing, fill-the-gap, dictation), looking up words that are in the word list, the review drill, "Work on this", "My mistakes" and Progress. Sentence completion keeps working while its stock of ready-made sentences lasts (the stock only refills when Ollama is running). Unavailable: conversation, reading, the AI chat and explanations, translating a line, and looking up words outside the word list. These show a short "is Ollama running?" message instead of hanging. You can start Ollama later; the app picks it up without a restart.

The Docker version has its own database, separate from the one `./dev.sh` uses, so accounts and progress aren't shared between the two. It uses the same ports (8000, 5173), so stop one before starting the other. See [Docker](#docker) for how it's put together.

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
- `SentencePoolItem` — a validated, ready-to-serve practice sentence (deleted when served)
- `VerbConjugation` — 1.68M-row lookup table: language, verb_infinitive, mood, tense, person, form

### `app/schemas.py`
Pydantic request/response schemas for all endpoints, plus `SentenceExerciseItem`, `SentenceCheckRequest/Response`, `ChatRequest/Response`.

### Routers

#### `app/routers/exercises.py`
- `POST /exercises/generate` — calls `exercise_gen.py` to build a prompt, sends it to the LLM, persists the Exercise row, returns the exercise.
- `POST /exercises/check` — reading answers (and grammar exercises made before the grammar section) are checked synchronously via `CHECKERS` dict; conjugation answers go through `check_conjugation` (async DB fallback). The `Progress` row is attributed to the logged-in user.

#### `app/routers/auth.py`
Cookie-session auth (httpOnly, SameSite=Lax; set `COOKIE_SECURE=true` when serving over HTTPS):
- `POST /auth/signup` — create an account (username 3–32 chars of `A-Za-z0-9_.-`, password ≥ 4 chars, no other rules) and log in.
- `POST /auth/login` / `POST /auth/logout` — logout deletes the session row, so the cookie is dead server-side.
- `GET /auth/me` / `PATCH /auth/me` — profile + settings (`target_language`, `level`, `daily_goal`).
- `POST /auth/password` — change password; logs out every other session.

Usernames keep their casing but are unique and matched case-insensitively.

#### `app/routers/grammar.py`
The grammar section (logic in `app/services/grammar_topics.py`, data in `backend/data/grammar/spanish/`):
- `GET /grammar/{language}` — categories, every topic with its sheets' progress (answered / right, from the latest answer to each question), its review status, and the overall score.
- `GET /grammar/{language}/topics/{topic}` — one topic, with its rule.
- `GET /grammar/{language}/topics/{topic}/sheets/{n}` / `…/review` — a sheet's questions (never the answers); a review sheet puts the questions you last got wrong first.
- `POST /grammar/answer` — grades one answer (an option, or a typed correction for "find the mistake"), records it, and returns the right answer, the rule behind it and where the topic now stands. A mistake puts the topic in "Work on this" with the same check-ups as verbs.

New questions: add `[text, answer, [3 wrong options], why]` to a topic file and run `python scripts/format_grammar_topics.py spanish` to give them ids.

#### `app/routers/progress.py`
- `GET /progress` — the logged-in user's exercise history with correctness stats.

#### `app/routers/verbs.py`
Verb dictionary endpoints backed by the `verb_conjugations` table:
- `GET /verbs/search/{language}?q=` — autocomplete (prefix match on infinitives).
- `GET /verbs/tenses/{language}` — all (mood, tense) pairs for a language.
- `GET /verbs/endings/{language}` — `-er/-ir/-re` etc. for filtering.
- `GET /verbs/random/{language}?mode=random|irregular|endings` — random verbs for exercise seeding (random/endings prefer the curated `COMMON_VERBS` list over the ~9,700 seeded verbs).
- `GET /verbs/table/{language}/{infinitive}?moods=` — full conjugation table. For Spanish, resolves compound tenses (e.g. `hablado → he hablado`) using `conjugation_utils.py`.

Also contains `IRREGULAR_VERBS` sets per language used for "irregular" mode.

#### `app/routers/history.py`
Answer history, weak spots and review (logic in `app/services/history.py`):
- `POST /history/attempts` — record answers graded in the browser (verb table only).
- `GET /history/weak-spots/{language}?limit=` — "Work on this": verb+tenses you got wrong that *need work* (worst first) or are *getting there* (right since, waiting for the 1-day and 3-day check-ups), counts per status (incl. *fixed*), how many review items are due and when the next check-up is.
- `GET /history/mistakes/{language}` — every verb+tense and word ever got wrong, with its status and latest wrong answers.
- `GET /history/drill/{language}?count=[&verb=&mood=&tense=]` — prompts for the review drill: what's due (needs work, then check-ups), or every person of one verb+tense; persons you got wrong come first.
- `POST /history/drill/check` — grades a drill answer against `verb_conjugations` (compound tenses, both subjunctive spellings) as `correct`/`almost`/`wrong`, records it, and returns a one-line explanation plus the whole tense for mistakes.
- `GET /history/stats?language=&tz=&days=` — totals, accuracy, per-day activity, today's count and streak, in the user's timezone.
- `GET /history/grid/{language}` — accuracy per verb × tense for the most-practised verbs.

The sentence-completion check and the old conjugation exercise check record their answers server-side.

#### `app/routers/vocabulary.py`
Words and everyday phrases (logic in `app/services/vocabulary.py`, data in `backend/data/vocabulary/`):
- `GET /vocab/{language}/overview` — per topic: items, seen, learned (review box ≥ 3), due.
- `GET /vocab/{language}/session?kind=word|phrase&topic=&count=` — due items first, then new ones (most common first), then the weakest; each with three wrong options and a fill-the-gap sentence.
- `GET /vocab/{language}/items` — browse a topic or all phrases, with the user's review box.
- `POST /vocab/check` — grades flashcard / multiple-choice / typing / fill-the-gap / dictation answers (article optional, punctuation ignored, accent slips = "almost"), records it and moves the review box.
- `POST /vocab/lookup` — meaning of a word clicked in a reading passage: curated vocabulary first (also verb forms like *tengo* → *tener*, plurals, *l'eau* → *eau*), then a cache of earlier AI lookups, then the LLM (cached after).
- `POST /vocab/my-words` / `DELETE /vocab/my-words/{id}` — save a word to review (curated words get a review; others become personal "My words" items) / remove a personal word.

#### `app/routers/conversation.py`
AI role-play practice (logic in `app/services/conversation.py`):
- `GET /conversation/scenarios` — café, asking the way, hotel, clothes shop, meeting someone, pharmacy, free chat; each with a goal for the learner.
- `POST /conversation/reply` — the AI's next in-character line (its opener when there are no messages yet), streamed as plain text, pitched at the user's level.
- `POST /conversation/check` — checks one learner message (only real mistakes; accent-only = "almost"), stores it in `conversation_turns`, and records verb mistakes in the shared history so they show up in weak spots and review.

#### `app/routers/chat.py`
- `POST /chat` — raw LLM chat relay; forwards a `messages` array directly to Ollama.
- `POST /chat/stream` — same, but streams the reply as plain text while it's written. Used by every chat panel (text appears within ~0.1–0.4 s instead of after the full reply).

#### `app/routers/conjugation_exercises.py`
Sentence-fill-in-the-blank conjugation exercises:
- `POST /conjugation-exercises/sentence/generate` — serves ready-made sentences from the background stock (`sentence_pool`) first, then generates the rest live (`services/sentences.py`: random DB conjugation row → LLM sentence with `___` as the blank → validity checks).
- `POST /conjugation-exercises/sentence/check` — grades form + tense identification against the DB answer, records the attempt and returns a rule-based hint. It does **not** call the LLM (that took ~10 s); the frontend streams the AI's longer explanation from `/chat/stream` only when the user opens it.

### Services

#### `app/services/llm.py`
`LLMClient` singleton wrapping `POST /api/chat` on Ollama: `chat()`, `chat_json()`, `chat_stream()` (async generator), `warm_up()`. Keeps the model loaded (`OLLAMA_KEEP_ALIVE`), caps reply length (`max_tokens`), disables "thinking" for qwen3/deepseek-r1. The only file that knows about Ollama — swap provider here only. Model choice: see [docs/llm-benchmark.md](docs/llm-benchmark.md) and `scripts/benchmark_llm.py`.

#### `app/services/sentences.py` / `app/services/sentence_pool.py`
Sentence generation — the LLM writes a complete sentence with the exact target form, the server blanks it (`blank_out`) and rejects fragments, repeated forms of the same verb and person mismatches (`quality_problem`); stocked sentences also pass an LLM grammar check (`judge_sentence`) — and the background stock of validated sentences: 20 per language by default (`SENTENCE_POOL_SIZE`), refilled after use and at startup, paused while any user waits on the LLM (`live_request()`).

#### `app/services/exercise_gen.py`
- `LANGUAGE_NAMES` — display names map.
- `TENSES_BY_DIFFICULTY` — maps A1–C1 difficulty to allowed tenses (only place difficulty semantics live).
- `GENERATORS` dict — prompt-builder functions per exercise type.
- `CHECKERS` dict — answer-check functions for grammar and reading (sync).
- `check_conjugation` — async checker: if LLM's `correct_answer` doesn't match, falls back to querying `verb_conjugations` to accept any valid form.

#### `app/services/grading.py`
`grade(answer, accepted)` → `correct`, `almost` (only accents differ — still logged as a mistake, with `attempts.is_almost`), or `wrong`. Used by the drill, sentence completion and the classic exercise check; `frontend/src/utils/grading.js` mirrors it for the verb table.

#### `app/services/explain.py`
Rule-based (no LLM) one-line explanations: accent slip, another person's form, a form from another tense, irregular vs a model regular verb (hablar/comer/vivir) with the new stem, or the regular pattern itself.

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

#### `alembic/versions/d4f6b8c0e2a3_add_sentence_pool.py`
Creates `sentence_pool` (pre-generated practice sentences; raw SQL, reuses the `language` enum).

#### `alembic/versions/f6b8d0e2a4c5_add_vocabulary.py`
Creates `vocab_items`, `vocab_reviews`, `vocab_attempts` (raw SQL, reuses the `language` enum).

#### `scripts/seed_vocabulary.py`
Loads `backend/data/vocabulary/{language}.json` into `vocab_items` (upsert — re-run after editing the JSON). Words were chosen and ranked with the [FrequencyWords](https://github.com/hermitdave/FrequencyWords) subtitle frequency lists (CC BY-SA 4.0); translations, topics and examples are curated in the JSON.

#### `alembic/versions/d1f3a5b7c9e0_grammar_topics.py`
Creates `grammar_attempts` and `grammar_reviews` and drops `grammar_pool` (the old stock of AI-made grammar exercises).

#### `alembic/versions/a7c9e1f3b5d6_add_personal_words.py`
Adds `vocab_items.owner_id` (personal words) with partial unique indexes for shared vs personal items, and the `word_lookups` cache.

#### `alembic/versions/e5a7c9d1f3b4_add_sentence_pool_prompt_version.py`
Adds `sentence_pool.prompt_version`; sentences from older prompts are never served.

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
/                          → Dashboard  (today's goal, Continue, what's due)
/practice/:language/…      → only for a language in LANGUAGES (anything else goes home); today that's /practice/spanish
/practice/:language        → Practice  (exercise type picker)
/practice/:language/conjugation → Conjugation  (verb drill hub)
/practice/:language/review → Review  (weak-spot drill)
/practice/:language/vocabulary → Vocabulary
/practice/:language/conversation → Conversation  (AI role-play)
/progress                  → Progress  (stats and charts)
/practice/:language/grammar → Grammar  (score, topics to review, topics by level and category)
/practice/:language/grammar/:topic → GrammarTopic  (the rule and the sheets)
/practice/:language/grammar/:topic/:sheet → GrammarSheet  (a sheet, or "review")
/exercise                  → Exercise  (reading answer screen)
/settings                  → Settings  (learning prefs, change password, log out)
```

### Auth (`src/auth/`)
`AuthProvider` loads `/auth/me` on startup and exposes `{ user, loading, login, signup, logout, setUser }` via `useAuth()`. Any 401 from the API (expired session) clears the user, which sends them to `/login`.

### `src/api.js`
Single module for all backend calls. All paths prefixed with `/api`; the session cookie rides along automatically. Methods: `signup`, `login`, `logout`, `me`, `updateSettings`, `changePassword`, `generateExercise`, `checkAnswer`, `getProgress`, `searchVerbs`, `getVerbTenses`, `getVerbEndings`, `getRandomVerbs`, `getVerbTable`, `recordAttempts`, `getWeakSpots`, `getDrill`, `checkDrill`, `getStats`, `getGrid`, `chat`, `chatStream`, `generateSentences`, `checkSentence`. Errors are thrown as `ApiError` (with `.status`).

### Pages

#### `src/pages/Review.jsx` (`/practice/:language/review`)
Review drill: one verb + tense + person at a time, graded by the server, keyboard-only flow (Enter to check, Enter for next). Serves what's due, or one verb + tense with `?verb=&mood=&tense=` (from "My mistakes"). The summary says where each verb + tense now stands (needs work / getting there + next check-up / fixed).

#### `src/pages/Progress.jsx` (`/progress`)
Stats, in two tabs (`?view=mistakes`; `?language=` and language tabs only matter once more than one language is offered). Overview: answer/accuracy/streak/daily-goal tiles, 30-day activity chart, "Work on this", and a verbs × tenses accuracy heatmap (`components/charts/`). My mistakes (`components/MyMistakes.jsx`): the whole history of mistakes, filterable by status, with a "Practise" button per verb + tense.

#### `src/pages/Vocabulary.jsx` (`/practice/:language/vocabulary`)
Everyday phrases and words by topic with learned/total progress, "Review now" when items are due, exercise styles (Mixed, Flashcards, Multiple choice, Typing, Fill the gap, Listening), and a browse list per topic. Sessions run in `components/vocab/VocabSession.jsx`.

#### `src/pages/Conversation.jsx` (`/practice/:language/conversation`)
Pick a scenario, then chat (`components/conversation/ConversationChat.jsx`): the AI's lines stream in, and once complete their words are clickable (meaning / add to my words), with 🔊 and Translate. Each of your messages gets a ✓ or a compact correction (fixed words highlighted, one line why). Accent buttons under the box, optional "Read replies aloud", and Finish shows the session summary.

#### `src/components/reading/ClickableText.jsx`
Used for reading passages: every word is a button; clicking shows a popover with the dictionary form, meaning and source, and "Add to my words". Saved words show up as "My words" on the Vocabulary page.

#### `src/utils/speech.js` / `src/components/SpeakButton.jsx`
Pronunciation with the browser's built-in speech synthesis (free, offline, no backend). `SpeakButton` (🔊) appears next to vocabulary words, examples, browse rows, the reading popup, the drill's correct answer and the completed practice sentence. It renders nothing in browsers without speech support, where the Listening mode is hidden too. **Dictation** (Listening mode, and every other review for well-known items in Mixed mode) plays a phrase or a word's example sentence, with a 🐢 slower replay; misheard words are highlighted after checking.

#### `src/components/MistakeExplanation.jsx` / `SessionSummary.jsx`
Compact feedback after a mistake (one line, all forms behind a toggle) and the end-of-session recap (score, mistakes with accent slips marked, "Review these now") shared by the drill, sentence completion and the classic exercise flow.

#### `src/components/WorkOnThis.jsx`
Compact panel (on `Practice` and `Progress`) listing what needs work, then what's getting there with its next check-up, the number fixed, a "Practise these" button when something is due, and a link to "My mistakes".

#### `src/pages/Dashboard.jsx` (`/`)
Today's answers against the daily goal and the streak, a "Continue practising" button, how many words and verb tenses are due (each a shortcut), tiles for Vocabulary / Conversation / Conjugation / Review, and the "Work on this" panel. With a single language offered there is nothing to pick: Spanish is saved as the user's `target_language` on the first visit (and replaces French/English for anyone who had chosen them). With more than one, the first visit shows a language picker and the header a flag switcher.

#### `src/components/TopBar.jsx`
Practice (your language) · Progress · Settings, with the current page highlighted. On phones (≤ 640 px) the username and Log out are hidden so it fits; Settings has a Log out button.

#### `src/pages/Practice.jsx`
Practice-area picker for a given language. Conjugation, Vocabulary, Conversation and Grammar open their own pages; Reading calls `api.generateExercise()` then navigates to `/exercise` with the exercise in `location.state`.

#### `src/pages/Exercise.jsx`
Answer screen for reading exercises. Reads exercise from `useLocation().state`, submits via `api.checkAnswer()`, shows `FeedbackPanel`.

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
Accent character insertion helper (á, é, í, ó, ú, ñ, ü, ¿, ¡) for input fields.

### Styling
No CSS framework. Each component has a `const s = { ... }` object at the bottom, built from the shared tokens and pieces in `src/theme.js` (`color`, `radius`, and `ui.page / h1 / primary / secondary / chip / chipOn / panel / tile …`). `src/index.css` only holds what inline styles can't do: base reset, focus ring, disabled buttons, tile hover (`hl-tile`) and the phone breakpoint (`hl-wide-only`).

### `vite.config.js`
Proxies `/api/*` → `http://localhost:8000/*` (strips `/api` prefix).

---

## Docker

`docker-compose.yml` runs three services: `postgres:16-alpine` (port 5433), FastAPI backend (port 8000), and React/nginx frontend (port 5173). `backend/entrypoint.sh` runs `alembic upgrade head`, then `scripts/seed_conjugations.py` (idempotent — a fast no-op once already seeded), then `scripts/seed_vocabulary.py`, then starts uvicorn. Ollama stays on the host at `host.docker.internal:11434`.

`frontend/nginx.conf` — nginx config for the production frontend container; proxies `/api/` to the backend service.

---

## Languages

Only Spanish is offered: `LANGUAGES` in `frontend/src/constants.js` lists just Spanish, so no page offers a choice, and `learningLanguage(user)` falls back to Spanish for anyone whose `target_language` is something else. French and English stay fully in the backend (`Language` enum, seeded `verb_conjugations`, French vocabulary) — to bring one back, add it to `LANGUAGES` again; the language picker, dashboard switcher, Progress tabs and Settings select reappear on their own.

### Adding a new language

1. Add to `Language` enum in `backend/app/models.py`
2. Add display name to `LANGUAGE_NAMES` in `backend/app/services/exercise_gen.py`
3. Add to `LANGUAGES` array in `frontend/src/constants.js` (used by `Dashboard`, `Settings`, `Progress` and the `/practice/:language` route guard)
4. Run migration: `alembic revision --autogenerate -m "add language X" && alembic upgrade head`
5. If mlconjug3 supports it, add to `LANG_CODES` in `scripts/seed_conjugations.py` and re-seed
6. For vocabulary, add `backend/data/vocabulary/{language}.json` and the language to `VOCAB_LANGUAGES`, then run `scripts/seed_vocabulary.py`

See [CLAUDE.md](CLAUDE.md#adding-a-new-language) for the full mlconjug3 data-quality checklist (person-index quirks, phantom list entries, etc.) — every item on it caused a real, silent bug for Spanish or French and is worth checking before trusting a new language's seeded data.
