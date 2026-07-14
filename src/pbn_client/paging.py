"""Sekwencyjna iteracja stron paginatora ze skończoną polityką ponowień.

Naprawia dwa defekty historycznego ``simple_page_getter``:

1. HTTP 500 było ponawiane w nieskończonej, ciasnej pętli (bez limitu
   prób i bez odczekania między próbami);
2. ``skip_page_on_failure=True`` połykało KAŻDY ``HttpException`` —
   również błędy autoryzacji 401/403 — dając po cichu niekompletne wyniki.

Uwaga o warstwach: transport ma własny, niskopoziomowy retry
(``PBNClientTransport._make_get_request_with_retry``) obejmujący błędy
SSL/połączenia — ta polityka działa POZIOM WYŻEJ, na całych stronach
i statusach HTTP. Obie warstwy się składają, a łączna liczba prób
pozostaje ograniczona: co najwyżej ``max_attempts`` prób strony razy
limit prób transportu.
"""

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from .exceptions import HttpException

__all__ = ["RetryPolicy", "iter_pages"]

#: Statusy HTTP uznawane domyślnie za przejściowe (warte ponowienia).
DEFAULT_RETRY_STATUSES = frozenset({500, 502, 503, 504})


class Paginator(Protocol):
    """Minimalny interfejs paginatora (spełniany przez ``PageableResource``)."""

    total_pages: int

    def fetch_page(self, page_number: int) -> Iterable[Any]: ...


@dataclass(frozen=True)
class RetryPolicy:
    """Skończona polityka ponowień dla pobierania pojedynczych stron.

    ``max_attempts`` — łączna liczba prób pobrania strony (co najmniej 1).
    ``backoff`` — bazowe opóźnienie w sekundach; 0 oznacza brak czekania.
    ``retry_statuses`` — tylko te statusy HTTP są ponawiane; wszystkie
    pozostałe (401, 403, 404, …) propagują natychmiast.
    """

    max_attempts: int = 3
    backoff: float = 0
    retry_statuses: frozenset[int] = field(default=DEFAULT_RETRY_STATUSES)

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts musi wynosić co najmniej 1")
        object.__setattr__(self, "retry_statuses", frozenset(self.retry_statuses))

    def should_retry(self, error: HttpException) -> bool:
        """Czy dany błąd HTTP kwalifikuje się do ponowienia."""
        return error.status_code in self.retry_statuses

    def delay(self, attempt: int) -> float:
        """Opóźnienie (sekundy) po nieudanej próbie ``attempt`` (od 1).

        Prosty wykładniczy backoff: ``backoff * 2 ** (attempt - 1)``.
        Przy ``backoff == 0`` zawsze zwraca 0 (testy nie śpią).
        """
        return self.backoff * 2 ** (attempt - 1)


def iter_pages(
    resource: Paginator,
    *,
    retry_policy: RetryPolicy | None = None,
    on_skipped: Callable[[int, HttpException], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[Iterable[Any]]:
    """Yielduj kolejne strony ``resource`` ze skończonym retry per strona.

    Ponawiane są WYŁĄCZNIE statusy z ``retry_policy.retry_statuses``,
    maksymalnie ``retry_policy.max_attempts`` razy. Statusy nie-retryowalne
    (np. 401/403) oraz wyjątki innych typów propagują natychmiast — nigdy
    nie są po cichu połykane.

    Gdy strona ostatecznie padnie po wyczerpaniu prób: jeśli podano
    ``on_skipped``, wywoływane jest ``on_skipped(page_number, error)``
    (jawne raportowanie pominięcia) i iteracja przechodzi do następnej
    strony; bez callbacka ostatni błąd jest re-raise'owany.

    ``sleep`` jest wstrzykiwalne na potrzeby testów; przy zerowym
    opóźnieniu nie jest wywoływane wcale.
    """
    policy = retry_policy if retry_policy is not None else RetryPolicy()

    for page_number in range(resource.total_pages):
        for attempt in range(1, policy.max_attempts + 1):
            try:
                page = resource.fetch_page(page_number)
            except HttpException as error:
                if not policy.should_retry(error):
                    raise
                if attempt >= policy.max_attempts:
                    if on_skipped is None:
                        raise
                    on_skipped(page_number, error)
                    break
                delay = policy.delay(attempt)
                if delay > 0:
                    sleep(delay)
            else:
                yield page
                break
