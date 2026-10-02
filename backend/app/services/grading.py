"""Answer grading shared by every practice area: correct, almost, or wrong.

"Almost" means the answer only differs by accents/diacritics (tuvó vs tuvo,
esta vs está, nino vs niño). It's shown kindly but still counts as a mistake.
frontend/src/utils/grading.js mirrors this for the browser-graded verb table.
"""
import unicodedata
from dataclasses import dataclass
from typing import Literal

GradeResult = Literal["correct", "almost", "wrong"]


def normalize(text: str) -> str:
    """Case- and whitespace-insensitive form of an answer."""
    return " ".join(text.split()).lower()


def fold_accents(text: str) -> str:
    """normalize() with diacritics stripped (é→e, ñ→n, ü→u, ç→c)."""
    decomposed = unicodedata.normalize("NFD", normalize(text))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Grade:
    result: GradeResult
    matched: str | None = None  # the accepted form the answer matched (or nearly matched)

    @property
    def is_correct(self) -> bool:
        return self.result == "correct"

    @property
    def is_almost(self) -> bool:
        return self.result == "almost"


def grade(answer: str, accepted: list[str]) -> Grade:
    given = normalize(answer)
    if not given:
        return Grade("wrong")
    for form in accepted:
        if given == normalize(form):
            return Grade("correct", form)
    folded = fold_accents(answer)
    for form in accepted:
        if folded == fold_accents(form):
            return Grade("almost", form)
    return Grade("wrong")
