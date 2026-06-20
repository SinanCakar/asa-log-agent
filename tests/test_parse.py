"""Unit tests for logparse — runs without tesseract/OCR.

Covers clean lines (classification + extraction) and fuzzy tolerance against
OCR-style corruption of the action keywords.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logparse as lp  # noqa: E402


def test_header_extraction():
    ev = lp.parse_line("Day 12345, 09:14:22: Your 'Metal Wall' was destroyed!")
    assert ev is not None
    assert ev.day == 12345
    assert ev.time == "09:14:22"
    assert ev.category == "raid"
    assert ev.severity == "critical"
    assert ev.structure == "Metal Wall"


def test_time_without_seconds():
    ev = lp.parse_line("Day 7, 09:14: Bob was added to the Tribe!")
    assert ev.day == 7
    assert ev.time == "09:14"
    assert ev.category == "member"


def test_kill_with_attacker_and_level():
    ev = lp.parse_line(
        "Day 100, 10:00:00: Tribemember Bob - Lvl 105 was killed by Alpha Raptor - Lvl 220!")
    assert ev.category == "kill"
    assert ev.severity == "high"
    assert ev.enemy == "Alpha Raptor"
    assert ev.level == 105  # first level annotation (the victim)


def test_tame():
    ev = lp.parse_line("Day 50, 12:00:00: Tribemember Bob - Lvl 105 Tamed a Raptor - Lvl 5!")
    assert ev.category == "tame"
    assert ev.severity == "low"


def test_demolish_is_raid():
    ev = lp.parse_line("Day 50, 12:00:00: Bob demolished a 'Stone Foundation'!")
    assert ev.category == "raid"
    assert ev.structure == "Stone Foundation"


def test_claim():
    ev = lp.parse_line("Day 50, 12:00:00: Bob claimed 'Raptor'!")
    assert ev.category == "claim"


def test_paren_enemy_attribution():
    ev = lp.parse_line("Day 50, 12:00:00: Your 'Gateway' was destroyed (Red Tribe)!")
    assert ev.category == "raid"
    assert ev.enemy == "Red Tribe"


def test_noise_line_dropped():
    assert lp.parse_line("") is None
    assert lp.parse_line("...") is None
    # No header and no keyword => noise.
    assert lp.parse_line("some random hud text 42%") is None


def test_header_required_drops_non_log_ui_text():
    # Real garbage seen from a full-screen capture: UI/menu text that fuzzy-matched
    # a keyword but has NO "Day N, HH:MM:SS:" header must be DROPPED (send only log).
    assert lp.parse_line("ADD TO FAVORITES REFRESH SORT ORDER") is None
    assert lp.parse_line("1/1 TAME SETTINGS") is None
    assert lp.parse_line("UNCLAIMING CREATURES") is None
    assert lp.parse_line("Any Tribe Member Can Unclaim") is None
    assert lp.parse_line("ge oS added to the Tribe!") is None  # keyword but no header
    # With a proper header it is accepted.
    assert lp.parse_line("Day 4, 16:28:21: Bob was added to the Tribe!").category == "member"


def test_fuzzy_keyword_recovery():
    # OCR corruptions of "destroyed" / "killed" / "Tamed".
    assert lp.parse_line("Day 1, 09:00:00: Your 'Wall' was destroyel!").category == "raid"
    assert lp.parse_line("Day 1, 09:00:00: Bob was kiiled by Rex!").category == "kill"
    # "Taned" (dropped 'm') is closer to "tamed" than any other vocab word.
    assert lp.parse_line("Day 1, 09:00:00: Bob Taned a Raptor!").category == "tame"


def test_fuzzy_does_not_overmatch():
    # A short unrelated word should not snap to a keyword at default threshold.
    ev = lp.parse_line("Day 1, 09:00:00: Bob added to the Tribe!")
    assert ev.category == "member"
    # 'Tribe' must not be misread as an action keyword.
    assert ev.matched_keyword == "added"


def test_parse_text_block_and_dedup_friendly():
    block = (
        "Day 1, 09:00:00: Your 'Wall' was destroyed!\n"
        "garbage line\n"
        "Day 1, 09:01:00: Bob was added to the Tribe!\n"
    )
    events = lp.parse_text(block)
    assert len(events) == 2
    assert [e.category for e in events] == ["raid", "member"]


def test_user_rules_override_severity():
    ev = lp.parse_line("Day 1, 09:00:00: Bob was added to the Tribe!")
    assert ev.severity == "medium"
    rules = [lp.Rule(pattern=r"added to the Tribe", severity="critical")]
    lp.apply_rules(ev, rules)
    assert ev.severity == "critical"


def test_to_dict_drops_none():
    ev = lp.parse_line("Day 1, 09:00:00: Bob was added to the Tribe!")
    d = ev.to_dict()
    assert "structure" not in d
    assert d["category"] == "member"
    assert d["day"] == 1


def test_starvation_and_drowning():
    ev = lp.parse_line("Day 1, 09:00:00: Bob - Lvl 50 starved to death!")
    assert ev is not None
    assert ev.category == "kill"
    assert ev.severity == "high"

    ev2 = lp.parse_line("Day 1, 09:00:00: Bob - Lvl 50 drowned!")
    assert ev2 is not None
    assert ev2.category == "kill"


def test_baby_born():
    ev = lp.parse_line("Day 200, 08:00:00: A Baby Rex - Lvl 1 has been born!")
    assert ev is not None
    assert ev.category == "tame"
    assert ev.severity == "low"


def test_imprint_events():
    ev = lp.parse_line("Day 200, 09:00:00: Bob's 'Rex - Lvl 50' completed 100% Imprint!")
    assert ev is not None
    assert ev.category == "tame"

    ev2 = lp.parse_line("Day 200, 10:00:00: Imprint Timer Expired for Rex - Lvl 50!")
    assert ev2 is not None
    assert ev2.category == "tame"


def test_cryopod_events():
    ev = lp.parse_line("Day 300, 12:00:00: Bob cryo'd 'Rex - Lvl 50'!")
    assert ev is not None
    assert ev.category == "cryo"
    assert ev.severity == "low"

    ev2 = lp.parse_line("Day 300, 12:05:00: Bob deployed 'Rex - Lvl 50' from a Cryopod!")
    assert ev2 is not None
    assert ev2.category == "cryo"


def test_alliance_events():
    ev = lp.parse_line("Day 400, 15:00:00: Your Tribe allied with EnemyTribe!")
    assert ev is not None
    assert ev.category == "alliance"
    assert ev.severity == "medium"

    ev2 = lp.parse_line("Day 400, 15:30:00: Alliance declined with EnemyTribe!")
    assert ev2 is not None
    assert ev2.category == "alliance"


def test_auto_decay():
    ev = lp.parse_line("Day 500, 06:00:00: Your 'Stone Wall' auto-decayed!")
    assert ev is not None
    assert ev.category == "raid"
    assert ev.severity == "critical"


if __name__ == "__main__":
    # stdlib runner so the suite works without pytest installed.
    import traceback

    tests = sorted(
        (n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
