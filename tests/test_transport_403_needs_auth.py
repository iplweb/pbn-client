"""403 z nieważnym tokenem użytkownika -> NeedsPBNAuthorisationException.

PBN zwraca tę odpowiedź raz jako JSON (``{"message": "Forbidden",
"description": "W celu poprawnej autentykacji..."}``), a raz jako goły
tekst. Wersja tekstowa kończyła się generycznym ``HttpException``
("Blad podczas odkodowywania JSON...") z wartością tokena w treści, więc
aplikacja nie mogła pokazać użytkownikowi, że ma się zalogować do PBN.
"""

import json

import pytest

from pbn_client.const import NEEDS_PBN_AUTH_MSG
from pbn_client.exceptions import NeedsPBNAuthorisationException
from pbn_client.transport import RequestsTransport

TEKST_403 = (
    NEEDS_PBN_AUTH_MSG + " Podany token użytkownika abc123 w ramach aplikacji "
    "BPP@TEST nie istnieje lub został unieważniony!"
)

JSON_403 = json.dumps({"message": "Forbidden", "description": TEKST_403})


class _FakeResp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.headers = {}
        self.content = text.encode("utf-8")

    def json(self):
        return json.loads(self.content)


def _transport():
    return RequestsTransport("app", "apptok", "https://pbn.example", "usertok")


@pytest.mark.parametrize("body", [TEKST_403, JSON_403])
def test_post_403_nieprawidlowy_token(monkeypatch, body):
    monkeypatch.setattr(
        "pbn_client.transport.requests.post",
        lambda *a, **kw: _FakeResp(403, body),
    )
    with pytest.raises(NeedsPBNAuthorisationException) as ei:
        _transport().post("/api/v1/repositorium/publications", body=[{}])
    assert ei.value.url == "/api/v1/repositorium/publications"


def test_get_403_nieprawidlowy_token_tekstem(monkeypatch):
    # Wariant JSON dla GET mapuje się (jak dotąd) na AccessDeniedException;
    # tekstowy wywracał się na ``ret.json()``.
    monkeypatch.setattr(
        "pbn_client.transport.requests.get",
        lambda *a, **kw: _FakeResp(403, TEKST_403),
    )
    with pytest.raises(NeedsPBNAuthorisationException):
        _transport().get("/api/v1/publications/id/x")


TOKEN = "c2c8mtmn4iv9ffn33n18plnaqi00thhe"
TEKST_403_Z_TOKENEM = TEKST_403.replace("abc123", TOKEN)


@pytest.mark.parametrize(
    "body",
    [
        TEKST_403_Z_TOKENEM,
        json.dumps({"message": "Forbidden", "description": TEKST_403_Z_TOKENEM}),
        json.dumps(
            {"message": "Forbidden", "description": TEKST_403_Z_TOKENEM},
            ensure_ascii=False,
        ),
    ],
)
def test_403_nie_ujawnia_tokenu_uzytkownika(monkeypatch, body):
    monkeypatch.setattr(
        "pbn_client.transport.requests.post",
        lambda *a, **kw: _FakeResp(403, body),
    )
    with pytest.raises(NeedsPBNAuthorisationException) as ei:
        _transport().post("/api/v1/repositorium/publications", body=[{}])
    assert TOKEN not in str(ei.value)
    assert TOKEN not in str(ei.value.content)
    assert TOKEN[-4:] in str(ei.value.content)


def test_403_nieznany_tekst_nie_ujawnia_tokenu():
    # Awaryjna ścieżka (tekst, ale bez znanego prefiksu) też maskuje token.
    from pbn_client.exceptions import HttpException

    ret = _FakeResp(403, "Inny błąd. Podany token użytkownika " + TOKEN + " zły")
    with pytest.raises(HttpException) as ei:
        _transport()._parse_403_response(ret, "/x")
    assert TOKEN not in str(ei.value)
