"""What an app hands core to take part in Admin's Setup checklist.

An installed app used to have no single place a tenant admin could go to
see "is this app actually configured yet" -- required connection details
(an API key, a base URL, a secret) lived wherever the app's own settings
UI put them, if it had one at all, and nothing aggregated that across every
installed app into one list. `AppPlugin.config_status` is that aggregation
point: an app declares the handful of things it needs configured, and
whether each currently is, and Admin's Setup page collects every installed
app's list into one checklist, each item linking back to that app's own
settings surface -- never a global settings blob core owns on the app's
behalf. An app with nothing that needs configuring (Contacts, Power Tools)
simply leaves `AppPlugin.config_status` unset, the same convention `graph`
and `mcp_tools` already established.

Deliberately thin, mirroring `McpToolSpec`/`AgentGraphContribution`: a
function that reports status, not a schema for *editing* a setting -- an
app's own routes (reached through its own settings page) still own reading
and writing whatever it stores (through `PlatformDeps.runtime.get`/`.put`
for a core-held Knob, or an app's own table for something it stores itself,
same as `fll-fastmcp`'s API key or `fll-fasttools`' registered servers
already do). This module only defines what one app reports, not how the
checklist as a whole is rendered or where a given app's settings actually
live in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from .deps import PlatformDeps


@dataclass(frozen=True)
class ConfigItem:
    """One thing this app either has configured or doesn't, for Admin's
    Setup checklist.

    `key` only needs to be unique *within this app* -- the checklist
    namespaces items by app id, the same reasoning `McpToolSpec.name`
    already uses for MCP tool names.
    """

    # Stable, unique within this app -- not shown to anyone, just a
    # React-key-shaped identifier for the checklist to render by.
    key: str
    # What a tenant admin reading the checklist sees, e.g. "Anthropic API
    # key" or "EmTL connection". Written for that reader, not another
    # engineer -- the same audience `McpToolSpec.description` writes for.
    label: str
    # Whether this item is currently satisfied. An app decides what
    # "satisfied" means for its own item -- a Knob being non-empty, a row
    # existing in the app's own table, whatever is true for that item.
    satisfied: bool
    # Whether the *product* is meaningfully degraded while this stays
    # unsatisfied (required=True), or it's a nice-to-have the app works
    # fine without (required=False, e.g. FastTables' optional external
    # Mongo -- SQLite is a real, working default, not a placeholder).
    # The checklist page uses this to separate "needs attention" from
    # "optional, if you want it".
    required: bool = True
    # One short sentence, shown only when `satisfied` is False, saying what
    # not having this actually costs -- the same "say what breaks, not just
    # what's missing" reasoning already applied to `McpToolSpec.description`
    # and to every user-facing error message elsewhere in this platform.
    # Optional: a self-explanatory label (e.g. "Anthropic API key") may not
    # need one.
    hint: str = ""


# `(deps) -> [ConfigItem, ...]`. Called fresh on every checklist read, the
# same "never a stale cache" reasoning `FastMCP`'s live tool-list assembly
# already uses -- a tenant admin who just pasted in a key expects the
# checklist to reflect that immediately, not after some cache expires.
ConfigStatusFn = Callable[[PlatformDeps], List[ConfigItem]]
