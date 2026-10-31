"""One deployment URL contract for static builds and Telegram chart links."""

import os
from urllib.parse import urlsplit, urlencode

DEFAULT_SITE_BASE_URL = "https://stell0.github.io/financealerts/"


def site_base_url():
    url = os.environ.get("SITE_BASE_URL", DEFAULT_SITE_BASE_URL).rstrip("/") + "/"
    parts = urlsplit(url)
    if (parts.scheme not in {"https", "http"} or not parts.netloc or parts.query
            or parts.fragment or parts.username or parts.password):
        raise ValueError(
            "SITE_BASE_URL must be an HTTP(S) site root without credentials, query or fragment"
        )
    return url


def chart_url(item):
    return site_base_url() + "?" + urlencode({"ticker": item.yahoo_symbol})
