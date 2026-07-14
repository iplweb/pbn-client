"""Testy aliasów kompatybilności publicznego API wyjątków (release 0.2)."""

import pbn_client
from pbn_client.exceptions import (
    SciencistDoesNotExist,
    ScientistDoesNotExist,
    StatementsResendFailedException,
)


def test_sciencist_alias_is_same_class():
    assert SciencistDoesNotExist is ScientistDoesNotExist


def test_both_scientist_names_exported_from_package():
    assert pbn_client.ScientistDoesNotExist is ScientistDoesNotExist
    assert pbn_client.SciencistDoesNotExist is ScientistDoesNotExist
    assert "ScientistDoesNotExist" in pbn_client.__all__
    assert "SciencistDoesNotExist" in pbn_client.__all__


def test_both_scientist_names_in_exceptions_all():
    from pbn_client import exceptions

    assert "ScientistDoesNotExist" in exceptions.__all__
    assert "SciencistDoesNotExist" in exceptions.__all__


def test_statements_resend_failed_keyword_correlation_id():
    exc = StatementsResendFailedException(
        correlation_id=123, pbn_uid="abc", last_error="boom"
    )
    assert exc.correlation_id == 123
    assert exc.publication_pk == 123
    assert exc.pbn_uid == "abc"
    assert exc.last_error == "boom"


def test_statements_resend_failed_positional_still_works():
    exc = StatementsResendFailedException(123, "abc", "boom")
    assert exc.correlation_id == 123
    assert exc.publication_pk == 123
    assert exc.pbn_uid == "abc"
    assert exc.last_error == "boom"


def test_statements_resend_failed_message_mentions_ids():
    exc = StatementsResendFailedException(123, "abc", "boom")
    text = str(exc)
    assert "123" in text
    assert "abc" in text
    assert "boom" in text
