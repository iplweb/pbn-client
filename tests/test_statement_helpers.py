"""Testy publicznych helperów oświadczeń (``StatementsMixin`` + moduł)."""

import pytest

from pbn_client.statements import StatementsMixin, decode_publication_object_id

# ---------------------------- klucze porównania ----------------------------


def test_statement_key_pbn_stringifies_fields():
    assert StatementsMixin.statement_key_pbn({"personId": "abc", "area": 301}) == (
        "abc",
        "301",
    )


def test_statement_key_pbn_missing_fields_default_to_empty_string():
    assert StatementsMixin.statement_key_pbn({}) == ("", "")


def test_statement_key_intended_stringifies_fields():
    assert StatementsMixin.statement_key_intended(
        {"personObjectId": "abc", "disciplineId": 301}
    ) == ("abc", "301")


def test_statement_key_intended_missing_fields_default_to_empty_string():
    assert StatementsMixin.statement_key_intended({}) == ("", "")


# ------------------------------ diff zestawów ------------------------------


def test_diff_statements_returns_only_in_pbn_and_only_in_intended():
    mixin = StatementsMixin()
    pbn_statements = [
        {"personId": "p1", "area": 301},
        {"personId": "p2", "area": "302"},
    ]
    intended_statements = [
        {"personObjectId": "p2", "disciplineId": 302},
        {"personObjectId": "p3", "disciplineId": "303"},
    ]

    only_in_pbn, only_in_intended = mixin.diff_statements(
        pbn_statements, intended_statements
    )

    assert only_in_pbn == {("p1", "301")}
    assert only_in_intended == {("p3", "303")}


def test_diff_statements_identical_sets_yield_empty_diffs():
    mixin = StatementsMixin()
    pbn_statements = [{"personId": "p1", "area": "301"}]
    intended_statements = [{"personObjectId": "p1", "disciplineId": "301"}]

    only_in_pbn, only_in_intended = mixin.diff_statements(
        pbn_statements, intended_statements
    )

    assert only_in_pbn == set()
    assert only_in_intended == set()


# ------------------------- dekodowanie objectId ---------------------------


def test_decode_publication_object_id_from_dict_response():
    response = {"objectId": "60bdfb2f7bd39c7c59e6a3b1"}
    assert (
        decode_publication_object_id(response, bez_oswiadczen=False)
        == "60bdfb2f7bd39c7c59e6a3b1"
    )


def test_decode_publication_object_id_dict_without_object_id_returns_none():
    assert decode_publication_object_id({}, bez_oswiadczen=False) is None


def test_decode_publication_object_id_non_dict_returns_none():
    assert decode_publication_object_id(None, bez_oswiadczen=False) is None


def test_decode_publication_object_id_from_one_item_list():
    response = [{"id": "60bdfb2f7bd39c7c59e6a3b1"}]
    assert (
        decode_publication_object_id(response, bez_oswiadczen=True)
        == "60bdfb2f7bd39c7c59e6a3b1"
    )


def test_decode_publication_object_id_raises_on_empty_list():
    with pytest.raises(Exception, match="różna od jednego"):
        decode_publication_object_id([], bez_oswiadczen=True)


def test_decode_publication_object_id_raises_on_multi_item_list():
    with pytest.raises(Exception, match="różna od jednego"):
        decode_publication_object_id([{"id": "a"}, {"id": "b"}], bez_oswiadczen=True)


# --------------------- aliasy prywatne == publiczne -----------------------


def test_private_aliases_are_the_same_callables_as_public_names():
    assert StatementsMixin._diff_statements is StatementsMixin.diff_statements
    assert StatementsMixin._statement_key_pbn is StatementsMixin.statement_key_pbn
    assert (
        StatementsMixin._statement_key_intended
        is StatementsMixin.statement_key_intended
    )


# ------------- _post_publication_data — zachowanie bez zmian --------------


class _FakeClient(StatementsMixin):
    def __init__(self, response):
        self._response = response

    def post_publication(self, json):
        return self._response

    def post_publication_no_statements(self, json):
        return self._response


def test_post_publication_data_with_statements_extracts_object_id():
    client = _FakeClient({"objectId": "oid-1"})
    ret, object_id = client._post_publication_data({}, bez_oswiadczen=False)
    assert ret == {"objectId": "oid-1"}
    assert object_id == "oid-1"


def test_post_publication_data_without_statements_extracts_id():
    client = _FakeClient([{"id": "oid-2"}])
    ret, object_id = client._post_publication_data({}, bez_oswiadczen=True)
    assert ret == [{"id": "oid-2"}]
    assert object_id == "oid-2"


def test_post_publication_data_without_statements_raises_on_ambiguous_list():
    client = _FakeClient([{"id": "a"}, {"id": "b"}])
    with pytest.raises(Exception, match="różna od jednego"):
        client._post_publication_data({}, bez_oswiadczen=True)
