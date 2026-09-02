# -*- coding: utf-8 -*-
"""גרסת המערכת. התג ב-GitHub חייב להיות זהה לה - הבנייה מוודאת את זה."""

VERSION = "1.1.0"
REPO = "tsoolgee/bell-system"
ASSET = "BellSystem.exe"


def as_tuple(text):
    """'1.2.3' -> (1, 2, 3). חלקים לא מספריים נספרים כאפס."""
    parts = []
    for chunk in str(text or "").lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(candidate, current=VERSION):
    return as_tuple(candidate) > as_tuple(current)
