import time
import os
from fastapi import HTTPException
from collections import defaultdict
import threading

# Per-tenant limits in front of the ERP.
#
# These used to be hard-coded at 60 reads/hour and 20 writes/hour. For a 40-user
# manufacturer that is roughly 0.3 questions per user per hour: the assistant
# would start refusing normal work after ten minutes of one person using it. The
# defaults now live in config.py and are sized for a real company; tighten them
# per tenant if a client's HANA box is small.
#
# KNOWN LIMITATION (documented, not hidden): this limiter is in-process. It is
# correct for the single-worker deployment we ship, and it resets when the
# process restarts. If you ever run multiple workers, move it to the shared
# SQLite/Redis store or the limits will be per-worker.
import config as _config

READ_LIMIT_PER_HR = int(os.getenv("CIRA_RATE_LIMIT_READS_PER_HR", "") or _config.RATE_LIMIT_READS_PER_HR)
WRITE_LIMIT_PER_HR = int(os.getenv("CIRA_RATE_LIMIT_WRITES_PER_HR", "") or _config.RATE_LIMIT_WRITES_PER_HR)
WINDOW_SECONDS = int(os.getenv("CIRA_RATE_LIMIT_WINDOW_S", "") or _config.RATE_LIMIT_WINDOW_S)

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
