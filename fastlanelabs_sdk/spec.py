"""What a client can be entitled to.

Owned here, not in core, because core's own built-in apps (chat, admin) and
every installed plugin describe themselves with the same shape -- and an app
repo has to be able to build one of these without importing core.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppSpec:
    id: str
    label: str
    purpose: str
    always: bool = False
    min_role: str = "member"
    group: str = "primary"
