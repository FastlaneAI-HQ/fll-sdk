"""What a client can be entitled to.

Owned here, not in core, because core's own built-in apps (chat, admin) and
every installed plugin describe themselves with the same shape -- and an app
repo has to be able to build one of these without importing core.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Feature:
    """One thing a person may be allowed to do inside an app: the unit a client administrator grants in Identity > Roles.

    The app owns its list (it knows what its screens and routes do) and enforces it: a route says `Depends(deps.require_feature("rfq",
    "send"))`, a screen hides or disables the control with `useFeatures("rfq").can("send")`. Identity only configures who holds which.
    Ids are short, lower-case and stable (renaming one silently revokes it from every role that held it); the label and description are
    what the administrator reads.
    """
    id: str
    label: str
    description: str = ""
    # A heading to list it under when an app has many ("Quotes", "Templates"); empty = no heading.
    group: str = ""


@dataclass(frozen=True)
class AppSpec:
    id: str
    label: str
    purpose: str
    always: bool = False
    min_role: str = "member"
    group: str = "primary"
    default_enabled: bool = False
    # What a member can be allowed to do in this app, for role-based access (see `Feature`). Empty = the app is all-or-nothing: a role
    # either includes it or not. A person with a role limited to some features can open the app only if the role includes the app.
    features: Tuple[Feature, ...] = ()
