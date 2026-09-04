"""Shared HTTP GET helpers for source plugins.

Every API-backed plugin needs the same thing: a urllib GET carrying the
pipeline User-Agent, decoded as UTF-8. Centralizing it means a UA change, a
retry policy or a proxy lands in one place instead of one copy per plugin.
Leading-underscore modules are skipped by site_profiles' plugin discovery.
"""
import json
import urllib.request

from constants import get_user_agent


def get_text(url, timeout=30, headers=None, accept="*/*"):
    """GET `url` and return the body as text (undecodable bytes replaced)."""
    hdrs = {"User-Agent": get_user_agent(), "Accept": accept}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def get_json(url, timeout=30, headers=None):
    """GET `url` with an `Accept: application/json` header and parse the body."""
    return json.loads(get_text(url, timeout=timeout, headers=headers,
                               accept="application/json"))
