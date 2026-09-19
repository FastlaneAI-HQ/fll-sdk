"""Smoke test for `McpToolSpec` and `AppPlugin.mcp_tools`.

There is no existing test suite in this repo to mirror coverage from (no
`tests/` directory exists as of the `graph`/`AgentGraphContribution`
addition) -- this is a first, minimal one, exercising the same shape a
real app (e.g. the FastMCP app itself, or an app opting into it) would:
build an `McpToolSpec`, a `handler` that uses `deps`, and an `AppPlugin`
that carries it.
"""
from __future__ import annotations

import unittest
from typing import Any, Dict

from fastapi import APIRouter

from fastlanelabs_sdk import AppPlugin, AppSpec, McpToolSpec


class _FakeDeps:
    """Stands in for `PlatformDeps` -- a `Protocol`, so nothing here is
    checked at runtime; only the attributes the handler actually uses need
    to exist."""

    def __init__(self, rows):
        self._rows = rows

    def get_conn(self):
        raise NotImplementedError


def _lookup_handler(deps: Any, args: Dict[str, Any]) -> Any:
    contact_id = args["contact_id"]
    for row in deps._rows:
        if row["id"] == contact_id:
            return row
    return None


class McpToolSpecTest(unittest.TestCase):
    def test_construction(self):
        tool = McpToolSpec(
            name="lookup_contact",
            description="Look up a single contact by its id.",
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["contact_id"],
                "properties": {"contact_id": {"type": "string"}},
            },
            handler=_lookup_handler,
        )
        self.assertEqual(tool.name, "lookup_contact")
        self.assertTrue(callable(tool.handler))

        deps = _FakeDeps(rows=[{"id": "c1", "name": "Ada"}])
        result = tool.handler(deps, {"contact_id": "c1"})
        self.assertEqual(result, {"id": "c1", "name": "Ada"})

    def test_app_plugin_accepts_mcp_tools(self):
        tool = McpToolSpec(
            name="lookup_contact",
            description="Look up a single contact by its id.",
            input_schema={"type": "object", "properties": {}},
            handler=_lookup_handler,
        )
        plugin = AppPlugin(
            id="contacts",
            spec=AppSpec(id="contacts", label="Contacts", purpose="test"),
            router=APIRouter(),
            mcp_tools=[tool],
        )
        self.assertEqual(plugin.mcp_tools, [tool])

    def test_mcp_tools_defaults_to_none(self):
        plugin = AppPlugin(
            id="power-tools",
            spec=AppSpec(id="power-tools", label="Power Tools", purpose="test"),
            router=APIRouter(),
        )
        self.assertIsNone(plugin.mcp_tools)


if __name__ == "__main__":
    unittest.main()
