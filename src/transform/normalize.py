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
def fix_mojibake(text):
    """Repair text whose UTF-8 bytes were read as Windows-1252, like the broken enye in some town names."""
    if not isinstance(text, str):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def fix_ocr_digits(name):
    """Fix digits a scanner read instead of letters: 0 next to a letter -> O, 1 before a letter -> I."""
    if not isinstance(name, str):
        return name
    name = re.sub(r"(?<=[A-Z])0|0(?=[A-Z])", "O", name)
    return re.sub(r"1(?=[A-Z])", "I", name)


SPACED_SUFFIX_RE = re.compile(r"\s+(JR|SR|II|III|IV|VI|VII|VIII)\.?$")
GLUED_DOT_SUFFIX_RE = re.compile(r"(?<=[A-Z]{3})(JR|SR)\.$")
GLUED_SUFFIX_RE = re.compile(r"(?<=[A-Z]{3})(JR|SR|III|II|IV)\.?$")
SUFFIX_LABELS = {"JR": "Jr.", "SR": "Sr."}


def split_suffix(name, glued_ok=False):
    """Split trailing suffixes off an uppercase name: 'JOSE JR.' -> ('JOSE', 'Jr.').

    glued_ok=True also splits suffixes written without a space and without a period
    ('ADOLFOJR'); use it only where spaces are known to be missing (2019).
    """
    if not isinstance(name, str):
        return name, None
    name = re.sub(r"\s111$", " III", name.strip())
    found = []
    for _ in range(2):
        m = SPACED_SUFFIX_RE.search(name) or GLUED_DOT_SUFFIX_RE.search(name)
        if not m and glued_ok:
            m = GLUED_SUFFIX_RE.search(name)
        if not m:
            break
        found.insert(0, SUFFIX_LABELS.get(m.group(1), m.group(1)))
        name = name[: m.start()].strip()
    return name, (" ".join(found) if found else None)