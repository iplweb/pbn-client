"""Rozpoznawanie i parsowanie identyfikatorów obiektów PBN.

Identyfikator obiektu PBN (``objectId``, historycznie „mongoId") to 24-znakowy
ciąg heksadecymalny. Publikacje bywają też podawane jako URL PBN postaci
``.../publication/view/<objectId>``.
"""

import re

_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")
_PUBLICATION_URL_RE = re.compile(r"/publication/view/([0-9a-fA-F]{24})(?:/|$)")


def is_valid_object_id(value):
    """Zwraca ``True``, gdy ``value`` to 24-znakowy heksadecymalny objectId PBN."""
    if not isinstance(value, str):
        return False
    return bool(_OBJECT_ID_RE.match(value))


def parse_publication_id(value):
    """Wyłuskuje objectId publikacji z surowego identyfikatora lub URL-a PBN.

    Przyjmuje goły 24-znakowy objectId albo URL ``.../publication/view/<id>``.
    Zwraca objectId albo ``None``, gdy nic rozpoznawalnego nie znaleziono.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if _OBJECT_ID_RE.match(candidate):
        return candidate
    match = _PUBLICATION_URL_RE.search(candidate)
    if match:
        return match.group(1)
    return None
