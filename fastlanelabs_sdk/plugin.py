"""What an app repo hands back to core once it has its platform deps."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable, List, Optional

from fastapi import APIRouter

from .graph import AgentGraphContribution
from .mcp_tools import McpToolSpec
from .spec import AppSpec


@dataclass(frozen=True)
class AppPlugin:
    id: str
    spec: AppSpec
    router: APIRouter
    # The RFQ-style machine surface: authenticated by a shared secret rather
    # than a session, so it carries no `require_app` dependency of its own.
    # Most apps have none.
    external_router: Optional[APIRouter] = None
    # This app's OWN tables only -- executescript'd once, after core's
    # schema. Never a table core also writes to; a table an app shares with
    # core (like the in-repo `rfq_drafts` table this contract exists to stop
    # repeating) can't move to another repo without moving core's own code
    # with it.
    schema: str = ""
    migrate: Optional[Callable[[sqlite3.Connection], None]] = None
    # Set only by an app that is also an agent -- contributes nodes/edges to
    # the shared chat graph rather than (or as well as) a REST surface. Most
    # apps (Contacts, Power Tools) leave this unset.
    graph: Optional[AgentGraphContribution] = None
    # Set only by an app that wants some of its own operations callable as
    # MCP tools through `fll-fastmcp`'s server -- independent of `graph`
    # (an app can expose tools without being a chat-graph agent, or vice
    # versa) and independent of whether FastAI is even installed on this
    # tenant. Most apps leave this unset, same convention as `graph`.
    mcp_tools: Optional[List[McpToolSpec]] = None
