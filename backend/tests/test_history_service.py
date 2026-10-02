from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.history import (
    MAX_BOX,
    answer_weight,
    current_streak,
    next_review,
    resolve_timezone,
    score_groups,
)

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


# ── Spaced review ────────────────────────────────────────────────────────────

def test_wrong_answer_resets_to_box_zero_and_is_due_now():
    assert next_review(4, False, NOW) == (0, NOW)


def test_right_answers_space_reviews_further_apart():
    box, due_dates = 0, []
    for _ in range(5):
        box, due = next_review(box, True, NOW)
        due_dates.append((due - NOW).days)
    assert due_dates == [1, 3, 7, 14, 30]
    assert box == MAX_BOX


def test_box_is_capped():
    assert next_review(MAX_BOX, True, NOW)[0] == MAX_BOX


# ── Weak-spot scoring ────────────────────────────────────────────────────────

def test_answer_weight_halves_every_two_weeks():
    assert answer_weight(timedelta(0)) == 1
    assert answer_weight(timedelta(days=14)) == pytest.approx(0.5)
    assert answer_weight(timedelta(days=28)) == pytest.approx(0.25)


def test_a_fresh_mistake_is_flagged():
    [g] = score_groups([("tener", False, NOW)], NOW)
    assert g["key"] == "tener"
    assert (g["attempts"], g["mistakes"]) == (1, 1)
    assert g["weakness"] == pytest.approx(1 / 3, abs=1e-3)
    assert g["last_mistake_at"] == NOW


def test_a_mistake_followed_by_many_right_answers_is_no_longer_weak():
    rows = [("tener", False, NOW - timedelta(hours=1))] + [("tener", True, NOW)] * 9
    assert score_groups(rows, NOW) == []


def test_old_mistakes_fade_away():
    assert score_groups([("tener", False, NOW - timedelta(days=90))], NOW) == []


def test_repeated_mistakes_rank_above_a_single_slip():
    rows = [
        ("hablar", False, NOW),
        ("tener", False, NOW), ("tener", False, NOW), ("tener", True, NOW), ("tener", False, NOW),
    ]
    ranked = score_groups(rows, NOW)
    assert [g["key"] for g in ranked] == ["tener", "hablar"]


def test_recent_mistakes_outweigh_old_ones():
    rows = [
        ("old", False, NOW - timedelta(days=30)), ("old", False, NOW - timedelta(days=30)),
        ("new", False, NOW), ("new", False, NOW),
    ]
    ranked = score_groups(rows, NOW)
    assert ranked[0]["key"] == "new"
    assert ranked[0]["weakness"] > ranked[1]["weakness"]


# ── Streaks, normalisation, timezones ────────────────────────────────────────

TODAY = date(2026, 10, 2)


@pytest.mark.parametrize("active,expected", [
    (set(), 0),
    ({TODAY}, 1),
    ({TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)}, 3),
    # Not practised yet today: yesterday's streak is still alive
    ({TODAY - timedelta(days=1), TODAY - timedelta(days=2)}, 2),
    # A missed day breaks it
    ({TODAY, TODAY - timedelta(days=2)}, 1),
    ({TODAY - timedelta(days=2)}, 0),
])
def test_current_streak(active, expected):
    assert current_streak(active, TODAY) == expected


def test_unknown_timezone_falls_back_to_utc():
    assert resolve_timezone("Europe/Paris") == "Europe/Paris"
    assert resolve_timezone("Mars/Olympus") == "UTC"
    assert resolve_timezone("../etc/passwd") == "UTC"
