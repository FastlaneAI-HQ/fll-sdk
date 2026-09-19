"""The chart config every FastBoards chart is -- whether an LLM wrote it from
a prompt, a person pasted it by hand, or a future app produces one some other
way.

Lives here, not in `fll-fastboards`, because "globally typed and accepted
within FLL" means one canonical shape the whole platform can validate
against without depending on FastBoards' own package -- the same reason
`AppSpec`/`AgentGraphContribution` live in this SDK rather than in core.

The query is a backend-agnostic spec (filter/group_by/aggregations/sort/
limit), not a MongoDB aggregation pipeline -- a FastTables table can be
stored in this VM's own SQLite (the default) or in an operator-provided
external MongoDB, and a chart has to run on either without caring which.
Whoever executes a chart (`fll-fastboards`'s own `sql_query.py`/
`mongo_query.py`) translates this spec into that backend's native query;
this module only defines and validates the spec itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

CHART_TYPES: Tuple[str, ...] = (
    "bar", "line", "area", "pie", "donut", "scatter", "radar", "heatmap",
)

# What a filter condition can compare with. Deliberately flat and AND-only
# (no nested $or/$and) -- a chart's filter is meant to narrow a table down,
# not express arbitrary logic, and a flat list is the same shape on both a
# SQL WHERE clause and a Mongo $match, with nothing to translate wrong.
FILTER_OPS: Tuple[str, ...] = ("eq", "ne", "gt", "gte", "lt", "lte", "in")

# What an aggregation can compute, per group. "count" ignores `field`, every
# other one requires it.
AGG_FUNCS: Tuple[str, ...] = ("sum", "avg", "min", "max", "count")

CHART_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chart_type", "title", "query", "x", "series"],
    "properties": {
        "chart_type": {"type": "string", "enum": list(CHART_TYPES)},
        "title": {"type": "string"},
        "query": {
            "type": "object",
            "additionalProperties": False,
            "required": ["aggregations"],
            "properties": {
                "filter": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["field", "op", "value"],
                        "properties": {
                            "field": {"type": "string"},
                            "op": {"type": "string", "enum": list(FILTER_OPS)},
                            # Kept as a string in the plan and coerced against
                            # the table's own field type when applied -- the
                            # table schema, not the LLM, decides whether a
                            # value is really a number or a date.
                            "value": {"type": "string"},
                        },
                    },
                },
                "group_by": {
                    "type": "string",
                    "description": "A field to group rows by, or an empty "
                                    "string for no grouping (aggregations "
                                    "then run over the whole table).",
                },
                "aggregations": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["fn", "field", "label"],
                        "properties": {
                            "fn": {"type": "string", "enum": list(AGG_FUNCS)},
                            "field": {
                                "type": "string",
                                "description": "Required for every fn except "
                                                "count, which ignores it.",
                            },
                            "label": {"type": "string"},
                        },
                    },
                },
                "sort_by": {
                    "type": "string",
                    "description": "An aggregation's label, or group_by, or "
                                    "empty for no explicit ordering.",
                },
                "sort_desc": {"type": "boolean"},
                "limit": {"type": "integer"},
            },
        },
        "x": {
            "type": "string",
            "description": "group_by if set, otherwise a raw field name -- "
                            "the category/x-axis of the chart.",
        },
        "series": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field", "label"],
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "An aggregation's label, or a raw "
                                        "field name if there are no "
                                        "aggregations.",
                    },
                    "label": {"type": "string"},
                },
            },
        },
    },
}


class ChartSpecError(ValueError):
    """A chart config that doesn't hold together. Its message is shown to
    whoever submitted it -- a prompt result, a pasted JSON blob -- so it
    names exactly what's wrong rather than failing silently."""


