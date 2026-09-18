"""The platform services a plugin is allowed to depend on.

An app repo must not import core's internal module paths -- `backend.app.*`
is free to move. It depends on this shape instead, and core hands it
something that satisfies it structurally at install time: Python does not
check `Protocol` conformance at runtime, so a plain object (or even a module)
with matching attributes works. This is documentation of the contract, not an
interface core has to declare implementing.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable, Protocol


class PlatformDeps(Protocol):
    def get_conn(self) -> sqlite3.Connection: ...

    def get_store(self) -> Any: ...

    def current_user(self, request: Any) -> Any: ...

    def require_app(self, app_id: str) -> Callable: ...

    def get_settings(self) -> Any: ...

    # Read-only platform configuration (e.g. `runtime.emtl_enabled()`,
    # `runtime.emtl_base_url()`). Exposed as one namespace rather than one
    # protocol method per accessor, since which accessors an app needs is not
    # something this contract can predict in advance.
    runtime: Any
