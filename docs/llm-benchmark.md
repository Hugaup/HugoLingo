# Local LLM benchmark

How the local Ollama models compare on HugoLingo's real work, and why the app
uses the model it does. Re-run it whenever prompts or candidate models change.

```bash
cd backend && source .venv/bin/activate
python scripts/benchmark_llm.py qwen2.5:7b qwen2.5:3b qwen3:4b qwen3:8b gemma3:4b --n 20 --out results.json
```

Every model gets the same 20 Spanish prompts (fixed seed: common verbs × the
six everyday tenses × random persons), built with the app's own prompt code
(`app/services/sentences.py`), plus 5 short explanation requests.

- **Pass app checks** — the output passes the same validation the app applies
  before showing a sentence (exactly one clean `___` blank, answer not leaked,
  subject matches the person).
- **+ complete** — also at least five words and ending in `.`, `!` or `?`,
  which catches fragments like "Esta mañana ___" that the app's checks let through.

## Run 1 — 2026-10-03 (Apple M5, 24 GB, Ollama 0.31.2)

| Model | Load (s) | Sentence median (s) | Sentence p90 (s) | Tokens/s | Pass app checks | + complete | Explanation median (s) |
|---|---|---|---|---|---|---|---|
| **qwen2.5:7b** | 8.5 | 2.26 | 2.49 | 28.1 | 75% | **65%** | 3.33 |
| qwen2.5:3b | 0.1 | 1.08 | 1.19 | 57.2 | 55% | 30% | 1.87 |
| qwen3:4b | 9.5 | 1.35 | 1.50 | 44.7 | 30% | 0% | 6.01 |
| qwen3:8b | 2.6 | 2.92 | 3.70 | 23.3 | 35% | 30% | 5.93 |
| gemma3:4b | 3.0 | 1.71 | 1.86 | 39.1 | 5% | 5% | 3.50 |

