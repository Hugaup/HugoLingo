#!/usr/bin/env python3
"""Give new grammar questions an id and lay every topic file out the same way.

Questions are written as [text, answer, [3 wrong options], why]; this turns them
into [id, text, answer, [3 wrong options], why] with the next free id of their
sheet ("2-07" = sheet 2, question 7). Existing ids are never changed (answers are
stored against them). Run from backend/ after editing data/grammar/{language}/:
    python scripts/format_grammar_topics.py spanish
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "grammar"


def dump(topic: dict) -> str:
    head = {k: v for k, v in topic.items() if k not in ("rule", "sheets")}
    lines = ["{"]
    lines.append("  " + json.dumps(head, ensure_ascii=False)[1:-1] + ",")
    lines.append('  "rule": [')
    lines.append(",\n".join("    " + json.dumps(r, ensure_ascii=False) for r in topic["rule"]))
    lines.append("  ],")
    lines.append('  "sheets": [')
    sheets = []
    for sheet in topic["sheets"]:
        title = f'"title": {json.dumps(sheet["title"], ensure_ascii=False)}, ' if sheet.get("title") else ""
        qs = ",\n".join("      " + json.dumps(q, ensure_ascii=False) for q in sheet["questions"])
        sheets.append(f'    {{{title}"questions": [\n{qs}\n    ]}}')
    lines.append(",\n".join(sheets))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(language: str) -> None:
    for path in sorted((DATA / language).glob("*.json")):
        if path.name == "index.json":
            continue
        topic = json.loads(path.read_text(encoding="utf-8"))
        for s, sheet in enumerate(topic["sheets"], 1):
            used = {q[0] for q in sheet["questions"] if len(q) == 5}
            n = 0
            for i, q in enumerate(sheet["questions"]):
                if len(q) == 4:
                    while True:
                        n += 1
                        qid = f"{s}-{n:02d}"
                        if qid not in used and all(qid != o[0] for o in topic["sheets"][s - 1]["questions"] if len(o) == 5):
                            break
                    sheet["questions"][i] = [qid, *q]
                    used.add(qid)
        path.write_text(dump(topic), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "spanish")
