import pytest

from pbn_client.const import PBN_GET_PUBLICATION_BY_ID_URL
from pbn_client.exceptions import HttpException, PublicationNotFound
from pbn_client.mixins.publications import PublicationsMixin


class _RaisingTransport:
    def __init__(self, exception=None, value=None):
        self.exception = exception
        self.value = value

    def get(self, url, *args, **kwargs):
        if self.exception is not None:
            raise self.exception
        return self.value


def _client(exception=None, value=None):
    client = PublicationsMixin()
    client.transport = _RaisingTransport(exception=exception, value=value)
    return client


def test_publication_not_found_is_http_exception_subclass():
    assert issubclass(PublicationNotFound, HttpException)


def test_get_publication_by_id_raises_publication_not_found_on_422_marker():
    url = PBN_GET_PUBLICATION_BY_ID_URL.format(id="12345")
    content = "Publication with ID 12345 was not exists!"
    original = HttpException(422, url, content)
    client = _client(exception=original)

    with pytest.raises(PublicationNotFound) as exc_info:
        client.get_publication_by_id("12345")

    assert exc_info.value.status_code == 422
    assert exc_info.value.url == url
    assert exc_info.value.content == content
    assert exc_info.value.__cause__ is original


def test_get_publication_by_id_404_stays_plain_http_exception():
    url = PBN_GET_PUBLICATION_BY_ID_URL.format(id="12345")
    original = HttpException(404, url, "Not Found")
    client = _client(exception=original)

    with pytest.raises(HttpException) as exc_info:
        client.get_publication_by_id("12345")

    assert not isinstance(exc_info.value, PublicationNotFound)
    assert exc_info.value is original


def test_get_publication_by_id_422_without_marker_stays_plain():
    url = PBN_GET_PUBLICATION_BY_ID_URL.format(id="12345")
    original = HttpException(422, url, "Some other validation problem")
    client = _client(exception=original)

    with pytest.raises(HttpException) as exc_info:
        client.get_publication_by_id("12345")

    assert not isinstance(exc_info.value, PublicationNotFound)
    assert exc_info.value is original


def test_get_publication_by_id_bytes_content_with_marker():
    url = PBN_GET_PUBLICATION_BY_ID_URL.format(id="abc")
    content = b"Publication with ID abc was not exists!"
    original = HttpException(422, url, content)
    client = _client(exception=original)

    with pytest.raises(PublicationNotFound) as exc_info:
        client.get_publication_by_id("abc")

    assert exc_info.value.status_code == 422
    assert exc_info.value.url == url
    assert exc_info.value.content == content


def test_get_publication_by_id_success_passthrough():
    client = _client(value={"objectId": "12345"})

    assert client.get_publication_by_id("12345") == {"objectId": "12345"}


def test_publication_not_found_exported_from_package():
    import pbn_client

    assert pbn_client.PublicationNotFound is PublicationNotFound
    assert "PublicationNotFound" in pbn_client.__all__
