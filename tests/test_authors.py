"""Testy normalizacji autora z niespójnych JSON-ów PBN.

PBN podaje nazwisko raz jako ``lastName``, raz jako ``familyName``,
a imię jako ``firstName``, ``givenNames`` albo ``name`` — w zależności
od endpointu. ``normalize_author_name`` sprowadza wszystkie warianty
do jednego kształtu ``{"lastName": ..., "firstName": ...}``.
"""

import pytest

from pbn_client import normalize_author_name


def test_firstname_lastname_payload():
    assert normalize_author_name({"firstName": "Jan", "lastName": "Kowalski"}) == {
        "lastName": "Kowalski",
        "firstName": "Jan",
    }


def test_familyname_givennames_payload():
    assert normalize_author_name(
        {"familyName": "Nowak", "givenNames": "Anna Maria"}
    ) == {"lastName": "Nowak", "firstName": "Anna Maria"}


def test_name_only_payload():
    assert normalize_author_name({"name": "Zofia"}) == {
        "lastName": None,
        "firstName": "Zofia",
    }


def test_givennames_only_payload():
    assert normalize_author_name({"givenNames": "Piotr"}) == {
        "lastName": None,
        "firstName": "Piotr",
    }


def test_lastname_only_payload():
    assert normalize_author_name({"lastName": "Wiśniewska"}) == {
        "lastName": "Wiśniewska",
        "firstName": None,
    }


def test_missing_everything():
    assert normalize_author_name({}) == {"lastName": None, "firstName": None}


def test_irrelevant_keys_only():
    assert normalize_author_name({"orcid": "0000-0001-2345-6789"}) == {
        "lastName": None,
        "firstName": None,
    }


@pytest.mark.parametrize("value", [None, "5e70930d878c28a04b8efd23", 42, ["x"]])
def test_non_dict_input(value):
    assert normalize_author_name(value) == {"lastName": None, "firstName": None}


def test_union_familyname_wins_over_lastname():
    assert normalize_author_name({"familyName": "Wolski", "lastName": "Kowalski"}) == {
        "lastName": "Wolski",
        "firstName": None,
    }


def test_union_firstname_wins_over_givennames_and_name():
    assert normalize_author_name(
        {"firstName": "Jan", "givenNames": "Janusz", "name": "Jasiek"}
    ) == {"lastName": None, "firstName": "Jan"}


def test_union_givennames_wins_over_name():
    assert normalize_author_name({"givenNames": "Ewa", "name": "Ewelina"}) == {
        "lastName": None,
        "firstName": "Ewa",
    }


def test_empty_string_values_fall_through():
    # PBN potrafi przysłać puste stringi — traktujemy je jak brak wartości.
    assert normalize_author_name(
        {"firstName": "", "givenNames": "Adam", "lastName": "", "familyName": ""}
    ) == {"lastName": None, "firstName": "Adam"}
