# Plan: Licensed-Broker Real-Time Market Data Access

## Status: APPROVED — ready to implement

---

## Overview

Implement the security and entitlement layer that the AGENTS.md specification requires
but that does not yet exist in code. Every request — REST and MCP — must be authenticated
via JWT, have its entitlement resolved server-side, receive the correct data tier, be
rate-limited by role, and produce one structured audit event.

The existing public API response shape must be fully preserved. Fields may be added;
none may be removed or renamed. The eight changed application files are listed below.
Tests are excluded from that count per the task brief.

---

## Scope

- Replace the plain-string token check with HS256 JWT validation
  (signature, expiry, audience, issuer, required claims)
- Remove the MCP/SSE authentication bypass
- Implement server-side entitlement: BROKER + MARKET_DATA_REALTIME → REALTIME tier;
  RETAIL → DELAYED tier; BROKER without entitlement → DENY
- Apply the 15-minute quote_as_of offset for DELAYED responses
- Remove the caller-controlled data_tier query parameter (seeded defect)
- Implement per-role in-memory rate limiting (RETAIL 5 req/min, BROKER 20 req/min),
  configurable via environment variables
- Emit one structured audit event per request (ALLOW, DENY, THROTTLE) to stdout as JSON
- Fix the Authorization-header log leak in exception_handler

## Out of Scope

- Persistent audit storage (database, file, external service)
- Distributed rate limiting (Redis or equivalent) — in-memory only
- Changes to synthetic_market_data.py or synthetic_users.py data values
- Any endpoint other than /api/v1/ticker/prices for tier enforcement
  (the other endpoints are yfinance-backed and not part of the synthetic demo scenario)
- Changes to the Pydantic model field names or response envelope shape
- Token issuance, key rotation, or JWKS endpoint
- CORS policy changes

---

## Files Affected (8 application files, excluding tests)

| # | File | Change type |
|---|------|-------------|
| 1 | `src/common/auth.py` | NEW — JWT validation, claims extraction |
| 2 | `src/common/rate_limiter.py` | NEW — per-role sliding-window counter |
| 3 | `src/common/audit.py` | NEW — structured audit event emitter |
| 4 | `src/common/policy.py` | NEW — entitlement resolution, tier assignment |
| 5 | `src/models/ticker_prices_model.py` | MODIFY — add quote_as_of and data_tier fields |
| 6 | `src/common/fastapi_util.py` | MODIFY — fix Authorization header leak |
| 7 | `src/api/ticker.py` | MODIFY — pass validated identity into get_ticker_prices |
| 8 | `main.py` | MODIFY — wire JWT auth, remove bypass, remove data_tier param, add rate-limit and audit dependencies |

---

## Ordered Implementation Steps

### Step 1 — Fix the Authorization header leak
**File:** `src/common/fastapi_util.py`

**Intent:**
The exception handler currently prints `request.headers.get('authorization')` to stdout.
This must be fixed before any JWT work begins so that the new, real tokens are never
exposed in logs from the moment they are introduced.

**Change:**
Replace the `print` call with a redacted log line that records only the request path
and exception type — no header values.

**Expected outcome:**
Exceptions produce a log line containing the path and error class only.
The Authorization header value never appears in any log output.

**Acceptance check:**
Trigger a deliberate exception (e.g. call an endpoint with a bad symbol);
confirm stdout contains no token or header value.

---

### Step 2 — JWT validator + PyJWT dependency
**Files:** `src/common/auth.py` (new), `pyproject.toml` (add dependency)

**Intent:**
Centralise all JWT validation so that both the REST dependency and the MCP path
call exactly one function. This guarantees a single policy for both channels.
Add `PyJWT>=2.8.0` explicitly to `pyproject.toml` — it is used by the gitignored
`generate_JWT_tokens.py` in this repo but is not currently a declared dependency.
The `mcp[cli]` package likely pulls it in transitively, but with `uv.lock` gitignored
the transitive presence cannot be verified. Declaring it explicitly is the only safe approach.

