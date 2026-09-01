import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("audit")


def emit_audit_event(
    request_id: str,
    actor_id: str,       # JWT sub claim only — never a token, header value, or display name
    channel: str,        # "REST" or "MCP"
    action: str,         # e.g. "GET_QUOTE", "LIST_INSTRUMENTS"
    resource: str,       # instrument symbol or endpoint path
    decision: str,       # "ALLOW", "DENY", or "THROTTLE"
    reason_code: str,    # exact code from decision matrix
    latency_ms: float,   # end-to-end measured latency
) -> None:
    """Emit one structured audit event as a single JSON log line.

    Every request — ALLOW, DENY, or THROTTLE — must produce exactly one event.
    This function is the sole point of audit emission; call it on every exit path.

    Security invariants enforced by caller convention:
      - actor_id must be claims["sub"] — never a raw token, Authorization header
        value, display name, or internal database key
      - The Authorization header value must never be passed to any parameter here
      - No PII fields are written
    """
    event = {
        "event_id":      str(uuid.uuid4()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "request_id":    request_id,
        "actor_id":      actor_id,
        "channel":       channel,
        "action":        action,
        "resource":      resource,
        "decision":      decision,
        "reason_code":   reason_code,
        "latency_ms":    round(latency_ms, 3),
    }
    logger.info(json.dumps(event))
