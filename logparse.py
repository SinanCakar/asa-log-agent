"""Tribe-log line parser and rule engine (pure, dependency-free, unit-testable).

Takes raw OCR text of the ARK in-game tribe log and turns each line into a
structured event. OCR is noisy, so classification keywords are matched fuzzily
(stdlib difflib) before regex extraction. No I/O, no network, no OCR here — this
module is the decision-gate "brain" and is validated headlessly by tests.

Typical ARK tribe-log lines (rich-text tags already stripped):
    Day 12345, 09:14:22: Your 'Metal Wall' was destroyed!
    Day 12345, 09:15:01: Tribemember Bob - Lvl 105 was killed by Alpha Raptor - Lvl 220!
    Day 12345, 10:00:00: Bob was added to the Tribe!
    Day 12345, 12:00:00: Tribemember Bob - Lvl 105 Tamed a Raptor - Lvl 5!
    Day 12345, 12:00:00: Bob demolished a 'Stone Foundation'!
    Day 12345, 13:00:00: A Baby Rex - Lvl 1 has been born!
    Day 12345, 14:00:00: Bob cryo'd 'Rex - Lvl 50'!
    Day 12345, 14:30:00: Bob deployed 'Rex - Lvl 50' from a Cryopod!
    Day 12345, 15:00:00: Bob - Lvl 50 starved to death!
    Day 12345, 16:00:00: Your Tribe allied with 'EnemyTribe'!
    Day 12345, 17:00:00: Bob's 'Rex - Lvl 50' completed 100% Imprint!
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

# --- vocabulary -----------------------------------------------------------
# Action keywords whose presence drives classification. OCR may mangle these,
# so single tokens in the line are fuzzily snapped to this set first.
CATEGORY_KEYWORDS = {
    "raid":     ("destroyed", "demolished", "auto-decay", "auto-destroyed"),
    "kill":     ("killed", "died", "slain", "starved", "drowned"),
    "member":   ("added", "removed", "joined", "left", "promoted", "demoted"),
    "tame":     ("tamed", "hatched", "raised", "imprinted", "born"),
    "claim":    ("claimed", "unclaimed", "uploaded", "downloaded"),
    "cryo":     ("cryo",),      # "cryo'd" and "cryopod" both fuzzy-snap to this
    "alliance": ("allied",),
}
# Flat keyword -> category lookup, plus a vocab list for fuzzy snapping.
_KW_TO_CAT: dict[str, str] = {}
for _cat, _kws in CATEGORY_KEYWORDS.items():
    for _kw in _kws:
        _KW_TO_CAT[_kw] = _cat
_VOCAB = list(_KW_TO_CAT)

# PHRASE triggers (substring match on a normalized line) for multi-word events
# that aren't a single token, e.g. "added to the tribe".
PHRASE_KEYWORDS = {
    "raid": [
        "destroyed", "demolished", "auto-decay", "auto destroyed",
    ],
    "kill": [
        "killed", "slain",
        "starved to death", "drowned",                 # environment deaths
        "was killed by", "tribemember was killed",
    ],
    "member": [
        "added to the tribe", "removed from the tribe",
        "was added", "was removed",
        "left the tribe", "promoted to", "demoted in",
    ],
    "tame": [
        "tamed", "hatched", "raised", "imprint",
        "has been born", "baby",                        # breeding
        "completed imprint", "imprint timer",           # imprint events
        "100 imprint",                                  # "100% Imprint" after _fold
    ],
    "claim":    ["claimed", "unclaimed", "uploaded", "downloaded"],
    "cryo": [
        "cryopod", "cryo d", "deployed from cryopod",  # "cryo'd" folds to "cryo d"
        "from a cryopod", "into cryopod",
    ],
    "alliance": [
        "allied with", "tribe alliance",
        "alliance accepted", "alliance declined",
        "ended their alliance", "alliance has been",
    ],
}


def _fold(text: str) -> str:
    """Lowercase + collapse to single spaces for a tolerant substring match."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


_FOLDED_PHRASES = [(_fold(p), cat) for cat, ps in PHRASE_KEYWORDS.items() for p in ps]

# Severity defaults per category (rule engine baseline; user rules override later).
DEFAULT_SEVERITY = {
    "raid":     "critical",
    "kill":     "high",
    "member":   "medium",
    "tame":     "low",
    "claim":    "medium",
    "cryo":     "low",
    "alliance": "medium",
    "other":    "low",
}