**Contract:**
```
validate_jwt(token: str) -> dict
```
Returns the validated claims dict on success. Raises HTTPException on any failure.

**Validation sequence (all checks are mandatory; fail closed on any error):**
1. Decode with algorithm=HS256, key from env JWT_SECRET (default: demo-secret-key-not-for-production)
2. Verify audience == "adx-demo-gateway"
3. Verify issuer == "adx-demo-idp"
4. Verify exp has not passed (PyJWT handles this automatically)
5. Assert presence of claims: sub, role, entitlements, exp, aud
6. Return claims dict

**Error mapping:**
- Missing/malformed token → 401, reason TOKEN_MISSING
- Expired → 401, reason TOKEN_EXPIRED
- Bad audience → 403, reason TOKEN_AUDIENCE_INVALID
- Bad issuer → 403, reason TOKEN_AUDIENCE_INVALID (treat as same class)
- Any other decode error → 401, reason TOKEN_INVALID
- Internal error (service unavailable equivalent) → 403, reason POLICY_UNAVAILABLE

**Dependencies:**
PyJWT is available via the `mcp[cli]` transitive dependency or must be added to
pyproject.toml. Confirm presence; add `PyJWT>=2.8.0` explicitly if absent.

**Expected outcome:**
`validate_jwt` rejects all invalid tokens with the correct HTTP status and reason_code.
Valid tokens return a claims dict containing at minimum: sub, role, entitlements.
`PyJWT>=2.8.0` is declared in `pyproject.toml` dependencies.

---

### Step 3 — Entitlement and tier policy
**File:** `src/common/policy.py` (new)

**Intent:**
Separate the business decision (what tier does this identity get?) from the transport
layer (REST vs MCP) and from the data layer (how to apply the tier). This is the single
source of truth for the decision matrix.

**Contract:**
```
resolve_tier(claims: dict) -> tuple[str, str]
```
Returns `(decision, tier)` where:
- decision ∈ {ALLOW, DENY}
- tier ∈ {REALTIME, DELAYED, NONE}

**Logic (from decision matrix):**
```
role = claims["role"]
entitlements = claims["entitlements"]   # list, from validated JWT claims only

if role == "BROKER" and "MARKET_DATA_REALTIME" in entitlements:
    return ("ALLOW", "REALTIME")
elif role == "RETAIL":
    return ("ALLOW", "DELAYED")
else:
    return ("DENY", "NONE")
```

Note: the `entitlements` key name here refers to the **JWT claim** named
`entitlements`. This is independent of the `"entitlement"` / `"entitlements"` typo
in `synthetic_users.py` — that file is never consulted during request processing.
The JWT fixture tokens (in `demo/tokens.json`, gitignored) must use `entitlements`
(plural) as the claim name, consistent with this policy function.

**reason_code mapping:**
- REALTIME → ENTITLEMENT_CONFIRMED
- DELAYED  → RETAIL_DELAY_APPLIED
- DENY     → ENTITLEMENT_MISSING

**Expected outcome:**
All five decision-matrix rows for identity-based outcomes are covered.
The caller's claims — never a query parameter — are the only input to this function.

---

### Step 4 — Rate limiter
**File:** `src/common/rate_limiter.py` (new)

**Intent:**
Enforce per-role request budgets. Configurable via environment variables so limits
can be adjusted without code changes.

**Design:**
- In-memory sliding-window counter keyed on `actor_id` (sub claim)
- Read limits from env: RATE_LIMIT_RETAIL (default 5), RATE_LIMIT_BROKER (default 20)
- Window: 60 seconds
- Thread-safe using a simple lock (the process is single-worker uvicorn for demo)

**Contract:**
```
check_rate_limit(actor_id: str, role: str) -> None
```
Raises HTTPException 429 with reason_code RATE_LIMIT_EXCEEDED if over limit.
Returns None if within limit and increments the counter.

**Expected outcome:**
A retail actor making 6 requests within one minute receives 429 on the 6th.
A broker actor may make up to 20 requests per minute.
Counters reset after the 60-second window expires.

---

