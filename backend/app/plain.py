"""Keep visitor facing advice in plain words: no dashes, no stiff hyphenated jargon."""

import re

# Hyphenated or stiff words that read like a template. Order matters (longer first).
_WORDS = [
    (r"\bself-serve\b", "self service"),
    (r"\bstaff-dependent\b", "dependent on staff"),
    (r"\bfollow-ups\b", "follow ups"),
    (r"\bfollow-up\b", "follow up"),
    (r"\bafter-hours\b", "after hours"),
    (r"\blink-in-bio\b", "link in bio"),
    (r"\bone-page\b", "one page"),
    (r"\bcopy-paste\b", "copy and paste"),
    (r"\bhand-offs\b", "handovers"),
    (r"\bhand-off\b", "handover"),
    (r"\bhandoffs\b", "handovers"),
    (r"\bhandoff\b", "handover"),
    (r"\bleverage\b", "use"),
    (r"\butilize\b", "use"),
    (r"\bstreamline\b", "simplify"),
]


def plain(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    # Em and en dashes, and spaced hyphens used as dashes, become commas.
    s = re.sub(r"\s*[—–]\s*", ", ", s)
    s = re.sub(r"\s+-{1,2}\s+", ", ", s)
    for pattern, repl in _WORDS:
        s = re.sub(pattern, lambda m, r=repl: _keep_case(m.group(0), r), s, flags=re.I)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r",\s*\.", ".", s)
    s = re.sub(r"^,\s*", "", s)
    return s


def plain_all(value):
    """Apply plain() to every string inside dicts and lists."""
    if isinstance(value, str):
        return plain(value)
    if isinstance(value, list):
        return [plain_all(v) for v in value]
    if isinstance(value, dict):
        return {k: plain_all(v) for k, v in value.items()}
    return value


def _keep_case(original: str, repl: str) -> str:
    return repl[:1].upper() + repl[1:] if original[:1].isupper() else repl
