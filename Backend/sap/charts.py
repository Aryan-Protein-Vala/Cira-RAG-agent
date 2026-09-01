"""Turn a result set into a chart the UI can actually render.

The old implementation handed Recharts the raw 500-row result and guessed the
axes from hard-coded entity names, which produced unreadable charts (500 bars,
one per document number) or invisible ones (a string column on the Y axis).

This module aggregates first: pick a dimension with sensible cardinality, pick
a numeric measure, group, sort, keep the top N and roll everything else into
"Others".
"""

from __future__ import annotations

import datetime as dt
import re
from collections import OrderedDict, defaultdict
from typing import Any

from .entities import semantics_for

MAX_POINTS = 20
MAX_PIE_SLICES = 10

MEASURE_PRIORITY = [
    "doctotal", "linetotal", "total", "amount", "balance", "currtotal", "maxsumloc",
    "debit", "credit", "paidtodate", "salary", "onhand", "quantity", "planedqty",
    "plannedqty", "quantityonstock", "value", "count", "avgprice", "netamount",
]
DIMENSION_PRIORITY = [
    "cardname", "itemname", "acctname", "whsname", "whscode", "dscription", "city",
    "country", "jobtitle", "name", "groupname", "itmsgrpnam", "slpname", "status",
    "docstatus", "cardcode", "itemcode", "dept", "branch", "priority",
]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _looks_like_date(value: Any) -> bool:
    return isinstance(value, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", value))


def detect_chart_type(user_query: str, default: str = "bar") -> str:
    q = (user_query or "").lower()
    if any(w in q for w in ("pie", "share", "split", "distribution", "breakdown", "proportion", "mix")):
        return "pie"
    if any(w in q for w in ("trend", "over time", "monthly", "month by month", "growth", "timeline", "line chart")):
        return "line"
    if "area" in q:
        return "area"
    if any(w in q for w in ("bar chart", "column chart", "compare", "top ", "ranking", "rank")):
        return "bar"
    return default


def _column_stats(rows: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for key in rows[0].keys():
        values = [r.get(key) for r in rows]
        non_null = [v for v in values if v is not None and v != ""]
        numeric = [v for v in non_null if _is_number(v)]
        stats[key] = {
            "distinct": len({str(v) for v in non_null}),
            "numeric_ratio": (len(numeric) / len(non_null)) if non_null else 0.0,
            "date_ratio": (sum(1 for v in non_null if _looks_like_date(v)) / len(non_null)) if non_null else 0.0,
            "sum": sum(numeric) if numeric else 0,
            "non_null": len(non_null),
        }
    return stats


def pick_measure(rows: list[dict], stats: dict, table: str) -> str | None:
    sem = semantics_for(table)
    candidates = [
        k for k, s in stats.items()
        if s["numeric_ratio"] > 0.7 and s["non_null"] > 0 and s["date_ratio"] < 0.3
    ]
    if not candidates:
        return None
    preferred = sem.get("amount")
    if preferred and preferred in candidates:
        return preferred
    for want in MEASURE_PRIORITY:
        for c in candidates:
            if c.lower() == want:
                return c
    for want in MEASURE_PRIORITY:
        for c in candidates:
            if want in c.lower():
                return c
    # avoid identifier-ish columns (DocNum, LineNum, codes)
    non_ids = [c for c in candidates
               if not re.search(r"(num|entry|id|code|line|year)$", c.lower())]
    pool = non_ids or candidates
    return max(pool, key=lambda c: abs(stats[c]["sum"]))


def pick_dimension(rows: list[dict], stats: dict, table: str, measure: str | None,
                   want_time: bool) -> str | None:
    sem = semantics_for(table)
    n = len(rows)

    if want_time:
        dates = [k for k, s in stats.items() if s["date_ratio"] > 0.7]
        if dates:
            preferred = sem.get("date")
            return preferred if preferred in dates else dates[0]

    text_cols = [
        k for k, s in stats.items()
        if k != measure and s["numeric_ratio"] < 0.6 and s["date_ratio"] < 0.7 and s["distinct"] > 1
    ]
    if not text_cols:
        dates = [k for k, s in stats.items() if s["date_ratio"] > 0.7]
        return dates[0] if dates else None

    for want in DIMENSION_PRIORITY:
        for c in text_cols:
            if c.lower() == want:
                return c
    # otherwise the column whose cardinality is most "chartable"
    def score(col: str) -> tuple:
        d = stats[col]["distinct"]
        ideal = abs(d - min(12, max(3, n // 8)))
        too_unique = 1 if d > max(40, n * 0.8) else 0
        return (too_unique, ideal)

    return sorted(text_cols, key=score)[0]


def _humanise(name: str) -> str:
    """Total_DocTotal -> Total Doc Total; CardName -> Card Name."""
    text = name.replace("_", " ")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _month_key(value: str) -> str:
    try:
        return dt.date.fromisoformat(value[:10]).strftime("%Y-%m")
    except Exception:
        return str(value)[:7]


def build_chart(
    rows: list[dict],
    table: str,
    user_query: str = "",
    entity_label: str = "",
    simulated: bool = False,
) -> dict | None:
    """Return an SSE-ready chart payload, or None when nothing sensible fits."""
    if not rows or not isinstance(rows[0], dict) or len(rows) < 2:
        return None

    stats = _column_stats(rows)
    chart_type = detect_chart_type(user_query)
    want_time = chart_type in ("line", "area")

    measure = pick_measure(rows, stats, table)
    dimension = pick_dimension(rows, stats, table, measure, want_time)
    if dimension is None:
        return None

    is_time = stats[dimension]["date_ratio"] > 0.7
    if is_time and chart_type == "bar" and stats[dimension]["distinct"] > MAX_POINTS:
        chart_type = "line"

    # ── aggregate ────────────────────────────────────────────────────────────
    buckets: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        raw_key = row.get(dimension)
        if raw_key is None or raw_key == "":
            raw_key = "(blank)"
        key = _month_key(str(raw_key)) if is_time else str(raw_key)
        counts[key] += 1
        if measure and _is_number(row.get(measure)):
            buckets[key] += float(row[measure])

    if measure and any(buckets.values()):
        data_map: dict[str, float] = dict(buckets)
        measure_label = measure
    else:
        data_map = {k: float(v) for k, v in counts.items()}
        measure_label = "Records"

    if len(data_map) < 2:
        return None

    if is_time:
        ordered = OrderedDict(sorted(data_map.items(), key=lambda kv: kv[0]))
        points = list(ordered.items())[-MAX_POINTS * 2:]
    else:
        ordered_items = sorted(data_map.items(), key=lambda kv: abs(kv[1]), reverse=True)
        cap = MAX_PIE_SLICES if chart_type == "pie" else MAX_POINTS
        points = ordered_items[:cap]
        rest = ordered_items[cap:]
        if rest:
            points.append(("Others", sum(v for _, v in rest)))

    data = [
        {
            dimension: (k if len(str(k)) <= 28 else str(k)[:27] + "…"),
            measure_label: round(v, 2) if isinstance(v, float) else v,
        }
        for k, v in points
    ]
    if len(data) < 2:
        return None

    label = entity_label or table
    pretty_measure = _humanise(measure_label)
    if is_time:
        title = f"{pretty_measure} by month · {label}"
    else:
        title = f"{pretty_measure} by {_humanise(dimension)} · {label}"

    return {
        "type": "chart",
        "chartType": chart_type,
        "title": title,
        "data": data,
        "xKey": dimension,
        "yKey": measure_label,
        "category": ("SIMULATED · " if simulated else "") + f"SAP B1 ({label})",
        "aggregated": True,
        "points": len(data),
        "sourceRows": len(rows),
    }
