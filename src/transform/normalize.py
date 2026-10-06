"""Reusable cleaning functions for names and places (task 6)."""

import re
from difflib import SequenceMatcher


def norm_town(name):
    """Standardize a town name so the same town matches across sources."""
    name = name.upper()
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("Ñ", "N")
    name = name.replace("-", " ").replace(".", "").replace("'", "").replace("`", "").replace("’", "")
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^CITY OF ", "", name)
    name = re.sub(r" CITY$", "", name)
    return name



SUFFIX_RE = re.compile(r"\b(?:JR|SR|II|III|IV)\b\.?")


def name_key(name):
    """Compact name for matching: uppercase, no suffix, letters only."""
    name = name.upper().replace("Ñ", "N")
    name = SUFFIX_RE.sub("", name)
    return re.sub(r"[^A-Z]", "", name)


def name_tokens(name):
    """Set of words in a name, for loose first-name matching."""
    if not isinstance(name, str):
        return set()
    name = name.upper().replace("Ñ", "N")
    name = SUFFIX_RE.sub("", name)
    return set(re.findall(r"[A-Z]+", name))


def _fits(small, big):
    """True if every word of `small` appears in `big` (single letters may be initials)."""
    if not small or not big or small[0] != big[0]:
        return False
    for word in small[1:]:
        if len(word) == 1:
            if not any(w.startswith(word) for w in big[1:]):
                return False
        elif word not in big:
            return False
    return True


def first_names_compatible(a, b):
    """True if one first name fits inside the other, e.g. 'Herbert C' and 'Herbert Constantine'."""
    wa = a.upper().replace("Ñ", "N").replace(".", " ").split()
    wb = b.upper().replace("Ñ", "N").replace(".", " ").split()
    return _fits(wa, wb) or _fits(wb, wa)


def middle_names_agree(a, b):
    """True if two middle-name keys match, one extends the other, or they differ only by a typo."""
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.8