### Step 5 — Audit emitter
**File:** `src/common/audit.py` (new)

**Intent:**
Every request — allowed, denied, or throttled — must produce exactly one structured
event. Writing to stdout-as-JSON keeps the demo dependency-free while making events
grep-able and compatible with log aggregators.

**Contract:**
```
emit_audit_event(
    request_id: str,
    actor_id: str,
    channel: str,        # "REST" or "MCP"
    action: str,         # "GET_QUOTE", "LIST_INSTRUMENTS", etc.
    resource: str,       # symbol or endpoint path
    decision: str,       # "ALLOW", "DENY", "THROTTLE"
    reason_code: str,
    latency_ms: float,
) -> None
```
Generates event_id (UUID4) and timestamp_utc internally.
Writes one JSON line to stdout via the standard `logging` module (not `print`).

**Security invariants:**
- actor_id is always the `sub` claim — never a token, display name, or internal key
- The event must never contain the Authorization header value or token string
- No PII fields

**Expected outcome:**
Every request path — including early-exit DENY and THROTTLE paths — emits one event.
Each event is valid JSON containing all nine schema fields.

---

### Step 6 — Update TickerPriceItem model
**File:** `src/models/ticker_prices_model.py`

**Intent:**
Add the two fields the spec requires to the price response. Existing fields are
untouched; no field is removed or renamed. Both new fields are Optional so that
the model remains valid when constructed from cached data before tier is applied.

**Fields to add:**
```python
quote_as_of: Optional[datetime] = Field(None, description="Timestamp the quote is valid as-of")
data_tier: Optional[str] = Field(None, description="REALTIME or DELAYED")
```

**Expected outcome:**
The public API response for /api/v1/ticker/prices gains two new fields.
All existing fields remain present and serialise identically to before.

---

### Step 7 — Apply tier in ticker service
**File:** `src/api/ticker.py`

**Intent:**
Wire the resolved tier into the price response. The service layer receives the tier
from the caller's validated claims (passed in by the route handler), applies it, and
returns annotated price items. The service layer does not perform auth or policy
decisions — it only applies what the policy layer resolved.

**Change to get_ticker_prices:**
- Add `tier: str` parameter (REALTIME or DELAYED)
- For DELAYED: set `quote_as_of = served_at - timedelta(minutes=15)` on each item
- For REALTIME: set `quote_as_of = served_at` on each item
- Set `data_tier = tier` on each item
- `served_at` = `datetime.now(timezone.utc)` at the point of the call

**Cache interaction:**
The `@cache` decorator currently caches by `(symbol, interval, start_date, end_date)`.
Adding `tier` as a parameter would cause separate cache entries per tier, which is
incorrect — the underlying price data is the same; only the timestamps differ.

Resolution: keep the cache on the raw data fetch and apply tier annotation *after*
the cache lookup, outside the cached function. This requires splitting
`get_ticker_prices` into:
- `_fetch_ticker_prices(symbol, interval, start_date, end_date)` — cached, returns raw items
- `get_ticker_prices(symbol, interval, start_date, end_date, tier)` — uncached wrapper that calls
  the cached fetch then annotates

**Expected outcome:**
REALTIME callers receive `quote_as_of = served_at` and `data_tier = "REALTIME"`.
DELAYED callers receive `quote_as_of = served_at - 15 min` and `data_tier = "DELAYED"`.
Cache behaviour for the underlying price data is unchanged.

---

### Step 8 — Wire everything into main.py
**File:** `main.py`

**Intent:**
Replace the stub auth dependency with JWT validation, remove the MCP/SSE bypass,
remove the seeded `data_tier` query parameter, and thread the claims, rate-limit
check, and audit emission through every request.

**Changes:**

1. **Replace verify_token with a new FastAPI dependency** `authenticated_claims()`:
   - Extracts the Bearer token from any of the 6 accepted headers (preserve existing header aliases)
   - Calls `validate_jwt(token)` → claims dict
   - Calls `check_rate_limit(claims["sub"], claims["role"])`
   - Returns claims dict to the route handler
   - Raises on any failure (fail closed)
   - Remove the path-prefix bypass entirely — the MCP and SSE routes go through the
     same dependency

