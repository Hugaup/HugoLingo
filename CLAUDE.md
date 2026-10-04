# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A language learning web app (alternative to Duolingo) powered by a local LLM (Qwen2.5 7B via Ollama). **Only Spanish is offered for now** (user decision, 2026-10-04): `frontend/src/constants.js` `LANGUAGES` lists just Spanish, every page hides its language choice when there's one language, `learningLanguage(user)` falls back to Spanish, and `/practice/<other>` redirects home. French/English code and data stay in place (don't delete them) — re-adding them to `LANGUAGES` brings them back. Practice areas: verb conjugation, vocabulary, conversation, grammar correction and reading comprehension. Includes a pre-seeded `verb_conjugations` table (1.68M rows) used to validate conjugation answers independently of the LLM.

## Running the app

`./dev.sh` (repo root) starts everything: brew Postgres, `ollama serve`, `alembic upgrade head`, uvicorn `--reload` on 8000 and Vite on 5173 (`--strictPort`), with `[api]`/`[web]`-prefixed logs, then opens the browser. Ctrl+C stops all four (including the Ollama app and Postgres); `./dev.sh stop` does the same from another terminal. It must stay bash 3.2 compatible (macOS default) and pass `shellcheck` (CI runs it). Manual steps, if needed:

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

## Tests

```bash
cd backend && source .venv/bin/activate && pytest     # needs Postgres; uses language_learning_test (auto-created, refuses non-"test" DB names)
cd frontend && npm test                                 # Vitest + RTL, fetch is mocked
```

