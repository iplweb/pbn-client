"""Testy sekwencyjnego iteratora stron z polityką skończonych ponowień."""

import pytest

from pbn_client.exceptions import HttpException
from pbn_client.paging import RetryPolicy, iter_pages


class FakeResource:
    """Paginator zgodny z ``PageableResource`` o kontrolowanych stronach.

    ``pages`` to lista, w której każdy element opisuje jedną stronę jako
    listę „prób": kolejne wywołania ``fetch_page(n)`` zwracają (albo rzucają,
    gdy próba jest wyjątkiem) kolejne elementy tej listy; ostatni element
    jest powtarzany w nieskończoność.
    """

    def __init__(self, pages):
        self.pages = pages
        self.total_pages = len(pages)
        self.calls = {n: 0 for n in range(len(pages))}

    def fetch_page(self, page_number):
        attempts = self.pages[page_number]
        index = min(self.calls[page_number], len(attempts) - 1)
        self.calls[page_number] += 1
        result = attempts[index]
        if isinstance(result, Exception):
            raise result
        return result


def http_error(status_code):
    return HttpException(status_code, "/fake/url", "content")


def test_retry_policy_defaults():
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.backoff == 0
    assert policy.retry_statuses == frozenset({500, 502, 503, 504})


def test_retry_policy_delay_is_exponential():
    policy = RetryPolicy(backoff=2)
    assert policy.delay(1) == 2
    assert policy.delay(2) == 4
    assert policy.delay(3) == 8


def test_retry_policy_zero_backoff_means_no_delay():
    policy = RetryPolicy(backoff=0)
    assert policy.delay(1) == 0
    assert policy.delay(5) == 0


def test_500_retried_finitely_then_reraised_without_callback():
    resource = FakeResource([[http_error(500)]])

    with pytest.raises(HttpException) as excinfo:
        list(iter_pages(resource))

    assert excinfo.value.status_code == 500
    # Skończona liczba prób — nie pętla nieskończona.
    assert resource.calls[0] == 3


def test_custom_max_attempts_is_respected():
    resource = FakeResource([[http_error(503)]])

    with pytest.raises(HttpException):
        list(iter_pages(resource, retry_policy=RetryPolicy(max_attempts=5)))

    assert resource.calls[0] == 5


def test_401_propagates_immediately_never_swallowed():
    on_skipped_calls = []
    resource = FakeResource([[http_error(401)]])

    with pytest.raises(HttpException) as excinfo:
        list(iter_pages(resource, on_skipped=on_skipped_calls.append))

    assert excinfo.value.status_code == 401
    assert resource.calls[0] == 1
    # Nawet z callbackiem: błędy nie-retryowalne nigdy nie są połykane.
    assert on_skipped_calls == []


def test_403_propagates_immediately():
    resource = FakeResource([[http_error(403)]])

    with pytest.raises(HttpException) as excinfo:
        list(iter_pages(resource))

    assert excinfo.value.status_code == 403
    assert resource.calls[0] == 1


def test_page_succeeding_on_second_attempt_is_yielded():
    resource = FakeResource(
        [
            [["a1", "a2"]],
            [http_error(500), ["b1"]],
            [["c1"]],
        ]
    )

    pages = list(iter_pages(resource))

    assert pages == [["a1", "a2"], ["b1"], ["c1"]]
    assert resource.calls[1] == 2


def test_on_skipped_called_with_page_number_and_error():
    skipped = []
    resource = FakeResource(
        [
            [["a"]],
            [http_error(500)],
            [["c"]],
        ]
    )

    pages = list(
        iter_pages(
            resource,
            on_skipped=lambda page, error: skipped.append((page, error)),
        )
    )

    # Strona 1 raportowana jawnie, iteracja kontynuuje resztę stron.
    assert pages == [["a"], ["c"]]
    assert len(skipped) == 1
    page_number, error = skipped[0]
    assert page_number == 1
    assert isinstance(error, HttpException)
    assert error.status_code == 500
    assert resource.calls[1] == 3


def test_sleep_not_called_with_zero_backoff():
    sleeps = []
    resource = FakeResource([[http_error(500), ["ok"]]])

    pages = list(iter_pages(resource, sleep=sleeps.append))

    assert pages == [["ok"]]
    assert sleeps == []


def test_sleep_called_with_computed_delays():
    sleeps = []
    resource = FakeResource([[http_error(500)]])

    with pytest.raises(HttpException):
        list(
            iter_pages(
                resource,
                retry_policy=RetryPolicy(max_attempts=3, backoff=1),
                sleep=sleeps.append,
            )
        )

    # max_attempts=3 → dwie przerwy między trzema próbami: 1s, 2s.
    assert sleeps == [1, 2]


def test_non_http_exceptions_propagate():
    resource = FakeResource([[ValueError("boom")]])

    with pytest.raises(ValueError):
        list(iter_pages(resource))

    assert resource.calls[0] == 1


def test_exports_available_from_package_root():
    import pbn_client

    assert pbn_client.RetryPolicy is RetryPolicy
    assert pbn_client.iter_pages is iter_pages
