"""Testy jednostkowe modułu ``pbn_api.error_record`` (P4 Stage 1).

``parse()`` MUSI być totalne (nigdy nie rzuca) i rozpoznawać legacy ORAZ
nowy format v1. ``serialize()`` produkuje v1 z limitami rozmiaru.
"""

import json

import pytest

from pbn_client.error_record import ErrorRecord, parse, serialize

TUPLE_DICT = (
    "(400, '/api/v1/publications', "
    '\'{"code":400,"message":"Bad Request","description":"Boom",'
    '"details":{"isbn":"ISBN zajęty"}}\')'
)
PREFIX_HTTP = "pbn_api.exceptions.HttpException: " + TUPLE_DICT
PREFIX_VALIDATION = (
    "pbn_client.exceptions.PBNValidationError: "
    '(400, \'/api/v1/publications\', \'{"details":{"doi":"Duplicate"}}\')'
)
TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/app/x.py", line 1, in f\n' + PREFIX_HTTP + "\n"
)


# --- totalność: parse() nigdy nie rzuca ---------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "plain text",
        "(1, 2)",  # krotka za krótka
        "(niepoprawna",  # niedomknięta
        '{"v": 1}',  # v1 bez kind
        '{"v": 1, "kind": "http"}',
        '{"v": "1", "kind": "http"}',  # v jako string, nie int
        '{"broken json',
        "(400, '/x', '{niepoprawny json}')",
        "\x00\x01\x02 binarne",
        "(400, '/x', '" + "A" * 5000 + "')",  # długi payload
        "pbn_api.exceptions.Foo: " + "B" * 2000,  # długi message
        "😀 emoji 💥",
        "[]",
        "{}",
        "null",
        "42",
        # --- regresje totalności (recenzje Fable) ---
        "(1e999, '/x', '{}')",  # OverflowError: int(inf)
        "pbn_api.exceptions.HttpException: (1e999, '/x', '{}')",
        "(400, '/x', '" + "[" * 20000 + "]" * 20000 + "')",  # RecursionError
        "{" + '"a":' * 20000 + "1" + "}" * 20000,  # głęboki dict jako całość
    ],
)
def test_parse_never_raises(value):
    rec = parse(value)
    assert isinstance(rec, ErrorRecord)


def test_parse_deep_json_content_does_not_raise():
    # Głęboko zagnieżdżone body z wrogiej odpowiedzi PBN. Na CPythonie <3.14
    # json.loads rzuca RecursionError (→ content_json None, valid False); 3.14+
    # parsuje głębiej bez błędu. W OBU przypadkach parse() musi pozostać totalne
    # i rozpoznać krotkę (kod/URL) niezależnie od głębi body.
    deep = "(400, '/x', '" + "[" * 30000 + "]" * 30000 + "')"
    rec = parse(deep)
    assert isinstance(rec, ErrorRecord)
    assert rec.status_code == 400
    assert rec.url == "/x"
    # content_json zależny od wersji interpretera: None (RecursionError) albo
    # sparsowana lista — ale content_json_valid odzwierciedla to spójnie.
    assert rec.content_json_valid is (rec.content_json is not None)


def test_parse_overflow_status_code_falls_through():
    rec = parse("(1e999, '/x', '{}')")
    # int(1e999) rzuca OverflowError → nie-krotka → plaintext, bez wyjątku.
    assert rec.kind == "generic"
    assert rec.status_code is None


def test_parse_none_and_blank():
    for v in (None, "", "   "):
        rec = parse(v)
        assert rec.kind == "generic"
        assert rec.is_pbn_api_error is False
        assert rec.status_code is None


def test_parse_bare_tuple_http():
    rec = parse(TUPLE_DICT)
    assert rec.kind == "http"
    assert rec.is_pbn_api_error is True
    assert rec.status_code == 400
    assert rec.url == "/api/v1/publications"
    assert isinstance(rec.content_json, dict)
    assert rec.content_json["details"] == {"isbn": "ISBN zajęty"}


def test_parse_prefixed_line_captures_class():
    rec = parse(PREFIX_HTTP)
    assert rec.kind == "http"
    assert rec.exception_class == "pbn_api.exceptions.HttpException"
    assert rec.exception_type == "HttpException"
    assert rec.status_code == 400
    # verbatim linia do rekonstrukcji przez extract_pbn_error_from_komunikat
    assert rec.exception_line == PREFIX_HTTP


def test_parse_traceback_extracts_pbn_line():
    rec = parse(TRACEBACK)
    assert rec.kind == "http"
    assert rec.status_code == 400
    assert rec.traceback == TRACEBACK
    assert rec.exception_line == PREFIX_HTTP