Every feature should ship with tests (user requirement). Backend fixtures (`tests/conftest.py`): `client`, `new_client()` (separate cookie jars = separate browsers), `logged_in(username, password)` → `(client, user_json)`, `db`. The test schema is built from `Base.metadata.create_all`, not migrations — CI separately runs `alembic upgrade head && alembic check` to catch model/migration drift. Frontend helpers (`src/test/helpers.jsx`): `mockBackend({'METHOD /path': {status, body} | fn})`, `calls(fetchMock)`, `renderAppAt(path)`.

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
python scripts/seed_vocabulary.py   # words + phrases from backend/data/vocabulary/*.json (upsert, re-run after editing the JSON)
```
This reads mlconjug3's bundled JSON files (`data/conjug_manager/verbs-{lang}.json` + `conjugation-{lang}.json`) directly — no ML model is loaded. Each verb entry has a `root` string and a `template` name; the conjugated form is `root + suffix` from the template.

## Architecture

```
backend/app/
├── main.py          — FastAPI app, CORS (allows localhost:5173), router registration (login required on all but auth)
├── config.py        — Settings from .env: DATABASE_URL, OLLAMA_URL, OLLAMA_MODEL, COOKIE_SECURE
├── database.py      — Async SQLAlchemy engine + AsyncSessionLocal + get_db dependency
├── dependencies.py  — get_current_user (session cookie → User, else 401)
├── models.py        — ORM models: User, UserSession, Exercise, Progress, Attempt, ReviewItem, SentencePoolItem, GrammarAttempt, GrammarReview, VocabItem, VocabReview, VocabAttempt, WordLookup, ConversationTurn, VerbConjugation (+ enums)
├── schemas.py       — Pydantic request/response schemas
├── routers/
│   ├── auth.py                 — POST /auth/signup|login|logout|password, GET|PATCH /auth/me
│   ├── exercises.py            — POST /exercises/generate (conjugation/reading; grammar → 400, it has its own section), POST /exercises/check
│   ├── grammar.py              — GET /grammar/{language}, GET /grammar/{language}/topics/{topic}[/sheets/{n}|/review], POST /grammar/answer
│   ├── progress.py             — GET /progress (current user)
│   ├── verbs.py                — GET /verbs/search|tenses|endings|random/{language}, GET /verbs/table/{language}/{infinitive} — reads verb_conjugations directly, no LLM
│   ├── chat.py                 — POST /chat, POST /chat/stream (plain-text streaming) — freeform passthrough to the LLM
│   ├── conjugation_exercises.py — POST /conjugation-exercises/sentence/generate (stock first, then live via services/sentences) | check (no LLM call)
│   ├── history.py              — POST /history/attempts, GET /history/weak-spots|drill|mistakes/{language}, POST /history/drill/check, GET /history/stats, GET /history/grid/{language}
│   ├── vocabulary.py           — GET /vocab/{language}/overview|session|items, POST /vocab/check|lookup|my-words, DELETE /vocab/my-words/{id}
│   └── conversation.py         — GET /conversation/scenarios, POST /conversation/reply (streamed), POST /conversation/check
└── services/
    ├── auth.py              — scrypt password hashing, session token generation/hashing (pure, no DB)
    ├── llm.py               — LLMClient singleton wrapping Ollama /api/chat: chat/chat_json/chat_stream/warm_up
    ├── sentences.py         — sentence generation: prompt (v2), blank_out(), quality_problem(), judge_sentence(), generate_one(); COMMON_TENSES
    ├── sentence_pool.py     — background stock of validated sentences: take(), refill(), live_request()
    ├── exercise_gen.py      — Prompt templates, answer checkers, GENERATORS/CHECKERS dicts (conjugation + reading)
    ├── grammar_topics.py    — the grammar section: loads data/grammar/{language}/ topics, grades, records (grammar_attempts/grammar_reviews), progress, review sheets, weak topics
    ├── grammar.py           — find the mistake: the hand-written pairs bank, find_fix(), grade_answer(), accepted_corrections()
    ├── history.py           — record_attempts (attempts + Leitner review boxes), review statuses / "Work on this", mistake history, drill prompts, stats/streak, verb×tense grid
    ├── conversation.py      — role-play scenarios, reply prompt, message check (classify + verb_mistakes), record_turn
    ├── lookup.py            — click-a-word lookup (curated → verb forms/plurals → word_lookups cache → LLM) and "my words"
    ├── vocabulary.py        — vocabulary seeding (upsert), accepted answers/grading, sessions (due → new → weak), Leitner reviews, overview
    ├── grading.py           — grade(answer, accepted) → correct | almost (accent-only difference) | wrong; normalize/fold_accents
    ├── explain.py           — explain_mistake(): one-line rule-based feedback (no LLM) + the whole tense for a "show all forms" toggle
    └── conjugation_utils.py — tense_table()/expected_forms() (accepted answers per person, compounds resolved), PRONOUNS, PERSON_ORDER, Spanish compound-tense resolution (pairs a participle row with the matching haber row, e.g. tense "pretérito perfecto compuesto" + person "1s" → "he hablado") and FORM_ALTERNATES (interchangeable forms, e.g. "hay"/"ha")
