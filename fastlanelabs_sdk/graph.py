"""What an app hands core to take part in the shared agent graph.

An installed app is not only a REST surface (`AppPlugin.router`) -- it can
also be an *agent*: a branch of the LangGraph pipeline core runs for every
chat turn. This is that contract. An app with no agent behavior (Contacts,
Power Tools) simply leaves `AppPlugin.graph` unset; core's router-mounting
loop and its graph-assembly loop are independent of each other.

Deliberately thin: a name, some nodes, some edges, and a predicate deciding
whether a given turn belongs to this app. Core owns the shared `PipelineState`
dict and the supervisor that calls `wants` on each installed contribution in
priority order -- this dataclass carries what one app adds to that, nothing
about how the graph as a whole is assembled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

# A node is `Callable[[PipelineState], dict]` -- returns the keys it changed.
# Typed as `Any` here rather than importing core's PipelineState: that type
# lives in core (backend/app/graph/state.py) and is free to gain fields
# without every app needing to import it just to type-hint a callable.
Node = Callable[[Dict[str, Any]], Dict[str, Any]]

# `(question, history) -> (wants_it, reason, extra_state)`. No user or role
# is available yet at this point in a request -- the same reason the RFQ
# Drafter's own entitlement check is role-free today. Entitlement (is this
# app even turned on for this tenant) is checked by core *before* calling
# `wants`, not inside it -- an app's predicate only ever answers "is this
# turn mine", not "am I allowed to answer it".
#
# `extra_state`: deciding whether a turn belongs to an app can require doing
# some of that app's own work (the RFQ Drafter's `wants` has to parse the
# line items to know whether there are any -- the routing decision *is* the
# parse, and parsing twice risks the two disagreeing). When this contribution
# wins the route, core merges `extra_state` into the graph state before the
# entry node runs, so that work is not repeated. Empty for an app that has
# nothing to precompute.
WantsFn = Callable[[str, List[Dict[str, str]]], Tuple[bool, str, Dict[str, Any]]]


def _never_wants(
    question: str, history: List[Dict[str, str]],
) -> Tuple[bool, str, Dict[str, Any]]:
    return False, "", {}


@dataclass(frozen=True)
class AgentGraphContribution:
    # The node a turn enters on once the supervisor routes to this app.
    entry_node: str
    # name -> node function. Names must not collide with another installed
    # app's node names; core does not namespace them (nodes are LangGraph
    # graph-wide identifiers, not per-app).
    nodes: Dict[str, Node]
    # Static edges within this app's own subgraph.
    edges: List[Tuple[str, str]] = field(default_factory=list)
    # (from_node, condition_fn, {result -> to_node}) -- LangGraph conditional
    # edges, unchanged in shape from `add_conditional_edges`.
    conditional_edges: List[Tuple[str, Callable[[Dict[str, Any]], str], Dict[str, str]]] = field(
        default_factory=list)
    wants: WantsFn = _never_wants
    # Lower is asked first. A narrow, specific app (RFQ: "does this look like
    # a parts list") should outrank a broad default one (FastAI: "answer
    # whatever's left").
    priority: int = 100
    # Exactly one installed contribution should set this -- the supervisor's
    # fallback when no other installed app's `wants` claims the turn.
    default: bool = False
