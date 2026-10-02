#!/usr/bin/env python3
"""Compare Ollama models on HugoLingo's real prompts: speed and output validity.

Every model gets the exact same prompts (same verbs, tenses and persons, fixed
seed), built with the app's own code:
  - sentence generation: the real conjugation-exercise prompt (JSON output),
    scored with the app's own validity checks (one clean blank, answer not
    leaked, subject matches the person);
  - short explanations, like the feedback after a sentence check.

Run from backend/ with Ollama running and the models pulled:
    source .venv/bin/activate
    python scripts/benchmark_llm.py qwen2.5:7b qwen2.5:3b qwen3:4b --n 20 --out results.json
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Language, VerbConjugation
from app.routers.verbs import COMMON_VERBS
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient
from app.services.sentences import (
    COMMON_TENSES, SENTENCE_MAX_TOKENS, _sentence_is_valid, build_sentence_messages, target_forms,
)

TENSES = COMMON_TENSES
PERSONS = ["1s", "2s", "3s", "1p", "2p", "3p"]
EXPLANATIONS_PER_MODEL = 5


async def build_prompts(language: Language, n: int, seed: int) -> list[tuple[VerbConjugation, str, list[str]]]:
    rng = random.Random(seed)
    verbs = sorted(COMMON_VERBS[language])
    prompts = []
    async with AsyncSessionLocal() as db:
        while len(prompts) < n:
            mood, tense = rng.choice(TENSES[language])
            row = (await db.execute(
                select(VerbConjugation).where(
                    VerbConjugation.language == language,
                    VerbConjugation.verb_infinitive == rng.choice(verbs),
                    VerbConjugation.mood == mood,
                    VerbConjugation.tense == tense,
                    VerbConjugation.person == rng.choice(PERSONS),
                )
            )).scalar_one_or_none()
            if row:
                correct, alternates = await target_forms(db, language, row)
                prompts.append((row, correct, alternates))
    return prompts


def tokens_per_second(metrics: dict) -> float | None:
    if metrics.get("eval_count") and metrics.get("eval_duration"):
        return metrics["eval_count"] / (metrics["eval_duration"] / 1e9)
    return None


async def bench_model(model: str, language: Language, prompts) -> dict:
    client = LLMClient(model=model)
    started = time.perf_counter()
    await client.warm_up()
    load_seconds = time.perf_counter() - started

    sentences = []
    for row, correct, alternates in prompts:
        t = time.perf_counter()
        try:
            data = await client.chat_json(build_sentence_messages(language, row, correct), max_tokens=SENTENCE_MAX_TOKENS)
        except Exception:  # noqa: BLE001 — any failure (bad JSON, HTTP) counts as an invalid output
            data = None
        seconds = time.perf_counter() - t
        sentence = str(data.get("sentence", "")) if isinstance(data, dict) else ""
        subject = str(data.get("subject_hint", "")) if isinstance(data, dict) else ""
        valid = bool(sentence) and _sentence_is_valid(sentence, subject, correct, alternates, language, row.person)
        # The app's checks are mechanical; this catches the obvious fragments ("Esta mañana ___")
        complete = len(sentence.replace("_", " ").split()) >= 5 and sentence.rstrip().endswith((".", "!", "?"))
        sentences.append({
            "verb": row.verb_infinitive, "tense": row.tense, "person": row.person, "target": correct,
            "sentence": sentence, "subject": subject, "valid": valid, "complete": complete,
            "seconds": round(seconds, 2), "tokens_per_second": tokens_per_second(client.last_metrics),
        })

    explanations = []
    for row, correct, _ in prompts[:EXPLANATIONS_PER_MODEL]:
        messages = [
            {"role": "system", "content": "You are a language teacher giving clear, encouraging feedback."},
            {"role": "user", "content": (
                f"In {LANGUAGE_NAMES[language]}: in 2-3 sentences, explain why '{correct}' is the correct form "
                f"of '{row.verb_infinitive}' ({row.mood} — {row.tense}, person {row.person}) and when this tense is used."
            )},
        ]
        t = time.perf_counter()
        try:
            text = await client.chat(messages, max_tokens=250)
        except Exception as e:  # noqa: BLE001
            text = f"ERROR: {e}"
        explanations.append({"target": correct, "text": text, "seconds": round(time.perf_counter() - t, 2)})

    secs = [s["seconds"] for s in sentences]
    tps = [s["tokens_per_second"] for s in sentences if s["tokens_per_second"]]
    return {
        "model": model,
        "load_seconds": round(load_seconds, 1),
        "sentence_median_s": round(statistics.median(secs), 2),
        "sentence_p90_s": round(sorted(secs)[int(len(secs) * 0.9) - 1], 2),
        "tokens_per_second": round(statistics.median(tps), 1) if tps else None,
        "valid_rate": round(sum(s["valid"] for s in sentences) / len(sentences), 2),
        "valid_and_complete_rate": round(sum(s["valid"] and s["complete"] for s in sentences) / len(sentences), 2),
        "explanation_median_s": round(statistics.median(e["seconds"] for e in explanations), 2),
        "sentences": sentences,
        "explanations": explanations,
    }


def markdown_table(results: list[dict]) -> str:
    lines = [
        "| Model | Load (s) | Sentence median (s) | Sentence p90 (s) | Tokens/s | Pass app checks | + complete | Explanation median (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['model']} | {r['load_seconds']} | {r['sentence_median_s']} | {r['sentence_p90_s']} | "
            f"{r['tokens_per_second']} | {r['valid_rate']:.0%} | {r['valid_and_complete_rate']:.0%} | {r['explanation_median_s']} |"
        )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--language", default="spanish", choices=[l.value for l in TENSES])
    parser.add_argument("--n", type=int, default=20, help="sentence prompts per model")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", help="write full results (incl. every sentence) as JSON")
    args = parser.parse_args()

    language = Language(args.language)
    prompts = await build_prompts(language, args.n, args.seed)
    results = []
    for model in args.models:
        print(f"… {model}", file=sys.stderr)
        results.append(await bench_model(model, language, prompts))

    print(markdown_table(results))
    for r in results:
        print(f"\n### {r['model']} — sample sentences")
        for s in r["sentences"][:6]:
            print(f"- [{'ok' if s['valid'] else 'REJECTED'}] {s['verb']} / {s['tense']} / {s['person']} → {s['target']}: {s['sentence']}")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