```

`GET /health` is defined directly in `main.py`, not a router.

**Key design decisions:**

- **LLM abstraction:** `LLMClient` in `services/llm.py` is the only file that knows about Ollama. It is instantiated once at module level (`llm_client = LLMClient()`). To swap providers, change only this file. Every request sets `keep_alive` (model stays loaded), a `num_predict` cap (`max_tokens=` per call; sentences 200, explanations 250, default 600) and `think: false` for thinking-model families (qwen3, deepseek-r1). The model is warmed up at startup (`main.py` lifespan). Model choice is backed by `docs/llm-benchmark.md` / `scripts/benchmark_llm.py` — re-run it before switching models or after changing prompts.

- **Sentence generation pipeline (`services/sentences.py`).** The LLM writes one *complete* sentence containing the exact target form; the **server** blanks it (`blank_out`: whole-word, case-insensitive, must occur exactly once — small models can't reliably blank their own output). `quality_problem` then rejects fragments (< 4 words besides the blank, no final punctuation), any other form of the same verb in the sentence (forms from `verb_conjugations`, minus `_AMBIGUOUS_WORDS` like "como"/"para"/"été") and subject/person conflicts. Background stock sentences also get an LLM grammar check (`judge_sentence`, `SENTENCE_JUDGE`); live generation skips it for speed. **Bump `SENTENCE_PROMPT_VERSION` whenever the prompt or checks change** — stocked sentences from older versions are never served and are purged on the next refill. Measure prompt changes with `scripts/benchmark_llm.py --judge`.

- **Never make a user wait on the LLM when it can be avoided.** Sentence practice is served from `sentence_pool` (pre-generated, validated, deleted when served, refilled in the background); the sentence check returns the rule-based hint instantly and the LLM's long explanation is streamed from `/chat/stream` only if the user opens it (`ChatPanel autoAsk`). Ollama handles one request at a time, so **any endpoint where a user waits on the LLM must wrap the call in `sentence_pool.live_request()`** — background refills pause while it's held (for streams, hold it inside the generator). Tests set `LLM_WARMUP=false` / `SENTENCE_POOL_ENABLED=false`; drive the pool explicitly with `sentence_pool.refill(..., session_factory=TestSession, client=fake)`.

- **Conjugation answer checking is async; grammar and reading are sync.** `check_conjugation` in `exercise_gen.py` is `async` because it does a DB fallback lookup — if the LLM's `correct_answer` doesn't match, it queries `verb_conjugations` to accept any valid form of the verb. The router special-cases this with `await check_conjugation(..., db, exercise.language)` rather than going through the `CHECKERS` dict (which only contains grammar and reading).

- **Exercises are persisted on generation** as a cache and for progress attribution. The `content` column is JSON and stores the full LLM response.

- **Frontend Vite proxy:** `fetch('/api/exercises/generate')` → Vite strips `/api` → hits `localhost:8000/exercises/generate`. All API calls go through `/api` prefix. The `api.js` module is the only place that constructs fetch calls.

- **React Router state-passing:** (all of these sit under the `RequireAuth` layout route) `Dashboard` (`/`; first visit picks `target_language`, then goal/streak/Continue/due counts) → `Practice` (`/practice/:language`) → either `Exercise` (`/exercise`, for grammar/reading/conjugation-quiz) or `Conjugation` (`/practice/:language/conjugation`, the verb-table/sentence-completion/chat area). `Practice` calls `api.generateExercise()` then navigates to `/exercise` with the exercise object in `location.state`; `Exercise` reads it back via `useLocation().state`. `/practice/:language/review` is the weak-spot drill (`Review.jsx`, reached from the `WorkOnThis` panel on `Practice` and `Progress`); `/progress` is the stats page (`Progress.jsx`, charts in `components/charts/`).

- **Two parallel conjugation-practice paths:** the original `ExerciseType.conjugation` flow (`exercises.py` + `exercise_gen.py`, single LLM-generated fill-in-the-blank, DB-validated) still exists and is reachable via the "Conjugation" card on `Practice`. Separately, `pages/Conjugation.jsx` (routed at `/practice/:language/conjugation`) is a richer practice area — verb lookup/tables (`verbs.py`, pure DB reads, no LLM), sentence completion (`conjugation_exercises.py`, LLM-generated), and freeform chat (`chat.py`) — built directly on `verb_conjugations` rather than going through `Exercise`/`ExerciseType`. The two paths don't share code beyond the DB table and `LLMClient`.

- **Spanish compound tenses need two DB rows:** `verb_conjugations` only stores the participle for compound tenses (e.g. "pretérito perfecto compuesto" stores "hablado", not "he hablado"). `conjugation_utils.COMPOUND_AUX_MAP` + `load_haber_forms`/`resolve_compound_form` look up the matching `haber` conjugation and prepend it. Used by both `verbs.py` (table display) and `conjugation_exercises.py` (marking the correct answer). Only applies to Spanish — French/English compounds aren't in the seed data.

- **Auth is cookie sessions, not JWT.** `routers/auth.py` (signup/login/logout/me/password) issues a random token in an httpOnly `hugolingo_session` cookie; only its SHA-256 is stored in `user_sessions`, so logout and password change revoke sessions server-side. `dependencies.get_current_user` is applied to every non-auth router in `main.py` via `include_router(..., dependencies=...)` — **new routers must be registered the same way** or they'll be public. Routes that need the user object also take `user: User = Depends(get_current_user)` (FastAPI caches it per request). Never accept a `user_id` from the request body. Passwords: stdlib scrypt in `services/auth.py`, deliberately no rules beyond length ≥ 4 (product decision). On the frontend, `AuthProvider` + `RequireAuth` gate every route except `/login`/`/signup`, and `api.js` reports any 401 back to `AuthProvider` so expired sessions bounce to login.

- **Every conjugation answer is recorded via `services/history.record_attempts`** — one `attempts` row per answer plus a Leitner box per (user, language, verb, mood, tense) in `review_items` (wrong → box 0, due now; right → next box, due in 1/3/7/14/30 days — **but only if it was due**, so a right answer before the check-up changes nothing; "due" opens `DUE_SLACK` = 8 h early; a batch moves each box once). Vocabulary reviews share `next_review`, so the same rule applies to words. Wiring per practice area: sentence completion is recorded inside `/conjugation-exercises/sentence/check` (before the LLM call; naming the wrong tense counts as a miss); the review drill grades server-side in `/history/drill/check` via `conjugation_utils.expected_forms`; the verb table is graded **in the browser** and reports via `POST /history/attempts` (the only client-reported source — `source` is a `Literal["verb_table"]`); the old `exercises.py` conjugation flow records verb-level only (`mood`/`tense` NULL — its LLM tense names don't map to the DB, so it never creates review items). `attempts.tense` is always `canonical_tense()`d. A new practice area must record its answers or it won't feed "Work on this".

- **Grammar is hand-written, organised like lingua.com/spanish/grammar** (user decision 2026-10-04: no LLM for grammar "for the moment"; the old generator + `grammar_pool` live in git history before `d1f3a5b7c9e0`). `backend/data/grammar/spanish/` holds `index.json` (categories in order + topic order) and one JSON file per topic: title, Spanish title, category, CEFR level 1–5, a 2–5 line `rule`, and `sheets` of questions `[id, text with one ___, answer, [3 wrong options], why]`. All sentences are original — never copy Lingua's (or anyone's) questions. Write new questions without an id and run `python scripts/format_grammar_topics.py spanish` (assigns `"{sheet}-{nn}"` ids, lays the file out); **never change or reuse an id** — answers are stored against it. `tests/test_grammar_topics.py` checks every file (one gap, four distinct options, 10–16 per sheet, ids). Make sure only one option fits: a "wrong" option that's grammatical with another meaning (e.g. *trabajaron* vs *trabajaban* without a time marker, *por/para* both possible, Latin-American usages like *¿cuál libro?*) is a bug — add context instead. Options are shuffled once per question id (stable) and graded by exact match (*a El* ≠ *a el*). The find-the-mistake pairs (`data/grammar/{language}.json`, typed corrections graded by `grammar.grade_answer`: capitals/punctuation ignored, accents-only "almost", `fix` marked up by `FeedbackPanel`) are one more topic, `find-the-mistake`, with a sheet per level. Every answer is a `grammar_attempts` row (counted in `history.stats`); a mistake gives the topic a `grammar_reviews` Leitner box with the same `next_review`/`review_status` as verbs, so topics show in "Work on this" (`/history/weak-spots` → `topics`, `grammar_due_count`) and "My mistakes" (`topics`). Sheet progress = the latest answer per question (DISTINCT ON). A topic's review sheet: last-wrong questions first, then never-answered, then the rest. Frontend: `pages/Grammar.jsx` (score, "To review", level → category → topic), `GrammarTopic.jsx` (rule + sheets), `GrammarSheet.jsx` (all questions on one page, marked on click, "You have answered X of N", restart, results).

- **One grader, three outcomes.** Every exact-answer check goes through `services/grading.grade()`: `correct`, `almost` (equal once accents are folded — tuvó/tuvo, nino/niño) or `wrong`. Product rule: **"almost" is shown kindly but always recorded as a mistake** (`is_correct=False`, `attempts.is_almost=True`). The browser-graded verb table uses the mirror `frontend/src/utils/grading.js` — change both together. Reading answers keep their own loose matching and never return "almost".

- **Mistake explanations are rule-based, not LLM** (`services/explain.py`), so they're instant and short (the user asked that feedback not crowd the screen). First matching rule wins: accent slip → another person's form in the same tense → a form from another tense → irregular vs the `REGULAR_MODELS` verb for that ending (with the shared stem, e.g. "tuv-") → the regular pattern. Frontend shows the line via `MistakeExplanation` (forms behind a toggle). Sentence completion still gets the LLM's longer explanation, but folded behind "AI explanation & questions". Every practice session ends in the shared `SessionSummary`.

- **Vocabulary is curated data, not LLM output.** `backend/data/vocabulary/{language}.json` (Spanish, French; ~250 words in 11 topics + ~40 everyday phrases each) holds the word, article, English translations (`;`-separated alternatives), part of speech, a FrequencyWords subtitle-frequency `rank` (→ `level`: ≤1500 A1, ≤4000 A2, else B1) and an example that contains the word verbatim (used for fill-the-gap via `blank_out`). Edit the JSON and re-run `seed_vocabulary.py` — it upserts by (language, kind, text). Vocabulary has its own reviews/attempts tables (`vocab_reviews`, `vocab_attempts`, same Leitner scheduling) but counts toward the shared daily stats/streak (`history.stats` unions both attempt tables). Grading accepts the word with or without its article, and English answers with or without "to"/"the"/"a"; punctuation is ignored; accent-only slips are "almost" (multiple choice never is). The frontend picks the exercise per item (`utils/vocab.pickExercise`): new → flashcard, box 0–1 → multiple choice, box 2 → type it, box ≥3 → fill the gap (box ≥4 alternates with dictation when the browser can speak).

- **Audio is browser-only.** `utils/speech.js` wraps `window.speechSynthesis` (language → BCP-47 voice in `VOICE_LANG`); no TTS on the backend. Everything speech-dependent is gated on `canSpeak()`: `SpeakButton` renders nothing, the `needsSpeech` Listening mode is filtered out, and `pickExercise(..., canListen)` never returns `dictation`. The `dictation` exercise's answer is the phrase itself or a word's example sentence (`vocabulary.accepted_answers` / `utils/vocab.dictationText` — keep them in sync). jsdom has no speech API, so tests stub `speechSynthesis` + `SpeechSynthesisUtterance` with `vi.stubGlobal` (see `src/test/audio.test.jsx`).

- **Conversation practice** (`services/conversation.py`, `pages/Conversation.jsx`, `components/conversation/ConversationChat.jsx`): role-play scenarios (`SCENARIOS`, English metadata; the AI plays `ai_role`). Two LLM calls per learner message, fired together by the frontend: `/conversation/reply` streams the in-character reply (history comes from the client, last `MAX_HISTORY` lines; prompt sets the user's level and forbids correcting), and `/conversation/check` grades the message with the tuned `CHECK_PROMPT` (temperature 0; see docs/llm-benchmark.md run 3 — **don't loosen it without re-running that check: false corrections are worse than misses**). `classify()` ignores punctuation/capital-only changes, treats accent-only fixes as "almost" (still a mistake), and discards untrustworthy answers (rewrites, pasted lines) as "correct". Each message is stored in `conversation_turns` and counts in `history.stats`; replaced words that are verb forms (`verb_mistakes`: token diff against `verb_conjugations`; reflexive twins like irse dropped, ambiguous verbs resolved by the learner's own word) are also recorded as `attempts` with source `conversation` — so they feed weak spots and the review queue — and are **excluded from the stats union** to avoid double counting. When a verb mistake's tense/person is pinned down, the rule-based `explain_mistake` line replaces the model's explanation.
- **Reading teaches words** (`services/lookup.py`, `components/reading/ClickableText.jsx`): every word of a reading passage is clickable. Lookup order, cheapest reliable first: curated `vocab_items` (also via `verb_conjugations` forms → infinitive, simple plurals, French elision) → the `word_lookups` cache → the LLM (JSON: lemma/translation/pos, sentence as context, then cached — one LLM call per word ever; Spanish plural lemmas it returns unchanged are fixed by `singular_guess`). "Add to my words" gives a curated item a review due now, or creates a **personal** `vocab_items` row (`owner_id` = user, kind `personal`, topic `my_words`). Shared vs personal rows are kept apart by two partial unique indexes (`uq_vocab_item_shared` WHERE owner_id IS NULL — the one `upsert_items` targets — and `uq_vocab_item_personal`); every vocabulary query must filter with `vocabulary.visible_to(user_id)`.

- **"Work on this" is a status per review box, not a score.** Anything with `wrong_count > 0` is *needs work* (box 0), *getting there* (box 1–2: right since, the 1-day and 3-day check-ups pending) or *fixed* (box ≥ `FIXED_BOX` = 3) — `history.review_status`, product decision: fixed means passing both check-ups. `/history/weak-spots` lists needs work then getting there (+ counts, `due_count`, `next_check_up_at`); a fixed item that goes wrong again is back to needs work. The drill serves only what's due (`reason` needs_work / check_up), or one verb+tense on request (`?verb=&mood=&tense=`, reason practice, from "My mistakes"); `/history/drill/check` returns the item's new `status`/`due_at` for the end-of-drill "Where you stand" recap. `/history/mistakes/{language}` is the whole history (verbs + words) behind Progress → "My mistakes". `score_groups` (recency-weighted error rate, 14-day half-life over 120 days) now only orders "needs work". The old `exercises.py` flow has no review items, so it never appears there. Tuning knobs are the constants at the top of `services/history.py` (frontend mirror of `DUE_SLACK` in `utils/reviewStatus.js`). Stats days/streaks use the browser's IANA timezone (`tz` param, validated by `resolve_timezone`, passed to Postgres as a bind param).

- **Pre-auth users have `password_hash = NULL`** and can't log in until claimed with `scripts/set_password.py <username> <password> [--rename new]`. The original hardcoded `default` user (id 1) holds early progress history.

- **Difficulty maps to tenses:** `TENSES_BY_DIFFICULTY` in `exercise_gen.py` controls which tenses the LLM is allowed to pick at each level (A1–C1). This is the only place difficulty semantics are defined. It only governs the `exercises.py` flow — the `Conjugation` practice area picks tenses via `verbs.py`'s `get_tenses`/`get_random_verbs` instead, with no difficulty concept.

## Environment

Backend `.env` (auto-loaded by `config.py`):
```
DATABASE_URL=postgresql+asyncpg://localhost/language_learning
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
# Optional (defaults shown): OLLAMA_KEEP_ALIVE=30m, OLLAMA_MAX_TOKENS=600,
# LLM_WARMUP=true, SENTENCE_POOL_ENABLED=true, SENTENCE_POOL_SIZE=20
```

## Frontend styling

No CSS framework. Components use inline style objects at the bottom of each file (`const s = { ... }`), built from **`src/theme.js`**: `color` tokens (primary `#4f46e5`, ink `#1e1b4b`, surface `#f8f9fa`, …), `radius`, and shared pieces in `ui` (`page` with a 16px phone gutter, `back`, `h1`, `h2`, `primary`, `secondary`, `link`, `chip` + `chipOn`/`chipSoftOn`, `panel`, `tile`). Use them for new UI instead of re-typing colours. **Write borders as longhands** (`borderWidth/borderStyle/borderColor`, as `ui.chip` does) whenever a state override changes `borderColor` — mixing the `border` shorthand with a `borderColor` override makes React warn. `src/index.css` holds only what inline styles can't: reset, `:focus-visible` ring, `button:disabled` look, `.hl-tile` hover, and the `.hl-wide-only` class hidden at ≤ 640px (the top bar uses it; Settings has the phone Log out). Check new pages at 390px width for sideways overflow.

