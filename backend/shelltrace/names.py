import re

import jellyfish
from unidecode import unidecode


SUFFIXES = {
    "ltd", "limited", "llc", "llp", "inc", "incorporated", "corp", "corporation", "sa", "sarl", "gmbh",
    "ag", "bv", "nv", "plc", "pjsc", "jsc", "ooo", "ao", "fze", "as", "co", "company", "holdings", "holding",
    "trading", "trdg", "group", "trust", "foundation", "ventures", "capital", "international", "intl",
    "services", "nominees", "partners",
}


def norm(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", unidecode(name or "").lower()).split())


def core(name: str) -> str:
    normalized = norm(name)
    tokens = [token for token in normalized.split() if token not in SUFFIXES]
    return "".join(tokens) if tokens else normalized.replace(" ", "")


def phon(name: str) -> str:
    value = core(name)
    return jellyfish.metaphone(value) if value else ""
