# SPDX-License-Identifier: MIT
"""Proxy-aware urlopen helper.

System HTTP proxies (notably WinINET on Windows) can intercept requests to
``127.0.0.1`` / ``localhost`` and return ``503 Service Unavailable``. That
breaks local mock services. This helper bypasses the proxy for localhost
targets while still honoring proxy settings for real remote hosts.

Set ``SELF_COACHING_TRUST_PROXY=1`` to honor proxy settings even for localhost.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import Any

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_OPENER_CACHE: dict[bool, urllib.request.OpenerDirector] = {}


def _trust_proxy() -> bool:
    return os.environ.get("SELF_COACHING_TRUST_PROXY", "").lower() in ("1", "true", "yes")


def _is_local(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host in _LOCAL_HOSTS


def _opener_for(bypass_proxy: bool) -> urllib.request.OpenerDirector:
    opener = _OPENER_CACHE.get(bypass_proxy)
    if opener is None:
        if bypass_proxy:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        else:
            opener = urllib.request.build_opener()
        _OPENER_CACHE[bypass_proxy] = opener
    return opener


def urlopen(req: Any, *, timeout: float | None = None) -> Any:
    """Drop-in for ``urllib.request.urlopen`` that bypasses the proxy for localhost."""
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    bypass = _is_local(url) and not _trust_proxy()
    return _opener_for(bypass).open(req, timeout=timeout)