## Docker

A full three-service stack is defined in `docker-compose.yml` (postgres:16-alpine on port 5433, backend on 8000, frontend/nginx on 5173). The backend `entrypoint.sh` runs `alembic upgrade head`, then `scripts/seed_conjugations.py` (idempotent — skips if `verb_conjugations` already has rows, so this is a fast no-op after the first run), then `scripts/seed_vocabulary.py` (upsert), then starts uvicorn. Ollama is expected at `host.docker.internal:11434` (i.e. still running on the host).

## Adding a new language

1. Add the value to `Language` enum in `backend/app/models.py`
2. Add its display name to `LANGUAGE_NAMES` in `backend/app/services/exercise_gen.py`
3. Add it to the `LANGUAGES` array in `frontend/src/constants.js` (shared by `Dashboard`, `Settings`, `Progress` and the `/practice/:language` route guard)
4. Run `alembic revision --autogenerate -m "add language X"` and `alembic upgrade head`
5. If mlconjug3 supports the language (fr/es/en/it/pt/ro), add it to `LANG_CODES` in `backend/scripts/seed_conjugations.py` and re-run the seed script
5b. For vocabulary, add `backend/data/vocabulary/{language}.json` (same shape as spanish.json; every `ex` must contain its `word` exactly once — `tests/test_vocabulary.py` enforces this), add the language to `VOCAB_LANGUAGES` in `services/vocabulary.py`, and run `scripts/seed_vocabulary.py`
5c. For grammar, add `backend/data/grammar/{language}/` (an `index.json` + one file per topic, same shape as spanish/; `tests/test_grammar_topics.py` checks them) and optionally a find-the-mistake bank at `backend/data/grammar/{language}.json` (`tests/test_grammar.py` checks every pair is one small change)
6. **Before trusting the seeded data, audit it for these mlconjug3 quirks** — every one of these caused a real, silent bug for Spanish and/or French (see the git history around the conjugation-data PRs) and is worth checking for any new language before calling the seed "done":
   - **Mixed-case tense-name duplicates.** Some templates (e.g. Spanish's defective-verb templates) spell a tense name with different capitalization than the regular templates use for that same tense. `SELECT mood, tense, count(*) FROM verb_conjugations WHERE language=... GROUP BY mood, tense` and scan for near-duplicates differing only in case.
   - **Non-standard person indexing.** Don't assume every list-type tense uses the plain 6-slot index (0=1s…5=3p). The imperative mood usually has no 1st-person-singular slot, so it's indexed compactly starting at 0 instead (Spanish: 5 slots, French: 3 slots) — dump the raw template JSON for a well-known verb and cross-check every resulting person against a real conjugation table (one regular verb, one irregular) before trusting the mapping.
   - **Phantom extra list entries.** Some non-personal moods (infinitive, gerund) list a second entry that's actually just the past participle again (internal bookkeeping), not a real second form. Survey list *lengths* per (mood, tense) across ALL templates, not just one verb — a mood that's "supposed" to have 1 entry but sometimes has 2 is the tell.
   - **Non-person list entries.** Some list-type tenses encode grammatical agreement rather than person (e.g. French Participe Passé: masculine/feminine × singular/plural). If the persons don't line up with a real conjugation table, check whether they're agreement variants instead.
   - **Compound tenses need a per-language auxiliary map.** `conjugation_utils.COMPOUND_AUX_MAP`/`resolve_compound_form` are currently Spanish-only (`if language != Language.spanish: return participle`). Most Romance languages have compound tenses (Italian avere/essere, Portuguese ter/haver) — if the new language does, the seed data will store the bare participle unless this gets extended per-language.
   - **Fix at the source, then backfill.** `insert_rows` uses `on_conflict_do_nothing()`, so re-running the seed script after fixing `build_rows()` does **not** correct already-seeded bad rows — delete the affected `(language, mood)` rows and re-insert.
7. **Wire the new language into the frontend's tense organization** (`frontend/src/utils/conjugationUtils.js`) — `MOOD_ORDER`, `TENSE_ORDER_IN_MOOD`, `SECTION_MOODS`, and `TENSE_LABEL_OVERRIDES` are all keyed per language. Without an entry, tenses still work but sort into an unordered bucket and show raw/awkward DB labels instead of clean ones.

Note: the `Language` enum already has `norwegian` and `galician`, but `constants.js` currently only lists Spanish — French and English are hidden (data kept), and Norwegian and Galician aren't reachable from the UI and have no seeded `verb_conjugations` data (mlconjug3 doesn't support them).
