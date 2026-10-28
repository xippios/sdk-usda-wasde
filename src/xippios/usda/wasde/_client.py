"""The package's one configured ``AsyncClient`` and its error mapping (conventions §6).

In 0.1.0 it sends nothing: every request this package makes goes through
``xippios-usda-esmis``'s tasks (ADR-0021), paced by esmis's client. ``SOURCE`` names
this package in every ``ResultMeta``.
"""

import httpx
from xippios.core import AsyncClient, ClientConfig, RateLimit, XippiosError

from xippios.usda.wasde._version import __version__

SOURCE = "usda-wasde"
BASE_URL = "https://esmis.nal.usda.gov"
API_KEY_ENV: str | None = None
# A self-imposed pace: upstream documents no per-second or per-minute limit (ADR-0010 decision 1).
RATE_LIMIT = RateLimit(per_minute=30, burst=1)


def classify(response: httpx.Response) -> XippiosError | None:
    """Upstream's documented error shapes as taxonomy errors, else ``None`` (conventions §6).

    The ``ClientConfig.classify`` hook: it sees every response before core's status mapping.
    """
    return None


config = ClientConfig(
    source=SOURCE,
    version=__version__,
    base_url=BASE_URL,
    rate_limit=RATE_LIMIT,
    classify=classify,
)

# A source with a documented hourly or daily quota installs a QuotaPolicy of its own on
# config (conventions §6, ADR-0015); core's README shows how.

client = AsyncClient(config)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "RATE_LIMIT",
    "SOURCE",
    "classify",
    "client",
    "config",
]