2. **Remove `data_tier` query parameter** from `ticker_prices()` handler entirely.
   Any caller currently passing `?data_tier=` will receive HTTP 422 Unprocessable Entity
   from FastAPI's query-param validation. This is the expected and intended behaviour —
   it is a seeded defect being removed, not a supported parameter being deprecated.

3. **Update `ticker_prices()` handler:**
   - Accept `claims: dict = Depends(authenticated_claims)`
   - Call `resolve_tier(claims)` → (decision, tier)
   - If DENY: emit audit event, raise 403
   - Call `get_ticker_prices(symbol, interval, start_date, end_date, tier)`
   - Emit audit event (ALLOW, RETAIL_DELAY_APPLIED or ENTITLEMENT_CONFIRMED)
   - Return `success(data)`

4. **Audit on error paths:**
   - Wrap the global exception handler to emit a DENY audit event before returning
     the error response
   - The handler already has request context; add latency measurement from request start

5. **Channel detection for audit:**
   - Detect channel from request path: paths starting with `/mcp` or `/sse` → "MCP",
     all others → "REST"

6. **MCP path — same policy, same function:**
   `FastApiMCP` routes MCP tool calls as internal HTTP requests through the FastAPI app,
   meaning the same `Depends(authenticated_claims)` on the route handler is invoked
   regardless of whether the original caller used REST or MCP. No separate MCP-specific
   auth code is required or permitted — this is the architectural guarantee that both
   channels share identical policy. The `test_mcp_broker_realtime` test verifies this
   by calling `authenticated_claims()` directly as a unit test with MCP-shaped input.

**Expected outcome:**
- `GET /api/v1/ticker/prices` with a valid broker+entitlement JWT → 200, REALTIME data
- Same endpoint with retail JWT → 200, DELAYED data (quote_as_of 15 min behind)
- Same endpoint with broker-no-entitlement JWT → 403, ENTITLEMENT_MISSING
- MCP call to `get_ticker_prices` with valid broker JWT → same REALTIME response
- MCP call with no token → 401
- All seven decision-matrix rows produce the correct HTTP status and reason_code
- Every request produces one audit event

---

## Security Controls Summary

| Control | Implementation location | Fail behaviour |
|---------|------------------------|----------------|
| JWT signature verification | `src/common/auth.py` | 401 / fail closed |
| Token expiry | `src/common/auth.py` (PyJWT auto) | 401 TOKEN_EXPIRED |
| Audience check | `src/common/auth.py` | 403 TOKEN_AUDIENCE_INVALID |
| Issuer check | `src/common/auth.py` | 403 TOKEN_AUDIENCE_INVALID |
| Required claims presence | `src/common/auth.py` | 401 TOKEN_INVALID |
| No auth bypass on any path | `main.py` (bypass removed) | n/a — all paths checked |
| Entitlement gate | `src/common/policy.py` | 403 ENTITLEMENT_MISSING |
| Caller cannot set own tier | `main.py` (param removed) | n/a — param absent |
| Rate limiting | `src/common/rate_limiter.py` | 429 RATE_LIMIT_EXCEEDED |
| No auth header in logs | `src/common/fastapi_util.py` | n/a — redacted |
| actor_id = sub claim only | `src/common/audit.py` | n/a — enforced by design |
| Fail closed on policy error | `src/common/auth.py` | 403 POLICY_UNAVAILABLE |

---

## Acceptance Criteria

All seven decision-matrix rows must return the correct HTTP status, tier, and reason_code:

| Identity | Expected HTTP | Expected tier | Expected reason_code |
|----------|--------------|--------------|----------------------|
| retail JWT | 200 | DELAYED | RETAIL_DELAY_APPLIED |
| broker + MARKET_DATA_REALTIME | 200 | REALTIME | ENTITLEMENT_CONFIRMED |
| broker, no entitlement | 403 | — | ENTITLEMENT_MISSING |
| expired JWT | 401 | — | TOKEN_EXPIRED |
| wrong audience | 403 | — | TOKEN_AUDIENCE_INVALID |
| missing token | 401 | — | TOKEN_MISSING |
| rate limit exceeded | 429 | — | RATE_LIMIT_EXCEEDED |

