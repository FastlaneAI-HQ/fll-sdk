"""What an app hands core to take part in FastMCP's tool surface.

An installed app is not only a REST surface (`AppPlugin.router`) and, for an
app that is also an agent, a branch of the chat graph (`AppPlugin.graph`,
see `graph.py`) -- it can also expose some of its own operations as MCP
(Model Context Protocol) tools, callable by an external MCP client (Claude
Desktop, ChatGPT, ...) through `fll-fastmcp`'s own server. That server is a
separate app, independent of whether FastAI (the chat app) is even installed
on a given tenant -- an app declares `AppPlugin.mcp_tools` once, and whether
it ends up reachable is entirely FastMCP's (and the tenant's entitlements')
business, not this app's. An app with nothing to expose this way (Contacts,
Power Tools) simply leaves `AppPlugin.mcp_tools` unset, the same convention
`graph` already established.

Deliberately thin, mirroring `AgentGraphContribution`: a list of tool specs,
nothing about how a server assembles or namespaces them. FastMCP owns
turning an installed app's `mcp_tools` into the server's actual tool
listing -- including namespacing each tool's `name` as `<app_id>.<name>` (or
whatever scheme it picks) so two apps can each register a tool called
`search` without colliding. This module only defines what one app
contributes, not how the collection as a whole is assembled or served.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from .deps import PlatformDeps

# `(deps, args) -> JSON-serializable result`. Mirrors how `AgentGraphContribution`'s
# nodes already receive `deps`-shaped platform access rather than importing
# core directly.
McpToolHandler = Callable[[PlatformDeps, Dict[str, Any]], Any]


@dataclass(frozen=True)
class McpToolSpec:
    """One tool an app exposes to FastMCP's server.

    IMPORTANT -- the same safety principle already established twice
    elsewhere in this platform (FastBoards' chart specs in `chart_schema.py`,
    FastAnalytics' analysis specs): `handler` is real code performing a
    validated, bounded operation. An MCP tool is NOT a general "run this
    code" or "run this query" escape hatch handed to an external LLM client.
    `input_schema` should constrain arguments as tightly as the operation
    allows, and `handler` should do exactly one well-defined thing with
    them -- never a passthrough to a raw query engine, a shell, or a code
    interpreter. Any app author adding to an `mcp_tools` list (including
    future maintainers of this SDK) should hold every new tool to that bar.
    """

    # Stable, unique *within this app* -- the MCP server namespaces it
    # (likely `<app_id>.<name>`, but composing that is FastMCP's job, not
    # this type's) so two apps' tools can't collide.
    name: str
    # Shown to the external LLM client (Claude Desktop, ChatGPT, ...) as the
    # tool's description, which is what that client's model reads to decide
    # whether and how to call this tool -- write it for that audience, not
    # for another engineer reading this code.
    description: str
    # A JSON Schema object describing this tool's arguments, exactly as an
    # MCP client expects a tool's input to be described.
    input_schema: Dict[str, Any]
    # Performs the operation and returns a JSON-serializable result. See
    # the safety note above: bounded, validated, one well-defined thing.
    handler: McpToolHandler
