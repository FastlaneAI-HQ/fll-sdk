"""The chart config every FastBoards chart is -- whether an LLM wrote it from
a prompt, a person pasted it by hand, or a future app produces one some other
way.

Lives here, not in `fll-fastboards`, because "globally typed and accepted
within FLL" means one canonical shape the whole platform can validate
against without depending on FastBoards' own package -- the same reason
`AppSpec`/`AgentGraphContribution` live in this SDK rather than in core.

A chart is: which table it reads (FastTables-owned, by id), a MongoDB
aggregation pipeline that produces the rows to plot, and an encoding (which
field is the x-axis/category, which fields are the plotted series) plus a
chart type. Deliberately silent on *how* it renders -- ApexCharts today,
something else later -- this is a data contract, not a rendering one.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

CHART_TYPES: Tuple[str, ...] = (
    "bar", "line", "area", "pie", "donut", "scatter", "radar", "heatmap",
)

# What a series' value can be, if the pipeline produced it via a $group
# accumulator -- documented here for whoever writes a pipeline by hand or
# prompts one, not enforced (the pipeline itself decides its own shape;
# this is just the vocabulary the prompt-to-chart step is told to use).
AGG_FUNCS: Tuple[str, ...] = ("sum", "avg", "min", "max", "count")

# The JSON-schema shape an LLM's `structured()` call is constrained to.
# `pipeline_json`/`series_json` are JSON-encoded *strings*, not nested
# schema objects -- the same reason FastTables' `filter_json` is a string:
# an aggregation pipeline's shape is genuinely open, and a JSON-schema
# validator fights that instead of describing it. `agg_safety.check_pipeline`
# (fll-fastboards' own module, since the operator allowlist is an execution
# concern, not a data-shape one) is what actually keeps the parsed result
# honest.
CHART_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["chart_type", "title", "pipeline_json", "x", "series_json"],
    "properties": {
        "chart_type": {"type": "string", "enum": list(CHART_TYPES)},
        "title": {"type": "string"},
        "pipeline_json": {
            "type": "string",
            "description": (
                "A MongoDB aggregation pipeline, as a JSON-encoded array of "
                "stage objects, run against the table's collection. Each "
                "resulting document must contain the x field and every "
                "series field named below."
            ),
        },
        "x": {
            "type": "string",
            "description": "Field name, present on every document the "
                            "pipeline produces, used as the chart's "
                            "category/x-axis.",
        },
        "series_json": {
            "type": "string",
            "description": (
                'A JSON-encoded array of {"field": ..., "label": ...} '
                "objects -- one per plotted value, each field present on "
                "every document the pipeline produces."
            ),
        },
    },
}


class ChartSpecError(ValueError):
    """A chart config that doesn't hold together. Its message is shown to
    whoever submitted it -- a prompt result, a pasted JSON blob -- so it
    names exactly what's wrong rather than failing silently."""


def validate_chart_spec(obj: Any) -> Dict[str, Any]:
    """Normalize and validate a chart config, whether it came from a
    prompt-generated plan or was pasted in directly. Raises `ChartSpecError`
    naming exactly what's wrong; returns a normalized dict on success --
    `pipeline` and `series` as real Python objects, not JSON strings, since
    everything past this point (storage, the query, the API response) wants
    them parsed.
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

    pipeline = obj.get("pipeline")
    if pipeline is None and isinstance(obj.get("pipeline_json"), str):
        try:
            pipeline = json.loads(obj["pipeline_json"])
        except json.JSONDecodeError as exc:
            raise ChartSpecError("pipeline_json is not valid JSON: {0}".format(exc))
    if not isinstance(pipeline, list):
        raise ChartSpecError("pipeline must be a JSON array of stage objects")

    x = str(obj.get("x") or "").strip()
    if not x:
        raise ChartSpecError("a chart needs an x field")

    series = obj.get("series")
    if series is None and isinstance(obj.get("series_json"), str):
        try:
            series = json.loads(obj["series_json"])
        except json.JSONDecodeError as exc:
            raise ChartSpecError("series_json is not valid JSON: {0}".format(exc))
    series = _validate_series(series)

    options = obj.get("options") if isinstance(obj.get("options"), dict) else {}

    return {
        "chart_type": chart_type,
        "title": title,
        "table_id": table_id,
        "pipeline": pipeline,
        "x": x,
        "series": series,
        "options": {
            "stacked": bool(options.get("stacked", False)),
            "horizontal": bool(options.get("horizontal", False)),
        },
    }


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
