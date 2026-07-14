from pbn_client.identifiers import is_valid_object_id, parse_publication_id

VALID = "60a1f2c3d4e5f60718293a4b"  # 24 znaki hex


def test_is_valid_object_id_accepts_24_hex_any_case():
    assert is_valid_object_id(VALID) is True
    assert is_valid_object_id("ABCDEF0123456789abcdef01") is True


def test_is_valid_object_id_rejects_bad_input():
    assert is_valid_object_id("g" * 24) is False  # nie-hex
    assert is_valid_object_id(VALID[:-1]) is False  # za krótki
    assert is_valid_object_id(VALID + "0") is False  # za długi
    assert is_valid_object_id(f" {VALID} ") is False  # spacje
    assert is_valid_object_id(None) is False
    assert is_valid_object_id(123456789012345678901234) is False


def test_parse_publication_id_bare_and_trimmed():
    assert parse_publication_id(VALID) == VALID
    assert parse_publication_id(f"  {VALID}  ") == VALID


def test_parse_publication_id_from_url():
    url = f"https://pbn.nauka.gov.pl/core/#/publication/view/{VALID}/current"
    assert parse_publication_id(url) == VALID


def test_parse_publication_id_from_url_at_end():
    assert parse_publication_id(f"/publication/view/{VALID}") == VALID


def test_parse_publication_id_returns_none_when_unrecognized():
    assert parse_publication_id("to nie jest identyfikator") is None
    assert parse_publication_id("") is None
    assert parse_publication_id(None) is None
