"""Klient API PBN — czysta, niezależna od frameworka warstwa protokołu.

Pakiet operuje wyłącznie na pojęciach PBN: tokeny, URL-e, PBN UID-y, JSON-y
i flagi bool. Nie zna modelu domenowego żadnej aplikacji-hosta, więc może
być używany przez dowolny projekt integrujący się z PBN.
"""

from .auth import OAuthMixin
from .authors import normalize_author_name
from .client import PBNClient
from .exceptions import PublicationNotFound
from .identifiers import is_valid_object_id, parse_publication_id
from .mixins import (
    ConferencesMixin,
    DictionariesMixin,
    InstitutionsMixin,
    InstitutionsProfileMixin,
    JournalsMixin,
    PersonMixin,
    PublicationsMixin,
    PublishersMixin,
    SearchMixin,
)
from .pagination import PageableResource
from .reporting import (
    ErrorReporter,
    LoggingReporter,
    NullReporter,
    get_default_reporter,
    set_default_reporter,
)
from .transport import PBNClientTransport, RequestsTransport
from .utils import smart_content

__all__ = [
    "PBNClient",
    "OAuthMixin",
    "ConferencesMixin",
    "DictionariesMixin",
    "InstitutionsMixin",
    "InstitutionsProfileMixin",
    "JournalsMixin",
    "PersonMixin",
    "PublicationNotFound",
    "PublicationsMixin",
    "PublishersMixin",
    "SearchMixin",
    "PageableResource",
    "ErrorReporter",
    "LoggingReporter",
    "NullReporter",
    "get_default_reporter",
    "set_default_reporter",
    "PBNClientTransport",
    "RequestsTransport",
    "smart_content",
    "is_valid_object_id",
    "parse_publication_id",
    "normalize_author_name",
]
