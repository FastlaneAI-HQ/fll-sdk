"""FastTools' wire shape: the result of calling one external MCP tool.

Separate module from `deps.py` for the same reason `chart_schema.py` is
separate from `graph.py` -- a data shape an app repo imports on its own
(`fll-fastai`'s tool loop, `fll-fasttools`'s admin UI) without pulling in
the whole `PlatformDeps` protocol.

Not to be confused with `mcp_tools.py` (FastMCP's opposite-direction
contract: FastlaneLabs exposing ITS OWN apps' operations as MCP tools to
an external client). This module is FastTools': FastAI consuming someone
else's MCP server as a tool.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class McpCallResult:
    """Always returned by `PlatformDeps.mcp.call_tool()`, success or
    failure -- callers never need a separate exception path for "the tool
    call didn't work"; that's `ok=False` with `error` set.
    """

    ok: bool
    result: Any
    error: Optional[str]
    truncated: bool
    ms: int
    server_name: str
    tool_name: str