Additional criteria:
- MCP and REST paths produce identical decisions for identical credentials
- Every request emits exactly one audit event with all 9 schema fields populated
- No Authorization header value appears in any log line
- Existing response fields (date, open, high, low, close, volume, dividends, stock_splits)
  are unchanged in shape and serialisation
- `uvicorn main:app --reload` starts cleanly with no import errors
- `ruff check .` passes with no new warnings

---

## Test Cases

Each test must be written as a `def test_*()` function in `test.py` using
`httpx` or FastAPI's `TestClient` so that `pytest test.py` discovers and runs them.

### Positive tests
- `test_broker_realtime_prices` — valid broker+entitlement JWT → 200, data_tier=REALTIME,
  quote_as_of within 1 second of now
- `test_retail_delayed_prices` — valid retail JWT → 200, data_tier=DELAYED,
  quote_as_of approximately 15 minutes behind now (within 5 seconds tolerance)
- `test_mcp_broker_realtime` — same broker JWT via MCP tool call → same REALTIME result

### Negative tests
- `test_broker_no_entitlement` — broker JWT without MARKET_DATA_REALTIME → 403,
  body contains reason_code ENTITLEMENT_MISSING
- `test_expired_token` — expired JWT → 401, reason_code TOKEN_EXPIRED
- `test_wrong_audience` — JWT with aud="other-service" → 403, reason_code TOKEN_AUDIENCE_INVALID
- `test_missing_token` — no Authorization header → 401, reason_code TOKEN_MISSING
- `test_data_tier_param_absent` — confirm `?data_tier=REALTIME` returns HTTP 422;
  the parameter was a seeded defect and is now absent from the API contract

### Dependency-failure tests
- `test_invalid_jwt_signature` — JWT signed with wrong key → 401
- `test_malformed_jwt` — non-JWT string as bearer token → 401
- `test_rate_limit_retail` — 6 requests from retail actor within 60s → 6th returns 429,
  reason_code RATE_LIMIT_EXCEEDED
- `test_rate_limit_broker` — 21 requests from broker within 60s → 21st returns 429

### Audit tests
- `test_audit_event_emitted_on_allow` — capture stdout, verify one JSON event per request
  containing all 9 fields, actor_id matches sub claim, no token value present
- `test_audit_event_emitted_on_deny` — denied request produces one DENY event

---

## Rollback Plan

All changes are confined to the 8 files listed. No schema migrations, no external
service dependencies, no database changes.

To rollback:
1. `git revert` the commit containing the 8 changed files, or
2. Restore each file from its pre-change state via `git checkout <sha> -- <file>`

The application will return to the stub-auth state (plain-string token, no tier,
no audit) which is the current baseline. No data is at risk.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PyJWT missing from resolved deps on clean install | Low — mitigated | High | Explicit `PyJWT>=2.8.0` declaration in pyproject.toml closes this; confirmed used by generate_JWT_tokens.py |
| MCP library re-introduces auth bypass internally | Low | High | Test no-token MCP call explicitly; assert 401 |
| `@cache` keyed on `tier` would split cache incorrectly | Certain if naive | Medium | Resolved in Step 7: split `_fetch_ticker_prices` (cached) from annotation wrapper (uncached) |
| `entitlements` typo in synthetic_users.py affects tests | Low | Low | Tests use JWT claims directly, not the synthetic_users dict; no impact |
| Rate limiter state lost on worker restart | Inherent | Low | Acceptable for in-memory demo; noted in code comments |
| JWT claim name `entitlements` (plural) must match fixture tokens | Medium | High | Confirmed plural in policy.py; fixture tokens must use the same name — document in test setup comment |
| Existing callers passing `?data_tier=` will get 422 | Certain | Low | Seeded defect intentionally removed; 422 is correct and expected |
