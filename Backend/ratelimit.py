import time
import os
from fastapi import HTTPException
from collections import defaultdict
import threading

# Configurable limits (Task specification: 60 reads/hr, 20 writes/hr)
READ_LIMIT_PER_HR = int(os.getenv("CIRA_RATE_LIMIT_READS_PER_HR", "60"))
WRITE_LIMIT_PER_HR = int(os.getenv("CIRA_RATE_LIMIT_WRITES_PER_HR", "20"))
WINDOW_SECONDS = int(os.getenv("CIRA_RATE_LIMIT_WINDOW_S", "3600"))

class RateLimitError(HTTPException):
    """Specific exception for ERP tenant rate limits, allowing caller disambiguation."""
    def __init__(self, action_type: str, limit: int):
        detail = f"Rate limit exceeded for {action_type}s. Maximum {limit} per hour for this company database."
        super().__init__(status_code=429, detail=detail)
        self.action_type = action_type
        self.limit = limit


# In-memory rate limiter per tenant
# Format: { tenant_id: { "read": [timestamp1, timestamp2], "write": [...] } }
_rate_limits = defaultdict(lambda: {"read": [], "write": []})
_lock = threading.Lock()
_op_counter = 0

def _sweep_idle_tenants(cutoff: float):
    """Evict tenants with zero active timestamps within the sliding window."""
    idle_keys = [
        k for k, v in _rate_limits.items()
        if not any(t > cutoff for t in v["read"]) and not any(t > cutoff for t in v["write"])
    ]
    for k in idle_keys:
        del _rate_limits[k]


def check_rate_limit(tenant_id: str, action_type: str = "read"):
    """
    Enforces per-tenant rate limits.
    action_type should be "read" or "write".
    """
    global _op_counter
    if action_type not in ("read", "write"):
        return

    clean_tenant = (tenant_id or "default").strip()
    limit = WRITE_LIMIT_PER_HR if action_type == "write" else READ_LIMIT_PER_HR
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        _op_counter += 1
        if _op_counter % 100 == 0:
            _sweep_idle_tenants(cutoff)

        timestamps = _rate_limits[clean_tenant][action_type]
        # Prune expired timestamps
        timestamps = [t for t in timestamps if t > cutoff]
        _rate_limits[clean_tenant][action_type] = timestamps

        if len(timestamps) >= limit:
            raise RateLimitError(action_type=action_type, limit=limit)

        _rate_limits[clean_tenant][action_type].append(now)
