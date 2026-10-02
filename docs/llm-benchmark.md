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

## Decision

Keep **qwen2.5:7b** as the default for now. The speed work in this branch
doesn't depend on the model:

- the model stays loaded between requests (`OLLAMA_KEEP_ALIVE`, default 30 min)
  and is loaded at backend startup, removing the ~8.5 s cold start;
- answer lengths are capped per call (sentences 200 tokens, explanations 250);
- chat replies stream, so text appears after a fraction of a second instead of
  after the full ~3 s reply;
- a background stock of validated sentences (`sentence_pool`, 20 per language)
  makes starting sentence practice near-instant.

**Next (feature/sentence-quality):** move the blanking to the server, tighten
the validation with the failure patterns above, and re-run this benchmark —
gemma3:4b and qwen2.5:3b get another chance under the new prompt.
