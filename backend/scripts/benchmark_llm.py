#!/usr/bin/env python3
"""Compare Ollama models on HugoLingo's real prompts: speed and output validity.

Every model gets the exact same prompts (same verbs, tenses and persons, fixed
seed), built with the app's own code:
  - sentence generation: the real conjugation-exercise prompt (JSON output),
    scored with the app's own validity checks (one clean blank, answer not
    leaked, subject matches the person);
  - short explanations, like the feedback after a sentence check.

With --grammar it instead runs the grammar-exercise pipeline (services/grammar.py)
--n times: how many attempts pass the checks, why the others are rejected, and
the time spent per kept exercise (rejected attempts included).

Run from backend/ with Ollama running and the models pulled:
    source .venv/bin/activate
    python scripts/benchmark_llm.py qwen2.5:7b qwen2.5:3b qwen3:4b --n 20 --out results.json
    python scripts/benchmark_llm.py qwen2.5:7b --grammar --language french --level 2 --n 30
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Language, VerbConjugation
from app.routers.verbs import COMMON_VERBS
from app.services import grammar
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient
from app.services.sentences import (
    COMMON_TENSES, SENTENCE_MAX_TOKENS, assess, build_sentence_messages, judge_sentence, target_forms,
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


async def bench_model(model: str, language: Language, prompts, judge: bool = False) -> dict:
    client = LLMClient(model=model)
    started = time.perf_counter()
    await client.warm_up()
    load_seconds = time.perf_counter() - started

    sentences = []
    async with AsyncSessionLocal() as db:
        for row, correct, alternates in prompts:
            t = time.perf_counter()
            try:
                data = await client.chat_json(build_sentence_messages(language, row, correct), max_tokens=SENTENCE_MAX_TOKENS)
            except Exception:  # noqa: BLE001 — any failure (bad JSON, HTTP) counts as an unusable output
                data = None
            seconds = time.perf_counter() - t
            tps = tokens_per_second(client.last_metrics)
            # The app's own pipeline: server-side blanking + quality checks
            blanked, problem = await assess(db, language, row, correct, alternates, data)
            raw = " ".join(str(data.get("sentence", "")).split()) if isinstance(data, dict) else ""
            approved = None
            if judge and blanked:
                approved = await judge_sentence(client, language, raw)
            sentences.append({
                "verb": row.verb_infinitive, "tense": row.tense, "person": row.person, "target": correct,
                "raw": raw, "sentence": blanked, "usable": blanked is not None, "problem": problem,
                "judge_approved": approved, "seconds": round(seconds, 2), "tokens_per_second": tps,
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
        "usable_rate": round(sum(s["usable"] for s in sentences) / len(sentences), 2),
        "judge_approved_rate": (
            round(sum(bool(s["judge_approved"]) for s in sentences) / len(sentences), 2) if judge else None
        ),
        "explanation_median_s": round(statistics.median(e["seconds"] for e in explanations), 2),
        "sentences": sentences,
        "explanations": explanations,
    }


async def bench_grammar(model: str, language: Language, level: int, n: int, seed: int) -> dict:
    client = LLMClient(model=model)
    await client.warm_up()
    rng = random.Random(seed)
    attempts = []
    async with AsyncSessionLocal() as db:
        for _ in range(n):
            t = time.perf_counter()
            try:
                item, reason = await grammar.generate_one(db, language, level, client, rng)
            except grammar.LLMUnavailable as e:
                sys.exit(f"Ollama unavailable: {e}")
            attempts.append({
                "kept": item is not None, "reason": reason, "seconds": round(time.perf_counter() - t, 2),
                "exercise": asdict(item) if item else None,
            })
    kept = [a for a in attempts if a["kept"]]
    total = sum(a["seconds"] for a in attempts)
    return {
        "model": model,
        "kept_rate": round(len(kept) / n, 2),
        "seconds_per_kept": round(total / len(kept), 1) if kept else None,
        "kept_by_source": dict(Counter(a["exercise"]["source"] for a in kept)),
        "kept_by_type": dict(Counter(a["exercise"]["error_type"] for a in kept)),
        "rejections": dict(Counter(a["reason"] for a in attempts if not a["kept"]).most_common()),
        "attempts": attempts,
    }


def grammar_report(results: list[dict]) -> str:
    lines = [
        "| Model | Kept | Seconds per kept exercise | Rule-made | Model-made |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        src = r["kept_by_source"]
        lines.append(f"| {r['model']} | {r['kept_rate']:.0%} | {r['seconds_per_kept']} | "
                     f"{src.get('rule', 0)} | {src.get('model', 0)} |")
    for r in results:
        lines.append(f"\n### {r['model']}\nRejected: {r['rejections'] or 'none'}\nKept by type: {r['kept_by_type']}\n")
        for a in r["attempts"]:
            if e := a["exercise"]:
                lines.append(f"- [{e['source']}/{e['error_type']}] {e['sentence_with_error']}  →  {e['corrected_sentence']}"
                             f"  ({e['explanation']})")
    return "\n".join(lines)


def markdown_table(results: list[dict]) -> str:
    lines = [
        "| Model | Load (s) | Sentence median (s) | Sentence p90 (s) | Tokens/s | Usable after checks | + judge approved | Explanation median (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['model']} | {r['load_seconds']} | {r['sentence_median_s']} | {r['sentence_p90_s']} | "
            f"{r['tokens_per_second']} | {r['usable_rate']:.0%} | "
            f"{'—' if r['judge_approved_rate'] is None else format(r['judge_approved_rate'], '.0%')} | {r['explanation_median_s']} |"
        )
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--language", default="spanish", choices=[l.value for l in TENSES])
    parser.add_argument("--n", type=int, default=20, help="sentence prompts per model")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", help="write full results (incl. every sentence) as JSON")
    parser.add_argument("--judge", action="store_true", help="also run the LLM grammar judge on usable sentences")
    parser.add_argument("--grammar", action="store_true", help="benchmark grammar-exercise generation instead")
    parser.add_argument("--level", type=int, default=2, help="--grammar: learner level 1-5 (A1-C1)")
    args = parser.parse_args()

    language = Language(args.language)
    if args.grammar:
        results = []
        for model in args.models:
            print(f"… {model}", file=sys.stderr)
            results.append(await bench_grammar(model, language, args.level, args.n, args.seed))
        print(grammar_report(results))
        if args.out:
            Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))
        return

    prompts = await build_prompts(language, args.n, args.seed)
    results = []
    for model in args.models:
        print(f"… {model}", file=sys.stderr)
        results.append(await bench_model(model, language, prompts, judge=args.judge))

    print(markdown_table(results))
    for r in results:
        print(f"\n### {r['model']} — sample sentences")
        for s in r["sentences"][:6]:
            verdict = "ok" if s["usable"] else f"REJECTED: {s['problem']}"
            print(f"- [{verdict}] {s['verb']} / {s['tense']} / {s['person']} → {s['target']}: {s['raw']}")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
