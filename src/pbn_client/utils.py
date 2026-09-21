"""Utility functions for PBN API client."""

import re


def mask_secret(value, widocznych=4):
    """Zamaskuj sekret, zostawiając tylko ostatnie ``widocznych`` znaków.

    Do bezpiecznego wypisania tokenów w trybie verbose — sam ogon pozwala
    zidentyfikować token bez ujawniania go w terminalu/CI/logach (uwaga #4).
    """
    if not value:
        return "(brak)"
    s = str(value)
    if len(s) <= widocznych:
        return "*" * len(s)
    return "*" * (len(s) - widocznych) + s[-widocznych:]


def smart_content(content):
    """Decode content to string, handling encoding errors gracefully."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content


# "Podany token użytkownika <TOKEN> w ramach aplikacji..." — komunikat 403
# PBN; "ż" także w postaci ``\u017c`` (JSON z ensure_ascii).
_USER_TOKEN_RE = re.compile(r"(Podany token u(?:ż|\\u017c)ytkownika\s+)([^\s\"\\]+)")


def mask_user_token_in_text(content):
    """Zamaskuj token użytkownika w treści odpowiedzi 403 z PBN.

    Treść trafia do wyjątków, logów i Rollbara — tokenu tam nie chcemy.
    Wartości inne niż ``str`` (niezdekodowane bajty) zwraca bez zmian.
    """
    if not isinstance(content, str):
        return content
    return _USER_TOKEN_RE.sub(lambda m: m.group(1) + mask_secret(m.group(2)), content)