# --- regexes --------------------------------------------------------------
# "Day 12345, 09:14:22:" header. Time may lack seconds (HH:MM) in some logs.
_HEADER_RE = re.compile(r"Day\s+(\d+)\s*,\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*:?\s*", re.IGNORECASE)
# Quoted structure name: 'Metal Wall'  (ASCII or curly quotes from OCR)
_STRUCT_RE = re.compile(r"['‘’\"]([^'‘’\"]{2,40})['‘’\"]")
# "- Lvl 105" level annotation.
_LEVEL_RE = re.compile(r"-\s*Lvl\s*(\d{1,4})", re.IGNORECASE)
# "killed by <name>" / "destroyed by <name>" — captures attacker up to level/paren/end.
_BY_RE = re.compile(r"\bby\s+([A-Za-z0-9 _.'-]{2,40}?)(?=\s*-\s*Lvl|\s*\(|[!.]|$)", re.IGNORECASE)
# Trailing "(Enemy Tribe)" attribution.
_PAREN_RE = re.compile(r"\(([^)]{2,40})\)")


@dataclass(slots=True)
class LogEvent:
    raw: str
    category: str
    severity: str
    day: Optional[int] = None
    time: Optional[str] = None
    structure: Optional[str] = None
    actor: Optional[str] = None        # tribe/own side, when stated
    enemy: Optional[str] = None        # "by <name>" attacker or attributed tribe
    level: Optional[int] = None
    matched_keyword: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _fuzzy_snap_tokens(text: str, threshold: float) -> tuple[str, Optional[str]]:
    """Return (normalized_text, first_matched_keyword).

    Each alphabetic token close enough to a vocab keyword is replaced by that
    keyword, so downstream classification survives OCR noise like
    'destroyel' -> 'destroyed'. Exact hits short-circuit (no false snapping).
    """
    matched: Optional[str] = None
    out: list[str] = []
    for tok in text.split(" "):
        core = tok.strip(".,!:;'\"()").lower()
        if not core or not core.replace("-", "").isalpha():
            out.append(tok)
            continue
        if core in _KW_TO_CAT:
            matched = matched or core
            out.append(tok)
            continue
        near = difflib.get_close_matches(core, _VOCAB, n=1, cutoff=threshold)
        if near:
            kw = near[0]
            matched = matched or kw
            # preserve surrounding punctuation by substituting the core only
            out.append(tok.lower().replace(core, kw))
        else:
            out.append(tok)
    return " ".join(out), matched


def classify(matched_keyword: Optional[str], body: str = "") -> str:
    # 1) token-fuzzy match (English + OCR-mangled single tokens)
    if matched_keyword:
        return _KW_TO_CAT[matched_keyword]
    # 2) bilingual phrase match on the accent-folded line (Turkish multi-word etc.)
    folded = _fold(body)
    for phrase, cat in _FOLDED_PHRASES:
        if phrase in folded:
            return cat
    return "other"


def parse_line(line: str, fuzzy_threshold: float = 0.72) -> Optional[LogEvent]:
    """Parse one tribe-log line into a LogEvent, or None if blank/garbage."""
    line = line.strip()
    if len(line) < 4:
        return None

    day: Optional[int] = None
    tstr: Optional[str] = None
    body = line
    m = _HEADER_RE.match(line)
    if m:
        day = int(m.group(1))
        tstr = m.group(2)
        body = line[m.end():].strip()

    # HARD FILTER: a genuine ARK tribe-log line ALWAYS starts with a
    # "Day N, HH:MM:SS:" header. Requiring it guarantees the agent only ever
    # captures and sends real tribe-log lines — never UI text, chat, server
    # browser, menus, or anything else that happens to be on screen.
    if day is None:
        return None

    normalized, matched = _fuzzy_snap_tokens(body, fuzzy_threshold)
    category = classify(matched, body)

    ev = LogEvent(
        raw=line,
        category=category,
        severity=DEFAULT_SEVERITY[category],
        day=day,
        time=tstr,
        matched_keyword=matched,
    )

    sm = _STRUCT_RE.search(body)
    if sm:
        ev.structure = sm.group(1).strip()

    lm = _LEVEL_RE.search(body)
    if lm:
        ev.level = int(lm.group(1))

    bm = _BY_RE.search(normalized)
    if bm:
        ev.enemy = bm.group(1).strip()
    else:
        pm = _PAREN_RE.search(body)
        if pm:
            ev.enemy = pm.group(1).strip()

    return ev


def parse_text(text: str, fuzzy_threshold: float = 0.72) -> list[LogEvent]:
    """Parse a full OCR block (multi-line) into events, skipping noise."""
    events: list[LogEvent] = []
    for raw in text.splitlines():
        ev = parse_line(raw, fuzzy_threshold)
        if ev is not None:
            events.append(ev)
    return events


# --- user rule engine (structure for the bot side later) ------------------
@dataclass(slots=True)
class Rule:
    pattern: str               # regex (case-insensitive) matched against raw line
    severity: str              # low|medium|high|critical
    _rx: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rx = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, line: str) -> bool:
        return self._rx.search(line) is not None


def apply_rules(event: LogEvent, rules: list[Rule]) -> LogEvent:
    """Override severity with the highest-priority matching user rule."""
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    best = event.severity
    for rule in rules:
        if rule.matches(event.raw) and order.get(rule.severity, -1) > order.get(best, -1):
            best = rule.severity
    event.severity = best
    return event