def _validate_filter(filter_list: Any) -> List[Dict[str, Any]]:
    if filter_list is None:
        return []
    if not isinstance(filter_list, list):
        raise ChartSpecError("filter must be a JSON array")
    out = []
    for item in filter_list:
        if not isinstance(item, dict):
            raise ChartSpecError("each filter condition must be an object")
        field = str(item.get("field") or "").strip()
        op = item.get("op")
        if not field:
            raise ChartSpecError("each filter condition needs a field")
        if op not in FILTER_OPS:
            raise ChartSpecError(
                "filter op must be one of {0}".format(", ".join(FILTER_OPS)))
        if "value" not in item:
            raise ChartSpecError("each filter condition needs a value")
        out.append({"field": field, "op": op, "value": item["value"]})
    return out


def _validate_aggregations(aggs: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(aggs, list) or not aggs:
        raise ChartSpecError("query.aggregations must be a non-empty array")
    out = []
    for item in aggs:
        if not isinstance(item, dict):
            raise ChartSpecError("each aggregation must be an object")
        fn = item.get("fn")
        if fn not in AGG_FUNCS:
            raise ChartSpecError(
                "aggregation fn must be one of {0}".format(", ".join(AGG_FUNCS)))
        field = str(item.get("field") or "").strip() or None
        if fn != "count" and not field:
            raise ChartSpecError("aggregation {0} needs a field".format(fn))
        label = str(item.get("label") or field or fn).strip()
        out.append({"fn": fn, "field": field, "label": label})
    return out


def _validate_series(series: Any) -> List[Dict[str, str]]:
    if not isinstance(series, list) or not series:
        raise ChartSpecError("series must be a non-empty array")
    out = []
    for item in series:
        if not isinstance(item, dict):
            raise ChartSpecError("each series entry must be an object")
        field = str(item.get("field") or "").strip()
        if not field:
            raise ChartSpecError("each series entry needs a field")
        label = str(item.get("label") or field).strip()
        out.append({"field": field, "label": label})
    return out


def validate_chart_spec(obj: Any) -> Dict[str, Any]:
    """Normalize and validate a chart config, whether it came from a
    prompt-generated plan, a pasted blob, or a chat proposal. Raises
    `ChartSpecError` naming exactly what's wrong; returns a normalized dict
    on success -- this does NOT check field names against a real table's
    schema (it has none to check against), that's `fll-fastboards`'
    `query_spec_safety.check`'s job once a table is known.
    """
    if not isinstance(obj, dict):
        raise ChartSpecError("a chart config must be a JSON object")

    chart_type = obj.get("chart_type")
    if chart_type not in CHART_TYPES:
        raise ChartSpecError(
            "chart_type must be one of {0}".format(", ".join(CHART_TYPES)))

    title = str(obj.get("title") or "").strip()
    if not title:
        raise ChartSpecError("a chart needs a title")

    table_id = str(obj.get("table_id") or "").strip()
    if not table_id:
        raise ChartSpecError("a chart needs a table_id")

    query = obj.get("query")
    if not isinstance(query, dict):
        raise ChartSpecError("a chart needs a query object")

    limit = query.get("limit")
    if limit is None:
        limit = 200
    if not isinstance(limit, int) or limit < 1:
        raise ChartSpecError("query.limit must be a positive integer")

    x = str(obj.get("x") or "").strip()
    if not x:
        raise ChartSpecError("a chart needs an x field")

    options = obj.get("options") if isinstance(obj.get("options"), dict) else {}

    return {
        "chart_type": chart_type,
        "title": title,
        "table_id": table_id,
        "query": {
            "filter": _validate_filter(query.get("filter")),
            "group_by": str(query.get("group_by") or "").strip() or None,
            "aggregations": _validate_aggregations(query.get("aggregations")),
            "sort_by": str(query.get("sort_by") or "").strip() or None,
            "sort_desc": bool(query.get("sort_desc", False)),
            "limit": min(limit, 200),
        },
        "x": x,
        "series": _validate_series(obj.get("series")),
        "options": {
            "stacked": bool(options.get("stacked", False)),
            "horizontal": bool(options.get("horizontal", False)),
        },
    }
