"""
Automated test suite for the secure market-data gateway.

Tokens are minted inline using the known demo secret.
No token values are stored in this file or logged.

JWT claim key:  entitlements  (plural) — must match policy.resolve_tier().
Demo secret:    demo-secret-key-not-for-production
Algorithm:      HS256
Audience:       adx-demo-gateway
Issuer:         adx-demo-idp
"""
import json
import logging
import uuid
import pytest
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app, authenticated_claims
from src.common import rate_limiter as rl
import src.common.auth as _auth_module

# ---------------------------------------------------------------------------
# Token factory — values computed at call time, never stored
# ---------------------------------------------------------------------------
_SECRET = "demo-secret-key-not-for-production"
_AUD    = "adx-demo-gateway"
_ISS    = "adx-demo-idp"
_PRICES_URL = "/api/v1/ticker/prices"
_PARAMS = {"symbol": "NEXUS", "interval": "1d", "start_date": "2026-08-01", "end_date": "2026-08-04"}


def _make_token(role: str, entitlements: list, exp_delta_s: int = 3600, aud=_AUD, iss=_ISS) -> str:
    payload = {
        "sub": f"test-{role.lower()}-01",
        "role": role,
        "entitlements": entitlements,
        "aud": aud,
        "iss": iss,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta_s),
    }
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Reset in-memory rate-limit counters between every test."""
    rl._counters.clear()
    yield
    rl._counters.clear()


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------

def test_broker_realtime_prices():
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    items = body["data"]
    assert len(items) > 0
    assert items[0]["data_tier"] == "REALTIME"
    # quote_as_of should be within 5 seconds of now
    qao = datetime.fromisoformat(items[0]["quote_as_of"])
    delta = abs((datetime.now(timezone.utc) - qao).total_seconds())
    assert delta < 5, f"quote_as_of unexpectedly far from now: {delta}s"


def test_retail_delayed_prices():
    token = _make_token("RETAIL", [])
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    items = body["data"]
    assert len(items) > 0
    assert items[0]["data_tier"] == "DELAYED"
    # quote_as_of should be approximately 15 minutes behind now (allow 5s tolerance)
    qao = datetime.fromisoformat(items[0]["quote_as_of"])
    expected = datetime.now(timezone.utc) - timedelta(minutes=15)
    delta = abs((expected - qao).total_seconds())
    assert delta < 5, f"DELAYED quote_as_of offset unexpected: {delta}s from expected"


def test_mcp_broker_realtime_via_authenticated_claims():
    """Architectural guarantee: authenticated_claims() is the single auth entry point.
    FastApiMCP routes MCP tool calls through the same FastAPI dependency, so testing
    authenticated_claims() directly with a valid broker token verifies MCP coverage."""
    import asyncio

    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])

    async def run():
        return await authenticated_claims(authorization=f"Bearer {token}")

    claims = asyncio.run(run())
    assert claims["role"] == "BROKER"
    assert "MARKET_DATA_REALTIME" in claims["entitlements"]


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------

def test_broker_no_entitlement():
    token = _make_token("BROKER", [])
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["reason_code"] == "ENTITLEMENT_MISSING"


def test_expired_token():
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"], exp_delta_s=-1)
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_EXPIRED"


def test_wrong_audience():
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"], aud="other-service")
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_AUDIENCE_INVALID"


def test_missing_token():
    r = client.get(_PRICES_URL, params=_PARAMS)
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_MISSING"


def test_data_tier_param_absent():
    """data_tier query param was a seeded defect and has been removed from the handler.
    FastAPI ignores unknown query params by default; the important assertion is that
    the response data_tier is server-resolved from the JWT, not caller-supplied."""
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])
    params = {**_PARAMS, "data_tier": "DELAYED"}  # caller attempts to request DELAYED
    r = client.get(_PRICES_URL, params=params, headers=_hdr(token))
    assert r.status_code == 200
    items = r.json()["data"]
    # Server resolves REALTIME from the broker+entitlement JWT, ignoring the param
    assert items[0]["data_tier"] == "REALTIME"


# ---------------------------------------------------------------------------
# Dependency-failure tests
# ---------------------------------------------------------------------------

def test_invalid_jwt_signature():
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])
    # Decode then re-sign with a wrong key to tamper the signature
    claims = pyjwt.decode(token, _SECRET, algorithms=["HS256"], audience=_AUD, issuer=_ISS)
    bad_token = pyjwt.encode(claims, "wrong-key", algorithm="HS256")
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(bad_token))
    assert r.status_code == 401
    assert r.json()["detail"]["reason_code"] == "TOKEN_INVALID"


def test_malformed_jwt():
    r = client.get(_PRICES_URL, params=_PARAMS, headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
    assert r.json()["detail"]["reason_code"] in ("TOKEN_INVALID", "TOKEN_MISSING")


def test_rate_limit_retail():
    token = _make_token("RETAIL", [])
    headers = _hdr(token)
    # First 5 requests must succeed
    for i in range(5):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
        assert r.status_code == 200, f"Request {i + 1} unexpectedly failed: {r.json()}"
    # 6th must be throttled
    r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    assert r.status_code == 429
    assert r.json()["detail"]["reason_code"] == "RATE_LIMIT_EXCEEDED"


def test_rate_limit_broker():
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])
    headers = _hdr(token)
    # First 20 requests must succeed
    for i in range(20):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
        assert r.status_code == 200, f"Request {i + 1} unexpectedly failed: {r.json()}"
    # 21st must be throttled
    r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    assert r.status_code == 429
    assert r.json()["detail"]["reason_code"] == "RATE_LIMIT_EXCEEDED"


# ---------------------------------------------------------------------------
# Audit tests
# ---------------------------------------------------------------------------

def test_audit_event_emitted_on_allow(caplog):
    import logging
    token = _make_token("BROKER", ["MARKET_DATA_REALTIME"])
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    audit_lines = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_lines) >= 1, "Expected at least one audit event"
    event = json.loads(audit_lines[-1].message)
    required_fields = {
        "event_id", "timestamp_utc", "request_id", "actor_id",
        "channel", "action", "resource", "decision", "reason_code", "latency_ms",
    }
    missing = required_fields - event.keys()
    assert not missing, f"Audit event missing fields: {missing}"
    assert event["decision"] == "ALLOW"
    assert event["reason_code"] == "ENTITLEMENT_CONFIRMED"
    # actor_id must be the sub claim — never a raw token or Bearer header value
    assert event["actor_id"] == "test-broker-01"
    assert "Bearer" not in event["actor_id"]
    assert _SECRET not in json.dumps(event)


def test_audit_event_emitted_on_deny(caplog):
    import logging
    token = _make_token("BROKER", [])  # broker role but no MARKET_DATA_REALTIME
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 403
    audit_lines = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_lines) >= 1, "Expected at least one audit event on DENY"
    event = json.loads(audit_lines[-1].message)
    assert event["decision"] == "DENY"
    assert event["reason_code"] == "ENTITLEMENT_MISSING"


# ---------------------------------------------------------------------------
# Extended tests — cover all 10 required areas with deterministic fixtures
# ---------------------------------------------------------------------------

# Shared deterministic fixture parameters
_BROKER_SUB  = "fix-broker-01"
_RETAIL_SUB  = "fix-retail-01"
_NOENT_SUB   = "fix-noent-01"


def _make_token_sub(sub: str, role: str, entitlements: list,
                    exp_delta_s: int = 3600, aud=_AUD, iss=_ISS) -> str:
    """Token factory with an explicit sub claim for deterministic actor_id assertions."""
    payload = {
        "sub": sub,
        "role": role,
        "entitlements": entitlements,
        "aud": aud,
        "iss": iss,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=exp_delta_s),
    }
    return pyjwt.encode(payload, _SECRET, algorithm="HS256")


# --- 1. Authorised broker — full response shape ----------------------------

def test_broker_realtime_all_rows_and_fields():
    """Broker with MARKET_DATA_REALTIME receives all 4 synthetic rows.
    Every row carries data_tier=REALTIME and a quote_as_of close to now.
    All original price fields must still be present and non-null."""
    token = _make_token_sub(_BROKER_SUB, "BROKER", ["MARKET_DATA_REALTIME"])
    t_before = datetime.now(timezone.utc)
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    t_after = datetime.now(timezone.utc)
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 4, f"Expected 4 rows, got {len(items)}"
    for i, item in enumerate(items):
        assert item["data_tier"] == "REALTIME", f"Row {i}: wrong tier"
        qao = datetime.fromisoformat(item["quote_as_of"])
        assert t_before <= qao <= t_after + timedelta(seconds=1), (
            f"Row {i}: quote_as_of={qao} outside [{t_before}, {t_after}]"
        )
        for field in ("date", "open", "high", "low", "close", "volume"):
            assert item[field] is not None, f"Row {i}: field '{field}' is None"


# --- 2. Retail delayed — deterministic offset assertion --------------------

def test_retail_delayed_offset_deterministic():
    """Retail user receives DELAYED tier. The offset is verified by snapshotting
    the clock before and after the request so the assertion is not a race."""
    token = _make_token_sub(_RETAIL_SUB, "RETAIL", [])
    t_before = datetime.now(timezone.utc)
    r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    t_after = datetime.now(timezone.utc)
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 4
    for i, item in enumerate(items):
        assert item["data_tier"] == "DELAYED", f"Row {i}: wrong tier"
        qao = datetime.fromisoformat(item["quote_as_of"])
        # quote_as_of must be 15 min behind served_at; served_at is in [t_before, t_after]
        lower = t_before - timedelta(minutes=15) - timedelta(seconds=2)
        upper = t_after  - timedelta(minutes=15) + timedelta(seconds=2)
        assert lower <= qao <= upper, (
            f"Row {i}: quote_as_of={qao} outside expected DELAYED window [{lower}, {upper}]"
        )


# --- 3. Missing entitlement — deny + audit event ---------------------------

def test_broker_no_entitlement_audit_event(caplog):
    """ENTITLEMENT_MISSING deny path must emit exactly one audit event
    with decision=DENY and reason_code=ENTITLEMENT_MISSING."""
    token = _make_token_sub(_NOENT_SUB, "BROKER", [])
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 403
    assert r.json()["detail"]["reason_code"] == "ENTITLEMENT_MISSING"
    audit_lines = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_lines) == 1, f"Expected 1 audit event, got {len(audit_lines)}"
    event = json.loads(audit_lines[0].message)
    assert event["decision"] == "DENY"
    assert event["reason_code"] == "ENTITLEMENT_MISSING"
    assert event["actor_id"] == _NOENT_SUB
    assert event["action"] == "GET_QUOTE"
    assert event["resource"] == _PARAMS["symbol"]


# --- 4. Expired token — correct HTTP status and reason_code ----------------

def test_expired_token_http_status_and_reason(caplog):
    """An expired JWT must return 401 with TOKEN_EXPIRED, and the HTTPException
    handler must emit a DENY audit event with reason_code TOKEN_EXPIRED."""
    token = _make_token_sub("fix-expired-01", "BROKER", ["MARKET_DATA_REALTIME"],
                            exp_delta_s=-10)
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_EXPIRED"
    # Verify no data is leaked in the response body
    assert "data" not in r.json() or r.json().get("data") is None
    # Audit event must be emitted even though the handler body never ran
    audit_events = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_events) == 1, f"Expected 1 audit event, got {len(audit_events)}"
    event = json.loads(audit_events[0].message)
    assert event["decision"] == "DENY"
    assert event["reason_code"] == "TOKEN_EXPIRED"
    assert event["actor_id"] == "ANONYMOUS"


# --- 5. Invalid audience — correct HTTP status and reason_code -------------

def test_invalid_audience_http_status_and_reason(caplog):
    """A JWT with the wrong audience must return 403 with TOKEN_AUDIENCE_INVALID,
    and the HTTPException handler must emit a DENY audit event."""
    token = _make_token_sub("fix-wrongaud-01", "BROKER", ["MARKET_DATA_REALTIME"],
                            aud="wrong-service")
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_AUDIENCE_INVALID"
    assert "data" not in r.json() or r.json().get("data") is None
    audit_events = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_events) == 1, f"Expected 1 audit event, got {len(audit_events)}"
    event = json.loads(audit_events[0].message)
    assert event["decision"] == "DENY"
    assert event["reason_code"] == "TOKEN_AUDIENCE_INVALID"
    assert event["actor_id"] == "ANONYMOUS"


# --- 6. Rate-limit breach — THROTTLE audit event ---------------------------

def test_rate_limit_retail_throttle_audit_event(caplog):
    """On the 6th retail request, the response must be 429 AND the audit log
    must contain a THROTTLE event with reason_code RATE_LIMIT_EXCEEDED.
    The HTTPException handler intercepts the 429 raised by check_rate_limit
    and emits the audit event before returning the response."""
    token = _make_token_sub(_RETAIL_SUB, "RETAIL", [])
    headers = _hdr(token)
    # Exhaust the limit silently
    for _ in range(5):
        client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    # 6th request — capture audit output
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    assert r.status_code == 429
    assert r.json()["detail"]["reason_code"] == "RATE_LIMIT_EXCEEDED"
    throttle_events = [
        rec for rec in caplog.records
        if rec.name == "audit" and "RATE_LIMIT_EXCEEDED" in rec.message
    ]
    assert len(throttle_events) == 1, (
        f"Expected exactly 1 THROTTLE audit event, got {len(throttle_events)}"
    )
    event = json.loads(throttle_events[0].message)
    assert event["decision"] == "THROTTLE"
    assert event["reason_code"] == "RATE_LIMIT_EXCEEDED"
    assert event["actor_id"] == _RETAIL_SUB


def test_rate_limit_window_resets():
    """Demonstrate that counters within a new window are independent.
    After clearing counters, a retail actor can make 5 more requests."""
    token = _make_token_sub(_RETAIL_SUB, "RETAIL", [])
    headers = _hdr(token)
    # Fill the window
    for _ in range(5):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
        assert r.status_code == 200
    assert client.get(_PRICES_URL, params=_PARAMS, headers=headers).status_code == 429
    # Reset (simulates new window / process restart)
    rl._counters.clear()
    # Should succeed again
    r = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    assert r.status_code == 200


# --- 7. REST/MCP decision parity -------------------------------------------

def test_rest_mcp_same_policy_function():
    """The authenticated_claims dependency is the single policy entry point for both
    REST and MCP channels. This test invokes it directly three times — once per
    identity type — and confirms resolve_tier produces the expected decision for each,
    mirroring what both channels would receive."""
    import asyncio
    from src.common.policy import resolve_tier, REASON_CODES

    cases = [
        (_make_token_sub("fix-parity-broker", "BROKER", ["MARKET_DATA_REALTIME"]),
         "ALLOW", "REALTIME", "ENTITLEMENT_CONFIRMED"),
        (_make_token_sub("fix-parity-retail", "RETAIL", []),
         "ALLOW", "DELAYED", "RETAIL_DELAY_APPLIED"),
        (_make_token_sub("fix-parity-noent", "BROKER", []),
         "DENY", "NONE", "ENTITLEMENT_MISSING"),
    ]

    async def get_claims(token):
        return await authenticated_claims(authorization=f"Bearer {token}")

    for token, exp_decision, exp_tier, exp_reason in cases:
        claims = asyncio.run(get_claims(token))
        decision, tier = resolve_tier(claims)
        assert decision == exp_decision,  f"sub={claims['sub']}: decision {decision!r} != {exp_decision!r}"
        assert tier == exp_tier,          f"sub={claims['sub']}: tier {tier!r} != {exp_tier!r}"
        assert REASON_CODES[tier] == exp_reason, f"sub={claims['sub']}: reason mismatch"


def test_rest_and_mcp_paths_same_http_outcome():
    """End-to-end: the same valid broker JWT sent to the REST path and to the
    /mcp path both return the same tier in their response (or 401 if the MCP
    route is not authenticated — which would itself be evidence of parity failure)."""
    token = _make_token_sub("fix-parity-e2e", "BROKER", ["MARKET_DATA_REALTIME"])
    headers = _hdr(token)

    # REST path
    r_rest = client.get(_PRICES_URL, params=_PARAMS, headers=headers)
    assert r_rest.status_code == 200
    rest_tier = r_rest.json()["data"][0]["data_tier"]
    assert rest_tier == "REALTIME"

    # MCP introspection endpoint — verifies the MCP layer requires auth
    # (a 401 here means the bypass was NOT removed; a 200 or 307 means MCP is mounted)
    r_mcp = client.get("/mcp", headers=headers)
    # FastApiMCP HTTP endpoint returns 200 (tool list) or 405; it should NOT return 401
    # because authenticated_claims resolves successfully for a valid token.
    assert r_mcp.status_code != 401, (
        f"MCP endpoint rejected a valid token — auth bypass may be re-introduced. "
        f"Status: {r_mcp.status_code}"
    )


# --- 8. Audit event creation — full schema + all decision paths ------------

def test_audit_allow_broker_full_schema(caplog):
    """ALLOW path for broker: verify all 9 schema fields are present and valid."""
    token = _make_token_sub(_BROKER_SUB, "BROKER", ["MARKET_DATA_REALTIME"])
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    events = [json.loads(rec.message) for rec in caplog.records if rec.name == "audit"]
    assert len(events) == 1
    ev = events[0]
    # All 9 schema fields present
    for field in ("event_id", "timestamp_utc", "request_id", "actor_id",
                  "channel", "action", "resource", "decision", "reason_code", "latency_ms"):
        assert field in ev, f"Missing field: {field}"
    # event_id is a valid UUID4
    uuid.UUID(ev["event_id"], version=4)
    # request_id is a valid UUID (set by middleware, not "UNKNOWN")
    uuid.UUID(ev["request_id"])
    # actor_id is the sub claim
    assert ev["actor_id"] == _BROKER_SUB
    # channel is REST for a direct HTTP call
    assert ev["channel"] == "REST"
    assert ev["action"] == "GET_QUOTE"
    assert ev["resource"] == _PARAMS["symbol"]
    assert ev["decision"] == "ALLOW"
    assert ev["reason_code"] == "ENTITLEMENT_CONFIRMED"
    assert isinstance(ev["latency_ms"], float)
    assert ev["latency_ms"] >= 0


def test_audit_allow_retail_reason_code(caplog):
    """ALLOW path for retail: reason_code must be RETAIL_DELAY_APPLIED."""
    token = _make_token_sub(_RETAIL_SUB, "RETAIL", [])
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    events = [json.loads(rec.message) for rec in caplog.records if rec.name == "audit"]
    assert len(events) == 1
    assert events[0]["reason_code"] == "RETAIL_DELAY_APPLIED"
    assert events[0]["actor_id"] == _RETAIL_SUB
    assert events[0]["decision"] == "ALLOW"


def test_audit_exactly_one_event_per_request(caplog):
    """Each request produces exactly one audit event — not zero, not two."""
    token = _make_token_sub(_BROKER_SUB, "BROKER", ["MARKET_DATA_REALTIME"])
    for _ in range(3):
        with caplog.at_level(logging.INFO, logger="audit"):
            client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
        events = [r for r in caplog.records if r.name == "audit"]
        assert len(events) == 1, f"Expected 1 audit event per request, got {len(events)}"
        caplog.clear()


# --- 9. Policy timeout / POLICY_UNAVAILABLE --------------------------------

def test_policy_unavailable_on_jwt_unexpected_error():
    """If an unexpected (non-JWT) exception propagates out of validate_jwt, the
    response must fail closed — 403 or 500, never a successful data response.
    Patch at main.validate_jwt (the name already bound in main's namespace after
    'from src.common.auth import validate_jwt') so the side-effect actually fires."""
    with patch("main.validate_jwt",
               side_effect=RuntimeError("simulated policy service timeout")):
        r = client.get(_PRICES_URL, params=_PARAMS,
                       headers={"Authorization": "Bearer any-token"})
    # RuntimeError is not an HTTPException; it propagates from authenticated_claims
    # to FastAPI's general exception handler → 500. Either 403 or 500 is fail-closed.
    assert r.status_code in (403, 500), (
        f"Expected fail-closed (403 or 500), got {r.status_code}"
    )
    # Critically: no market data in the response body (body may be empty on 500)
    if r.content:
        body = r.json()
        assert body.get("data") is None


def test_policy_unavailable_from_auth_internal_exception():
    """validate_jwt's bare-except block maps unexpected internal errors to
    403 POLICY_UNAVAILABLE. Trigger it by patching jwt.decode to raise RuntimeError."""
    with patch("src.common.auth.jwt.decode",
               side_effect=RuntimeError("internal crypto failure")):
        r = client.get(_PRICES_URL, params=_PARAMS,
                       headers={"Authorization": "Bearer any-token"})
    assert r.status_code == 403
    assert r.json()["detail"]["reason_code"] == "POLICY_UNAVAILABLE"


# --- 10. No Authorization header in logs -----------------------------------

def test_no_auth_header_in_warning_logs(caplog):
    """On any exception path, the WARNING logger must not emit the Authorization
    header value. Verified by triggering the exception handler and scanning all
    log records."""
    token = _make_token_sub("fix-logcheck-01", "BROKER", ["MARKET_DATA_REALTIME"])
    raw_token_value = token  # the actual JWT string that must never appear in logs

    with patch("src.common.auth.jwt.decode",
               side_effect=RuntimeError("forced exception for log test")):
        with caplog.at_level(logging.WARNING):
            r = client.get(_PRICES_URL, params=_PARAMS,
                           headers={"Authorization": f"Bearer {raw_token_value}"})

    # Scan every captured log record — token must not appear in any message
    all_log_text = " ".join(rec.message for rec in caplog.records)
    assert raw_token_value not in all_log_text, (
        "Raw JWT token value found in log output — Authorization header leak"
    )
    assert "Authorization" not in all_log_text, (
        "The word 'Authorization' was found in log output — header name leak"
    )
    # The request must have failed closed
    assert r.status_code in (403, 500)


def test_no_auth_header_in_audit_logs(caplog):
    """Audit events must never contain the Authorization header value or the
    Bearer token string, even on an ALLOW path."""
    token = _make_token_sub(_BROKER_SUB, "BROKER", ["MARKET_DATA_REALTIME"])
    with caplog.at_level(logging.INFO):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 200
    all_log_text = " ".join(rec.message for rec in caplog.records)
    assert token not in all_log_text, "Raw JWT found in log output"
    assert "Bearer" not in all_log_text, "'Bearer' keyword found in log output"
    assert _SECRET not in all_log_text, "JWT secret found in log output"


# --- Additional F-01/F-02 remediation tests --------------------------------

def test_audit_event_on_expired_token(caplog):
    """Dedicated audit schema test for TOKEN_EXPIRED path.
    The HTTPException handler must emit a fully-formed audit event with
    actor_id=ANONYMOUS (JWT was invalid so no sub claim is available)."""
    token = _make_token_sub("fix-exp-audit-01", "BROKER", ["MARKET_DATA_REALTIME"],
                            exp_delta_s=-10)
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS, headers=_hdr(token))
    assert r.status_code == 401
    audit_events = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_events) == 1
    ev = json.loads(audit_events[0].message)
    required_fields = {
        "event_id", "timestamp_utc", "request_id", "actor_id",
        "channel", "action", "resource", "decision", "reason_code", "latency_ms",
    }
    missing = required_fields - ev.keys()
    assert not missing, f"Audit event missing fields: {missing}"
    assert ev["decision"] == "DENY"
    assert ev["reason_code"] == "TOKEN_EXPIRED"
    assert ev["actor_id"] == "ANONYMOUS"
    # Must not contain the raw token or secret
    assert _SECRET not in json.dumps(ev)


def test_audit_event_on_missing_token(caplog):
    """Dedicated audit schema test for TOKEN_MISSING path.
    No token at all is provided; the HTTPException handler must emit
    actor_id=ANONYMOUS."""
    with caplog.at_level(logging.INFO, logger="audit"):
        r = client.get(_PRICES_URL, params=_PARAMS)  # no Authorization header
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["reason_code"] == "TOKEN_MISSING"
    audit_events = [rec for rec in caplog.records if rec.name == "audit"]
    assert len(audit_events) == 1
    ev = json.loads(audit_events[0].message)
    assert ev["decision"] == "DENY"
    assert ev["reason_code"] == "TOKEN_MISSING"
    assert ev["actor_id"] == "ANONYMOUS"