def test_parse_simple_exception_generic():
    rec = parse("pbn_api.exceptions.StatementsMissing: czegoś brakuje")
    assert rec.kind == "generic"
    assert rec.is_pbn_api_error is True
    assert rec.exception_type == "StatementsMissing"
    assert rec.message == "czegoś brakuje"


def test_parse_plaintext_fallback():
    rec = parse("zwykły błąd")
    assert rec.kind == "generic"
    assert rec.is_pbn_api_error is False
    assert rec.raw == "zwykły błąd"


def test_parse_validation_messages():
    rec = parse(PREFIX_VALIDATION)
    assert rec.messages == ["Duplicate"]


# --- brak kolizji legacy <-> v1 -----------------------------------------


def test_parse_legacy_dict_without_v_is_not_v1():
    # Payload który przypadkiem jest dict-em, ale bez markera v==1 —
    # NIE może być rozpoznany jako v1 (musi iść ścieżką legacy/plaintext).
    rec = parse('{"status_code": 400, "kind": "http"}')
    assert rec.raw == '{"status_code": 400, "kind": "http"}'
    # nie „awansowany" na strukturę http z markerów, bo brak v==1
    assert rec.exception_class is None


def test_parse_v1_requires_int_v_and_known_kind():
    assert parse('{"v": 1, "kind": "http", "status_code": 500}').status_code == 500
    # zły kind → nie v1
    bad = parse('{"v": 1, "kind": "banana"}')
    assert bad.status_code is None


# --- v1 detekcja + round-trip -------------------------------------------


def test_parse_v1_blob():
    blob = json.dumps(
        {
            "v": 1,
            "kind": "http",
            "source": "sentdata",
            "exception_class": "pbn_client.exceptions.PBNValidationError",
            "status_code": 422,
            "url": "/api/v1/x",
            "content": '{"details":{"a":"b"}}',
            "message": "msg",
            "traceback": None,
        }
    )
    rec = parse(blob)
    assert rec.kind == "http"
    assert rec.status_code == 422
    assert rec.url == "/api/v1/x"
    assert rec.exception_class == "pbn_client.exceptions.PBNValidationError"
    assert rec.content_json == {"details": {"a": "b"}}
    assert rec.messages == ["b"]


def test_serialize_is_single_line_v1_json():
    rec = parse(PREFIX_HTTP)
    blob = serialize(rec)
    assert "\n" not in blob
    data = json.loads(blob)
    assert data["v"] == 1
    assert data["kind"] == "http"


def test_serialize_round_trip_preserves_core_fields():
    rec = parse(PREFIX_HTTP)
    rec2 = parse(serialize(rec))
    assert rec2.kind == rec.kind
    assert rec2.status_code == rec.status_code
    assert rec2.url == rec.url
    assert rec2.exception_class == rec.exception_class
    assert rec2.content_json == rec.content_json


def test_serialize_enforces_size_caps():
    huge = "(400, '/x', '" + "A" * 50000 + "')"
    rec = parse(huge)
    blob = serialize(rec)
    assert len(blob) <= 60000
    data = json.loads(blob)
    assert data["truncated"] is True
    assert len(data["content"]) <= 10000


def test_serialize_bounded_on_huge_exception_class_and_source():
    # Finding 2 (recenzja Fable): limit MUSI obejmować też exception_class i
    # source, inaczej blob mógłby przekroczyć 65535 pola SentData.exception.
    from dataclasses import replace

    rec = replace(
        parse(PREFIX_HTTP),
        exception_class="X" * 200_000,
        source="S" * 200_000,
    )
    blob = serialize(rec)
    assert len(blob) <= 65535
    data = json.loads(blob)
    assert data["truncated"] is True
    assert len(data["exception_class"]) <= 512
    assert len(data["source"]) <= 128


# --- wire (v1 / legacy / empty) + ważność content_json ------------------


def test_wire_field_distinguishes_provenance():
    assert parse(None).wire == "empty"
    assert parse("").wire == "empty"
    assert parse(TUPLE_DICT).wire == "legacy"
    assert parse(PREFIX_HTTP).wire == "legacy"
    assert parse("zwykły tekst").wire == "legacy"
    v1 = serialize(parse(PREFIX_HTTP))
    assert parse(v1).wire == "v1"


def test_content_json_valid_distinguishes_null_from_invalid():
    # poprawny JSON null → (None, valid=True)
    rec_null = parse("(400, '/x', 'null')")
    assert rec_null.content_json is None
    assert rec_null.content_json_valid is True
    # niepoprawny JSON → (None, valid=False)
    rec_bad = parse("(400, '/x', '{nie-json}')")
    assert rec_bad.content_json is None
    assert rec_bad.content_json_valid is False
    # poprawny dict → valid=True
    rec_ok = parse(TUPLE_DICT)
    assert rec_ok.content_json_valid is True
