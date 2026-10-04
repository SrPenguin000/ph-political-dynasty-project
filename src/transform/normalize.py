"""Reusable cleaning functions for names and places (task 6)."""

import re


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
    name = name.upper().replace("Ñ", "N")
    name = SUFFIX_RE.sub("", name)
    return set(re.findall(r"[A-Z]+", name))