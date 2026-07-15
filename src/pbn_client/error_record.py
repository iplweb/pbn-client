"""Zunifikowany, wersjonowany kontrakt błędów PBN (``ErrorRecord``).

Odpowiedzi błędów PBN historycznie krążyły po aplikacjach-hostach jako surowe
stringi (tuple-repr ``HttpException``, tracebacki, JSON-y) parsowane w wielu
miejscach różną, kruchą logiką. Ten moduł centralizuje interpretację w jednej
**totalnej** funkcji :func:`parse` (NIGDY nie rzuca) zwracającej
:class:`ErrorRecord`, oraz w :func:`serialize` produkującej stabilny,
wersjonowany format v1 (jednoliniowy JSON) do trwałego zapisu.

Moduł jest czysty (bez zależności od Django). ``parse()`` rozpoznaje formaty
legacy ORAZ v1 — co pozwala hostowi wdrożyć odczyt v1 (reader-first) zanim
zacznie go zapisywać, unikając deploy-race.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

from pbn_client.exceptions import parse_pbn_validation_details

#: Ścieżki importu wyjątków PBN rozpoznawane w liniach tracebacku (legacy
#: ``pbn_api.exceptions`` oraz ten pakiet ``pbn_client.exceptions``).
PBN_EXCEPTION_MODULES = ("pbn_api.exceptions", "pbn_client.exceptions")

# Limity rozmiaru serializacji v1. Suma wszystkich capów + narzut JSON jest
# < 40k, więc blob v1 jest DOWODLIWIE < 65535 (typowy limit pola TextField
# hosta, np. ``SentData.exception``); patrz :func:`serialize`.
_CAP_CONTENT = 10_000
_CAP_TRACEBACK = 20_000
_CAP_MESSAGE = 2_000
_CAP_URL = 512
_CAP_EXCEPTION_CLASS = 512
_CAP_SOURCE = 128
_CAP_BLOB = 60_000

# Wyjątki „katastroficzne" łapane przy parsowaniu niezaufanych stringów, żeby
# parse() pozostało totalne: RecursionError (głęboko zagnieżdżony JSON),
# MemoryError (ogromny literał), OverflowError (int() z 1e999).
_PARSE_GUARD = (ValueError, TypeError, RecursionError, MemoryError, OverflowError)


@dataclass(frozen=True)
class ErrorRecord:
    """Znormalizowana reprezentacja pojedynczego błędu PBN.

    Niesie zarówno pola strukturalne (``status_code``, ``content_json``…),
    jak i werbatimowe fragmenty (``exception_line``, ``fallback_line``)
    potrzebne adapterom hosta do odtworzenia dokładnie tego samego outputu co
    przed unifikacją. ``wire`` mówi skąd rekord pochodzi (``v1`` / ``legacy`` /
    ``empty``); ``content_json_valid`` odróżnia poprawny JSON ``null`` od
    niepoprawnego body (oba dają ``content_json is None``).
    """

    kind: str = "generic"  # "http" | "generic"
    wire: str = "legacy"  # "v1" | "legacy" | "empty"
    source: str | None = None  # "sentdata" | "queue" | None
    exception_class: str | None = None  # pełna nazwa (moduł.Klasa)
    exception_type: str | None = None  # krótka nazwa (ostatni segment)
    status_code: int | None = None
    url: str | None = None
    content: str | None = None  # surowy body odpowiedzi PBN
    content_json: object = None  # sparsowany content (dict/list/scalar/None)
    content_json_valid: bool = False  # czy content był poprawnym JSON-em
    message: str | None = None
    traceback: str | None = None
    exception_line: str | None = None  # werbatim linia „moduł.Klasa: …"
    fallback_line: str = ""  # ostatnia niepusta linia surowego wejścia
    raw: str = ""
    is_pbn_api_error: bool = False
    truncated: bool = False

    @property
    def messages(self) -> list:
        """Odduplikowane komunikaty walidacyjne PBN z ``content_json``."""
        return parse_pbn_validation_details(self.content_json) or []


# --------------------------------------------------------------------------
# Parsowanie (totalne — NIGDY nie rzuca)
# --------------------------------------------------------------------------


def _last_nonempty_line(text: str) -> str:
    lines = [line for line in text.strip().split("\n") if line.strip()]
    return lines[-1].strip() if lines else ""


def _extract_pbn_line(text: str) -> str | None:
    """Ostatnia linia zawierająca ścieżkę wyjątku PBN, albo ``None``."""
    lines = [line for line in text.strip().split("\n") if line.strip()]
    for line in reversed(lines):
        if any(module in line for module in PBN_EXCEPTION_MODULES):
            return line.strip()
    return None


def _parse_json(content):
    """Zwróć ``(value, is_valid)``. ``is_valid`` False, gdy ``content`` nie jest
    poprawnym JSON-em — odróżnia to poprawny ``null`` (``(None, True)``) od
    błędu parsowania (``(None, False)``)."""
    if not isinstance(content, str):
        return None, False
    try:
        return json.loads(content), True
    except _PARSE_GUARD:
        return None, False


def _try_tuple(text: str):
    """Zwróć ``(status_code:int, url, content)`` z tuple-repr, albo ``None``.

    Odtwarza semantykę legacy: kod musi dać się rzutować na ``int`` (inaczej
    traktujemy string jako nie-krotkę, jak stare ``_parse_error_tuple``).
    """
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, *_PARSE_GUARD):
        return None
    if not (isinstance(value, tuple) and len(value) >= 3):
        return None
    try:
        status_code = int(value[0])
    except _PARSE_GUARD:
        return None
    return status_code, value[1], value[2]


def _http_from_tuple(
    tup,
    *,
    raw,
    exception_class,
    exception_type,
    traceback,
    exception_line,
    fallback_line,
) -> ErrorRecord:
    status_code, url, content = tup
    content_json, valid = _parse_json(content)
    return ErrorRecord(
        kind="http",
        wire="legacy",
        is_pbn_api_error=True,
        exception_class=exception_class,
        exception_type=exception_type,
        status_code=status_code,
        url=url if isinstance(url, str) else (str(url) if url is not None else None),
        content=content if isinstance(content, str) else None,
        content_json=content_json,
        content_json_valid=valid,
        traceback=traceback,
        exception_line=exception_line,
        fallback_line=fallback_line,
        raw=raw,
    )


def _parse_prefixed(line: str, *, raw, traceback, fallback_line) -> ErrorRecord:
    """Parsuj linię ``moduł.Klasa: reszta`` (z tracebacku lub pojedynczą)."""
    if ":" not in line:
        # Linia z modułem PBN, ale bez ``:`` (wyjątek rzucony bez argumentów) —
        # cała linia jest „komunikatem", brak wyłuskanej klasy z ``:``.
        exception_class = line.strip()
        exception_type = exception_class.split(".")[-1] or None
        return ErrorRecord(
            kind="generic",
            wire="legacy",
            is_pbn_api_error=True,
            exception_class=exception_class,
            exception_type=exception_type,
            message=line.strip(),
            raw=raw,
            traceback=traceback,
            exception_line=line,
            fallback_line=fallback_line,
        )
    before, _, after = line.partition(":")
    exception_class = before.strip()
    exception_type = exception_class.split(".")[-1] or None
    rest = after.strip()

    tup = _try_tuple(rest)
    if tup is not None:
        return _http_from_tuple(
            tup,
            raw=raw,
            exception_class=exception_class,
            exception_type=exception_type,
            traceback=traceback,
            exception_line=line,
            fallback_line=fallback_line,
        )

    # Prosty wyjątek (np. StatementsMissing) — brak krotki HTTP.
    return ErrorRecord(
        kind="generic",
        wire="legacy",
        is_pbn_api_error=True,
        exception_class=exception_class,
        exception_type=exception_type,
        message=rest,
        traceback=traceback,
        exception_line=line,
        fallback_line=fallback_line,
        raw=raw,
    )


def _try_v1(text: str) -> ErrorRecord | None:
    """Rozpoznaj nowy format v1. Oba markery (``v==1`` int, znany ``kind``)
    są wymagane — chroni przed kolizją z legacy payloadem, który przypadkiem
    jest dict-em."""
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        data = json.loads(stripped)
    except _PARSE_GUARD:
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("v")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        return None
    kind = data.get("kind")
    if kind not in ("http", "generic"):
        return None

    content = data.get("content")
    content_json, valid = _parse_json(content)
    exception_class = data.get("exception_class")
    exception_type = None
    if isinstance(exception_class, str) and exception_class:
        exception_type = exception_class.split(".")[-1] or None
    status_code = data.get("status_code")
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        status_code = None
    return ErrorRecord(
        kind=kind,
        wire="v1",
        source=data.get("source"),
        exception_class=exception_class,
        exception_type=exception_type,
        status_code=status_code,
        url=data.get("url"),
        content=content if isinstance(content, str) else None,
        content_json=content_json,
        content_json_valid=valid,
        message=data.get("message"),
        traceback=data.get("traceback"),
        raw=text,
        is_pbn_api_error=(kind == "http"),
        truncated=bool(data.get("truncated", False)),
        fallback_line=_last_nonempty_line(text),
    )


def parse(stored) -> ErrorRecord:
    """Zparsuj surowy string błędu do :class:`ErrorRecord`. NIGDY nie rzuca.

    Kolejność rozpoznania (pierwsze trafienie wygrywa): pusty → v1 →
    linia/traceback z prefiksem PBN → goła krotka → plaintext.
    """
    if stored is None:
        return ErrorRecord(wire="empty", raw="", fallback_line="")
    text = stored if isinstance(stored, str) else str(stored)
    if not text.strip():
        return ErrorRecord(wire="empty", raw=text, fallback_line="")

    v1 = _try_v1(text)
    if v1 is not None:
        return v1

    fallback_line = _last_nonempty_line(text)
    pbn_line = _extract_pbn_line(text)
    if pbn_line is not None:
        is_traceback = pbn_line != text.strip()
        return _parse_prefixed(
            pbn_line,
            raw=text,
            traceback=text if is_traceback else None,
            fallback_line=fallback_line,
        )

    tup = _try_tuple(text.strip())
    if tup is not None:
        return _http_from_tuple(
            tup,
            raw=text,
            exception_class=None,
            exception_type=None,
            traceback=None,
            exception_line=None,
            fallback_line=fallback_line,
        )

    return ErrorRecord(
        kind="generic",
        wire="legacy",
        is_pbn_api_error=False,
        raw=text,
        fallback_line=fallback_line,
    )


# --------------------------------------------------------------------------
# Serializacja v1
# --------------------------------------------------------------------------


def _cap(value, limit, *, tail=False):
    if isinstance(value, str) and len(value) > limit:
        return (value[-limit:] if tail else value[:limit]), True
    return value, False


def serialize(rec: ErrorRecord) -> str:
    """Zserializuj :class:`ErrorRecord` do jednoliniowego v1 JSON.

    Każde pole-string jest capowane, więc rozmiar blobu jest DOWODLIWIE
    ograniczony sumą capów (< 40k) niezależnie od wrogiego wejścia — blob
    zawsze mieści się w polach ``TextField(max_length=65535)`` hosta.
    """
    content, t1 = _cap(rec.content, _CAP_CONTENT)
    traceback, t2 = _cap(rec.traceback, _CAP_TRACEBACK, tail=True)
    message, t3 = _cap(rec.message, _CAP_MESSAGE)
    url, t4 = _cap(rec.url, _CAP_URL)
    exception_class, t5 = _cap(rec.exception_class, _CAP_EXCEPTION_CLASS)
    source, t6 = _cap(rec.source, _CAP_SOURCE)
    truncated = any((t1, t2, t3, t4, t5, t6)) or rec.truncated

    data = {
        "v": 1,
        "kind": rec.kind,
        "source": source,
        "exception_class": exception_class,
        "status_code": rec.status_code,
        "url": url,
        "content": content,
        "message": message,
        "traceback": traceback,
        "truncated": truncated,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
