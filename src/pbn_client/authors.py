"""Normalizacja danych osobowych autora z niespójnych JSON-ów PBN."""

#: Klucze imienia w kolejności preferencji (unia wariantów spotykanych w PBN).
_FIRST_NAME_KEYS = ("firstName", "givenNames", "name")

#: Klucze nazwiska w kolejności preferencji.
_LAST_NAME_KEYS = ("familyName", "lastName")


def _first_present(data, keys):
    """Zwróć pierwszą niepustą wartość spod ``keys`` w ``data`` (albo None)."""
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return None


def normalize_author_name(author):
    """Sprowadź autora z PBN do ``{"lastName": ..., "firstName": ...}``.

    PBN podaje dane osobowe niespójnie, zależnie od endpointu: nazwisko
    jako ``lastName`` albo ``familyName``, imię jako ``firstName``,
    ``givenNames`` albo ``name``. Czasem zamiast słownika przychodzi
    goły PBN UID (string) — wtedy nie mamy danych osobowych.

    Kolejność preferencji:

    - ``lastName``: ``familyName`` → ``lastName`` → ``None``
    - ``firstName``: ``firstName`` → ``givenNames`` → ``name`` → ``None``

    Puste stringi traktowane są jak brak wartości. Wejście inne niż dict
    (None, string-UID, cokolwiek) daje oba pola ``None``.
    """
    if not isinstance(author, dict):
        return {"lastName": None, "firstName": None}
    return {
        "lastName": _first_present(author, _LAST_NAME_KEYS),
        "firstName": _first_present(author, _FIRST_NAME_KEYS),
    }
