"""JSON-safe coercion of database values.

The old code streamed raw hdbcli values straight into json.dumps().  Any real
SAP HANA table blows that up instantly: numeric columns come back as
decimal.Decimal, dates as datetime.date, BLOB/RAW columns as bytes or
memoryview -- all of which raise "Object of type Decimal is not JSON
serializable" and killed the whole SSE stream.
"""

from __future__ import annotations

import base64
import datetime as _dt
import decimal
import math
import uuid
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert a single DB value into something json.dumps() accepts."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        # SUM() over floats produces artefacts like 80152384.27000001
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() and abs(rounded) < 1e15 else rounded
    if isinstance(value, decimal.Decimal):
        if value != value:  # NaN
            return None
        as_float = float(value)
        # Keep integers integral so charts/tables don't render "1450.0"
        if as_float.is_integer() and abs(as_float) < 1e15:
            return int(as_float)
        return round(as_float, 6)
    if isinstance(value, (_dt.datetime,)):
        # SAP B1 stores midnight timestamps for pure dates
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return value.isoformat(timespec="seconds")
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            if len(value) > 4096:
                return f"<binary {len(value)} bytes>"
            return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return str(value)


def rows_to_jsonable(columns: list[str], raw_rows: list) -> list[dict]:
    """Zip cursor rows into dicts with JSON-safe, trimmed values."""
    out: list[dict] = []
    for row in raw_rows:
        record: dict[str, Any] = {}
        for idx, col in enumerate(columns):
            val = to_jsonable(row[idx] if idx < len(row) else None)
            # SAP B1 pads CHAR columns with spaces all over the place
            if isinstance(val, str):
                val = val.strip()
            record[col] = val
        out.append(record)
    return out