(qwen3 models run with thinking disabled; "Load" is the cold load, which the
app now pays once at startup instead of on a user's first request.)

### Reading the outputs, not just the numbers

- **qwen2.5:7b** is the most reliable, but only ~8 of its 20 sentences are
  genuinely good. Typical failures that pass the checks: ungrammatical
  constructions ("Quiero que yo ___…"), another conjugated verb next to the
  blank ("Mañana ___ iréis al mercado…"), or a wrong form beside it
  ("Ojalá __ creara…").
- **gemma3:4b** writes the most natural Spanish but almost never replaces the
  verb with `___` itself — 18 of its 20 sentences contain the exact target
  form. If the *server* did the blanking instead of asking the model to, it
  could become the faster and better option.
- **qwen3** (4b/8b) with thinking off produces fragments ("yo ___ ayer") and
  slower explanations; with thinking on it would be several times slower still.
- **qwen2.5:3b** is twice as fast as 7b but half as reliable.

## Run 2 — 2026-10-03, new sentence pipeline (prompt v2)

What changed: the model now writes one *complete* sentence containing the exact
form (with a worked example in the prompt), the **server** does the blanking,
and stricter checks reject fragments, other forms of the same verb and person
mismatches. "Judge approved" = the model's own grammar check, which the app
runs on every background-stock sentence.

```bash
python scripts/benchmark_llm.py qwen2.5:7b qwen2.5:3b qwen3:4b qwen3:8b gemma3:4b --n 20 --judge
```

| Model | Load (s) | Sentence median (s) | Sentence p90 (s) | Tokens/s | Usable after checks | + judge approved | Explanation median (s) |
|---|---|---|---|---|---|---|---|
| **qwen2.5:7b** | 0.2 | 1.67 | 1.85 | 28.3 | 95% *(was 65%)* | 75% | 3.44 |
| qwen2.5:3b | 0.1 | 0.93 | 1.01 | 59.4 | 100% *(was 30%)* | 40% | 1.94 |
| qwen3:4b | 1.4 | 1.51 | 1.58 | 38.8 | 95% *(was 0%)* | 5% | 7.91 |
| qwen3:8b | 2.2 | 2.32 | 2.44 | 23.3 | 100% *(was 30%)* | 75% | 5.49 |
| gemma3:4b | 0.2 | 1.56 | 1.67 | 35.7 | 90% *(was 5%)* | 35% | 3.39 |

Manual read of every sentence:

- **qwen2.5:7b** — ~17/20 genuinely good (was ~8). E.g. "Ellos siempre deciden
  salir de paseo los domingos por la tarde.", "Yo siempre pongo música mientras
  hago ejercicio." Its misspelt output ("bailémos") is now rejected automatically.
- **qwen2.5:3b** — ~13/20 good; still writes "Quiero que yo baile…" (rightly
  rejected by the judge) and agreement slips ("vosotros … tus tíos").
- **qwen3:8b** — comparable to 7b but slower, with odd collocations
  ("habéis bajado el volumen todavía no").
- **gemma3:4b** — natural style now that blanking is server-side, but more
  tense/person drift (wrote "tú quedes" when asked for "quede").
- The judge is only as good as the model: qwen3:4b rejects nearly everything.
  With qwen2.5:7b it filters real errors and sometimes rejects a fine sentence
  (which only costs background time).

## Run 3 — 2026-10-03, conversation corrections (feature/conversation)

Before building conversation practice, the message check was prototyped on
qwen2.5:7b (JSON mode, temperature 0) with 22 learner messages in Spanish and
French: 11 correct, 11 with one classic mistake (wrong person, infinitive left
unconjugated, gender agreement, *mucho hambre*, *gusta los deportes*, missing
accent, *soy cansado*, *j'ai allé*…). A "flag" means the corrected message
differs from the original once punctuation and capitals are ignored.

| Prompt | Right | False corrections | Missed mistakes | Time / message |
|--------|-------|-------------------|-----------------|----------------|
| A — "fix only real mistakes, keep the rest" | 13/16* | 0 | 3 | 2.5 s |
| B — list every mistake first, then the corrected text | 14/16* | **2** ("Fui" → "Fuí", "J'ai allé" → "J'ai aller") | 1 | 4.5 s |
| C — A + a checklist (verb form/auxiliary, agreement, accents) + "if unsure, leave it" | **20/22** | **0** | 2 (*soy cansado*, *j'ai allé*) | 2.8 s |

\* first 16 messages only.

**Chosen: C** (`services/conversation.CHECK_PROMPT`). A wrong correction teaches a
mistake, so a prompt that never "fixes" correct text beats one that catches one
more error. Missed mistakes just go uncorrected. Two guards in `classify()` drop
answers that rewrite the message or paste in the other person's line.

The model's one-line *explanation* was sometimes off ("added the accent on
querer"), so when the fix is a verb form the conjugation data can pin down,
the rule-based `explain_mistake` line replaces it.

## Decision

**qwen2.5:7b** stays the default after run 2: best quality, now faster than
before (shorter prompt: 2.26 s → 1.67 s per sentence), and the background stock
hides its speed for most requests anyway. qwen2.5:3b is the fallback if speed
ever matters more than quality (set `OLLAMA_MODEL=qwen2.5:3b`).

### Run 1 decision (kept for history)

Keep **qwen2.5:7b** as the default for now. The speed work in this branch
doesn't depend on the model:

- the model stays loaded between requests (`OLLAMA_KEEP_ALIVE`, default 30 min)
  and is loaded at backend startup, removing the ~8.5 s cold start;
- answer lengths are capped per call (sentences 200 tokens, explanations 250);
- chat replies stream, so text appears after a fraction of a second instead of
  after the full ~3 s reply;
- a background stock of validated sentences (`sentence_pool`, 20 per language)
  makes starting sentence practice near-instant.

**Done in run 2 (feature/sentence-quality):** moved the blanking to the server, tightened
the validation with the failure patterns above, and re-ran this benchmark —
see "Run 2" above.
