"""Read-only, key-authenticated access to the app registry.

The registry's storage account is private; the only way in is the
fll-registry HTTP service in front of it. A tenant install authenticates with
the registry key issued for that tenant (`FASTLANELABS_REGISTRY_KEY`, format
`flr_<tenant>_<8 hex>_<48 hex>`) and reads exactly the paths it used to read
straight out of Blob Storage:

    catalog.json                    (already filtered to the tenant's apps)
    <app>/versions.json
    <app>/<x.y.z>/<file>
    themes/catalog.json
    themes/<id>/<x.y.z>/<file>

Deliberately dependency-free (`urllib` only), the same way the rest of the
SDK's install-time code is. The key is access control only: callers still
check every downloaded artifact's sha256 against `versions.json`.

The key is a secret. It is never logged, never put in an exception message,
and only ever sent over HTTPS (plain HTTP is accepted for loopback addresses,
for local testing), and never re-sent across a redirect.
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

KEY_ENV = "FASTLANELABS_REGISTRY_KEY"
URL_ENV = "FASTLANELABS_REGISTRY_URL"
PLACEHOLDER = "REGISTRY_URL_PLACEHOLDER"

# Mirrors fll-registry's registry_service/keys.py.
KEY_PATTERN = re.compile(r"flr_[a-z0-9][a-z0-9-]{0,39}_[0-9a-f]{8}_[0-9a-f]{48}")

JSON_TIMEOUT = 15.0
FILE_TIMEOUT = 120.0
MAX_RETRIES = 2
BACKOFF = (0.5, 1.5)

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class RegistryError(RuntimeError):
    """Any failure talking to the registry. `.status` is the HTTP status, or
    None when no HTTP response was received (config or network failure)."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class RegistryConfigError(RegistryError):
    """No key, a malformed key, or no registry URL configured."""


class RegistryAuthError(RegistryError):
    """401: the key is missing, invalid or revoked."""


class RegistryForbidden(RegistryError):
    """403: this tenant is not entitled to that app."""


class RegistryNotFound(RegistryError):
    """404: no such file in the registry."""


class RegistryThrottled(RegistryError):
    """429: too many requests."""


class RegistryUnavailable(RegistryError):
    """Network failure or 5xx after retries."""


def base_url() -> str:
    """The registry service's base URL, without a trailing slash.

    `FASTLANELABS_REGISTRY_URL` overrides `registry.url` in the bundled
    `apps.yaml`."""
    url = os.environ.get(URL_ENV, "").strip()
    if not url:
        import yaml
        from . import registry
        data = yaml.safe_load(registry._source()) or {}
        url = str((data.get("registry") or {}).get("url") or "").strip()
    if not url or PLACEHOLDER in url:
        raise RegistryConfigError(
            "no registry URL configured: set {0} or registry.url in "
            "apps.yaml".format(URL_ENV))
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise RegistryConfigError("registry URL must be an http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK:
        raise RegistryConfigError(
            "registry URL must use https (plain http is only allowed for "
            "localhost)")
    return url.rstrip("/")


def _key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise RegistryConfigError(
            "Set {0} — the registry key issued for this tenant".format(KEY_ENV))
    if not KEY_PATTERN.fullmatch(key):
        raise RegistryConfigError(
            "{0} is not a registry key (expected "
            "flr_<tenant>_<8 hex>_<48 hex>)".format(KEY_ENV))
    return key


def key_tenant() -> str:
    """The tenant slug embedded in the configured key (not a secret)."""
    return _key().split("_")[1]


def _quote_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("registry path must be a non-empty string")
    if path.startswith("/") or "\\" in path or any(ord(c) < 0x20 or ord(c) == 0x7f for c in path):
        raise ValueError("invalid registry path: {0!r}".format(path))
    segments = path.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError("invalid registry path: {0!r}".format(path))
    return "/".join(urllib.parse.quote(s, safe="") for s in segments)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never follow a redirect: urllib would carry the Authorization header to
    # wherever it points.
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect())


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _detail(body: bytes) -> str:
    text = body.decode("utf-8", "replace")
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("detail"):
            detail = data["detail"]
            return detail if isinstance(detail, str) else json.dumps(detail)
    except ValueError:
        pass
    return text.strip()[:300]


def _request(route: str, timeout: float, shown: str) -> bytes:
    key = _key()
    url = "{0}/{1}".format(base_url(), route)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer {0}".format(key),
        "Accept": "application/json, application/octet-stream",
        "User-Agent": "fastlanelabs-sdk",
    })
    retry_reason, last_status = "", None  # type: str, Optional[int]
    for attempt in range(MAX_RETRIES + 1):
        try:
            with _opener().open(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                detail = _scrub(_detail(exc.read()), key)
            except Exception:  # noqa: BLE001
                detail = ""
            if status == 401:
                raise RegistryAuthError(
                    "registry key rejected: revoked or mistyped", 401) from None
            if status == 403:
                raise RegistryForbidden(
                    detail or "this tenant is not entitled to {0}".format(shown),
                    403) from None
            if status == 404:
                raise RegistryNotFound(
                    "registry has no {0}".format(shown), 404) from None
            if status == 429:
                raise RegistryThrottled(
                    "registry is throttling requests; try again shortly", 429) from None
            if 300 <= status < 400:
                raise RegistryError(
                    "registry redirected {0} ({1}); refusing to follow".format(
                        shown, status), status) from None
            if status < 500:
                raise RegistryError("GET {0} -> {1}: {2}".format(
                    shown, status, detail), status) from None
            retry_reason = "{0} {1}".format(status, detail).strip()
            last_status = status
        except (socket.timeout, TimeoutError):
            # A timeout already cost the full budget; retrying would turn one
            # slow poll into several.
            raise RegistryUnavailable(
                "registry did not answer GET {0} within {1:.0f}s".format(
                    shown, timeout)) from None
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise RegistryUnavailable(
                    "registry did not answer GET {0} within {1:.0f}s".format(
                        shown, timeout)) from None
            retry_reason = _scrub(str(reason), key)
            last_status = None
        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    raise RegistryUnavailable(
        "registry unreachable for GET {0}: {1}".format(shown, retry_reason),
        last_status)


def get_blob(path: str) -> bytes:
    """The raw bytes of one registry path (e.g. `contacts/versions.json`)."""
    return _request("v1/files/" + _quote_path(path), FILE_TIMEOUT, path)


def get_json(path: str) -> Dict[str, Any]:
    data = _request("v1/files/" + _quote_path(path), JSON_TIMEOUT, path)
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise RegistryError("registry returned invalid JSON for {0}".format(path)) from None


def whoami() -> Dict[str, Any]:
    """`{"tenant", "key_id", "apps"}` for the configured key."""
    data = _request("v1/whoami", JSON_TIMEOUT, "whoami")
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        raise RegistryError("registry returned invalid JSON for whoami") from None
